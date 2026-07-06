# ebpfsentinel-release

Single trust anchor for eBPFsentinel supply-chain integrity. Centralizes
artifact signing so every published image and binary is signed, digest-
pinned, and unusable if modified — without exposing the private product
repos.

- **Consumer enforcement runbook**: [`docs/CONSUMER-ENFORCEMENT.md`](docs/CONSUMER-ENFORCEMENT.md)
- **Consumer verification**: [`policy/cosign-public.md`](policy/cosign-public.md)

## Reusable workflows

| Workflow | Purpose |
|---|---|
| [`.github/workflows/sign-image.yml`](.github/workflows/sign-image.yml) | cosign-keyless sign a pushed container image + attest SPDX SBOM |
| [`.github/workflows/sign-blob.yml`](.github/workflows/sign-blob.yml) | cosign-keyless sign release binaries/tarballs + signed `SHA256SUMS` + build provenance |

Product repos call these after their build step, e.g.:

```yaml
jobs:
  build:
    # ... docker/build-push-action with provenance: true, outputs digest ...
  sign:
    needs: build
    permissions:
      id-token: write
      packages: write
    uses: ebpfsentinel/ebpfsentinel-release/.github/workflows/sign-image.yml@v1
    with:
      image: ghcr.io/ebpfsentinel/ebpfsentinel-dashboard
      digest: ${{ needs.build.outputs.digest }}
```

## Verification

- Kubernetes: apply [`policy/kyverno-verify-images.yaml`](policy/kyverno-verify-images.yaml), or the cosign-native [`policy/policy-controller-clusterimagepolicy.yaml`](policy/policy-controller-clusterimagepolicy.yaml) (pick one).
- Bare metal: [`policy/verify.sh`](policy/verify.sh) (also shipped with each `measurements/v*` release; `OFFLINE=1` for air-gapped sites).
- License delivery (per-customer Secret): [`policy/license-external-secret.yaml`](policy/license-external-secret.yaml).
- Full runbook (admission + GitOps digest-pin + license + air-gap): [`docs/CONSUMER-ENFORCEMENT.md`](docs/CONSUMER-ENFORCEMENT.md).
- Acceptance (tamper is inert at every layer): [`policy/acceptance-tamper-test.sh`](policy/acceptance-tamper-test.sh) / [`.github/workflows/acceptance.yml`](.github/workflows/acceptance.yml).

Trust anchor: cosign keyless, issuer `token.actions.githubusercontent.com`,
identity = this repo's signing workflows on a `v*` tag. No public key to
distribute; image/blob signing needs no stored secret.
