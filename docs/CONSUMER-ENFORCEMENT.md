# Consumer-side enforcement runbook

How a customer (or our own e2e) makes a **modified** eBPFsentinel artifact
refuse to run. Two independent layers, each verifiable by the customer
against evidence the attacker does not control:

| Layer | Enforces | Who verifies |
|---|---|---|
| Registry signature (cosign keyless + Rekor) | image/binary is authentic | anyone, offline-capable (`verify.sh`) |
| Cluster admission (Kyverno `verifyImages`) | only signed digests run in k8s | the customer's cluster |
| Attestations (SBOM, vulnerability scan, VEX) | what we knew about the image when we shipped it | `cosign verify-attestation`, Kyverno |
| Revocation list (dual-signed, monotonic serial) | withdrawn digests stop running | `check-revocation.sh`, Kyverno deny policy |

Break the artifact anywhere → its digest changes → no signature exists for
the new digest under our identity → **admission rejects it**. The single
verification identity to pin is in
[`policy/cosign-public.md`](../policy/cosign-public.md).

---

## 1. Cluster admission (Kubernetes)

Install [Kyverno](https://kyverno.io/), then the policy:

```bash
kubectl apply -f policy/kyverno-verify-images.yaml
```

The cluster now rejects any `ghcr.io/ebpfsentinel/*` image lacking a valid
cosign signature from our release identity, and `mutateDigest: true` rewrites
tags to the verified digest so running pods are immutable.

Smoke-test that it rejects a tampered image:

```bash
# A re-tagged / rebuilt image has an unsigned digest → admission denies it.
kubectl run rogue --image ghcr.io/ebpfsentinel/ebpfsentinel:tampered
# Error from server: ... failed to verify image ... no matching signatures
```

> Already running the **Sigstore Policy Controller** instead of Kyverno? Use
> [`policy/policy-controller-clusterimagepolicy.yaml`](../policy/policy-controller-clusterimagepolicy.yaml)
> — same guarantee, cosign-native. Run only one of the two enforcers.

### Attestations

Every image carries an SPDX SBOM, a dated vulnerability scan, and — where we
have something to say about a CVE — OpenVEX statements. Read them:

```bash
REF=ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest>
ID_RE='^https://github.com/ebpfsentinel/ebpfsentinel-release/.github/workflows/sign-image.yml@refs/tags/v'

# What is inside / what was known to be wrong with it / what we assert about it
for t in spdxjson vuln openvex; do
  cosign verify-attestation --type "$t" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity-regexp "$ID_RE" \
    --certificate-github-workflow-repository ebpfsentinel/ebpfsentinel "$REF" \
    | jq -r '.payload | @base64d | fromjson | .predicate'
done
```

To require them at admission — including that the scan is recent, not merely
present — apply
[`policy/kyverno-verify-attestations.yaml`](../policy/kyverno-verify-attestations.yaml)
alongside the signature policy.

A scan attestation is a statement about the day it ran, not about today. Treat
an old one as an old one: the policy bounds it at 30 days, and the honest read
of a passing check is "nothing known then", not "nothing wrong now".

## 2. GitOps: deploy by digest

Public packages need **no pull secret**. Pin images by digest so what you
verified is exactly what runs — Kyverno's `mutateDigest` enforces this at
admission, and your GitOps tool should pin at the source too:

- **Argo CD** — reference `…@sha256:<digest>` in your Application manifests
  (or use the Argo Image Updater with `digest` update strategy).
- **Flux** — `ImagePolicy` with `digestReflectionPolicy: Always`, or pin the
  digest directly in the `HelmRelease`/`Kustomization`.

Charts are OCI artifacts signed the same way; verify the chart digest with
`verify.sh image oci://ghcr.io/ebpfsentinel/charts/<chart>@sha256:<digest>`.

## 3. License delivery (the only per-customer artifact)

Everything else is public + identical for all customers. Deliver the license
as a Kubernetes Secret via **External Secrets Operator** (kept in your vault)
or **SOPS** (encrypted in Git) — see `policy/license-external-secret.yaml`.
The agent reads it at `enterprise.license_path` / `--license`.

## 4. Bare metal / no Kubernetes

Use `policy/verify.sh` (ships with each release) to verify images, tarballs,
and the `SHA256SUMS` before install. See `policy/cosign-public.md` for the
raw cosign / `gh attestation verify` commands.

## 5. Revocation

A signature never expires and never changes its mind. When an artifact is
withdrawn — a critical defect, a compromised build — the signature on it stays
valid, so signature checking alone will keep admitting it. Poll the signed
list and enforce it:

```bash
gh release download revocations/current -R ebpfsentinel/ebpfsentinel-release -D rev
./verify.sh sums rev/SHA256SUMS rev/SHA256SUMS.sig rev/SHA256SUMS.crt
./check-revocation.sh rev/revocations.json sha256:<digest>      # exit 3 = revoked

# Kubernetes: apply next to kyverno-verify-images.yaml
./gen-revocation-policy.sh rev/revocations.json > kyverno-deny-revoked.yaml
kubectl apply -f kyverno-deny-revoked.yaml
```

`verify.sh` checks the list too when you point it at one:
`REVOCATIONS=rev/revocations.json ./verify.sh image <ref@sha256:...>`.

The list carries a monotonic `serial`; reject any list whose serial is lower
than one you have already seen, or an adversary can replay an older, shorter
list at you. Full procedure in [`REVOCATION.md`](REVOCATION.md).

## 6. Air-gapped / disconnected sites

Keyless verification normally calls the public Sigstore transparency log
(Rekor) at verify time. Two options when the site has no route to it:

- **Verify offline.** Signatures embed their Rekor inclusion proof, so no
  network call is needed. Set `OFFLINE=1`:

  ```bash
  OFFLINE=1 ./verify.sh image ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest>
  # Blobs use the *.bundle shipped next to *.sig/*.crt:
  OFFLINE=1 ./verify.sh sums SHA256SUMS SHA256SUMS.sig SHA256SUMS.crt
  ```

- **Rely on the key-based layer.** The signed measurements manifest is
  dual-signed (Ed25519 + ML-DSA-65) with our release signing keys and verifies
  **fully offline** — no Fulcio/Rekor at all. Both public keys ship as assets
  of the same `measurements/v*` release, so nothing else needs downloading:

  ```bash
  ebpfsentinel-license verify-manifest \
    --input measurements.signed \
    --public-key release-signing-ed25519.pub \
    --pq-public-key release-signing-mldsa.pub
  ```

  Both signatures must verify. That is the natural trust path for enterprise
  air-gap deployments; the keyless image chain is the connected-site path.
  Licenses are signed with a *different* pair — see
  [`KEY-MANAGEMENT.md`](KEY-MANAGEMENT.md).
