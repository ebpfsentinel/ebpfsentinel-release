# Consumer-side enforcement runbook

How a customer (or our own e2e) makes a **modified** eBPFsentinel artifact
refuse to run. Two independent layers, each verifiable by the customer
against evidence the attacker does not control:

| Layer | Enforces | Who verifies |
|---|---|---|
| Registry signature (cosign keyless + Rekor) | image/binary is authentic | anyone, offline-capable (`verify.sh`) |
| Cluster admission (Kyverno `verifyImages`) | only signed digests run in k8s | the customer's cluster |

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

## 5. Air-gapped / disconnected sites

Keyless verification normally calls the public Sigstore transparency log
(Rekor) at verify time. Two options when the site has no route to it:

- **Verify offline.** Signatures embed their Rekor inclusion proof, so no
  network call is needed. Set `OFFLINE=1`:

  ```bash
  OFFLINE=1 ./verify.sh image ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest>
  # Blobs use the *.bundle shipped next to *.sig/*.crt:
  OFFLINE=1 ./verify.sh sums SHA256SUMS SHA256SUMS.sig SHA256SUMS.crt
  ```

- **Rely on the key-based layer.** The signed measurements manifest and the
  license are dual-signed (Ed25519 + ML-DSA-65) with our own keys and verify
  **fully offline** — no Fulcio/Rekor at all. That is the natural trust path
  for enterprise air-gap deployments; the keyless image chain is the
  connected-site path.
