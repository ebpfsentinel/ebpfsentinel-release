# Verifying eBPFsentinel artifacts

Every eBPFsentinel container image and release binary is signed with
[cosign](https://docs.sigstore.dev/) **keyless** — there is no public key
to distribute. Trust is anchored on the identity of the release signing
workflow plus the Sigstore transparency log (Rekor).

## Trust anchor

| Field | Value |
|---|---|
| OIDC issuer | `https://token.actions.githubusercontent.com` |
| Signing identity | `https://github.com/ebpfsentinel/ebpfsentinel-release/.github/workflows/{sign-image,sign-blob}.yml@refs/tags/v*` |
| Source repository | one of `ebpfsentinel/ebpfsentinel`, `-enterprise`, `-operator`, `-dashboard`, `-release` |
| Transparency log | `https://rekor.sigstore.dev` |

Any modification to an image or binary changes its digest; no signature
exists for the new digest under this identity, so verification fails.

**Always check the source repository as well as the identity.** Our signing
workflows are *reusable* workflows, so Sigstore records the called workflow as
the certificate subject — the subject alone does not say which repository
requested the signature. `verify.sh` pins both; if you write your own
verification, pass `--certificate-github-workflow-repository`.

## Kubernetes (recommended)

Install the Kyverno policy — the cluster then refuses any unsigned or
tampered eBPFsentinel image at admission, and pins running pods to the
verified digest:

```bash
kubectl apply -f kyverno-verify-images.yaml   # requires Kyverno installed
```

## Bare metal / manual

Use the helper:

```bash
# Image (by digest):
./verify.sh image ghcr.io/ebpfsentinel/ebpfsentinel-dashboard@sha256:<digest>

# Release tarball:
./verify.sh blob ebpfsentinel-agent-amd64.tar.gz \
  ebpfsentinel-agent-amd64.tar.gz.sig ebpfsentinel-agent-amd64.tar.gz.crt

# Whole release manifest, then the files:
./verify.sh sums SHA256SUMS SHA256SUMS.sig SHA256SUMS.crt
sha256sum -c SHA256SUMS
```

**Air-gapped?** Set `OFFLINE=1` to verify without reaching Rekor — images
verify from the inclusion proof embedded in the signature, blobs from the
`*.bundle` shipped alongside `*.sig`/`*.crt`:

```bash
OFFLINE=1 ./verify.sh image ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest>
```

Or the raw cosign command:

```bash
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/ebpfsentinel/ebpfsentinel-release/.github/workflows/(sign-image|sign-blob)\.yml@refs/tags/v.*$' \
  --certificate-github-workflow-repository ebpfsentinel/ebpfsentinel \
  ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest>
```

Set `--certificate-github-workflow-repository` to the repository the artifact
was released from (`ebpfsentinel/ebpfsentinel-enterprise` for the enterprise
agent, `-operator`, `-dashboard`, and `-release` for the measurements
manifest). `verify.sh` does this for you — with `SOURCE_REPO=<owner>/<repo>`
to pin one exact origin, or unset to accept any eBPFsentinel product repo.

GitHub build-provenance attestations (on release binaries) can also be
checked with the GitHub CLI:

```bash
gh attestation verify ebpfsentinel-agent-amd64.tar.gz --owner ebpfsentinel
```
