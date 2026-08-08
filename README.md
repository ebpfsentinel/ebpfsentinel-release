# ebpfsentinel-release

Single trust anchor for eBPFsentinel supply-chain integrity. Centralizes
artifact signing so every published image and binary is signed, digest-
pinned, and unusable if modified — without exposing the private product
repos.

- **Consumer enforcement runbook**: [`docs/CONSUMER-ENFORCEMENT.md`](docs/CONSUMER-ENFORCEMENT.md)
- **Consumer verification**: [`policy/cosign-public.md`](policy/cosign-public.md)
- **Reporting a vulnerability**: [`SECURITY.md`](SECURITY.md)
- **How this repo itself is protected**: [`docs/REPO-HARDENING.md`](docs/REPO-HARDENING.md)

## Reusable workflows

| Workflow | Purpose |
|---|---|
| [`.github/workflows/sign-image.yml`](.github/workflows/sign-image.yml) | cosign-keyless sign a pushed container image + attest SPDX SBOM |
| [`.github/workflows/sign-blob.yml`](.github/workflows/sign-blob.yml) | cosign-keyless sign release binaries/tarballs + signed `SHA256SUMS` + build provenance |
| [`.github/workflows/security-scan.yml`](.github/workflows/security-scan.yml) | advisories, licenses, dependency policy floor, secret scan ([`docs/CODE-SECURITY.md`](docs/CODE-SECURITY.md)) |

Operational workflows run from here, not from product repos:

| Workflow | Purpose |
|---|---|
| [`.github/workflows/issue-measurements.yml`](.github/workflows/issue-measurements.yml) | dual-sign the release measurements manifest (append-only) |
| [`.github/workflows/issue-revocations.yml`](.github/workflows/issue-revocations.yml) | publish the dual-signed revocation list |
| [`.github/workflows/acceptance.yml`](.github/workflows/acceptance.yml) | prove tamper is rejected at every layer |
| [`.github/workflows/guard.yml`](.github/workflows/guard.yml) | fail the PR when a repo invariant drifts ([`scripts/guard.sh`](scripts/guard.sh)) |

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
- Attestations (SBOM + recent vulnerability scan + [VEX](vex/README.md)): [`policy/kyverno-verify-attestations.yaml`](policy/kyverno-verify-attestations.yaml).
- Bare metal: [`policy/verify.sh`](policy/verify.sh) (also shipped with each `measurements/v*` release; `OFFLINE=1` for air-gapped sites).
- License delivery (per-customer Secret): [`policy/license-external-secret.yaml`](policy/license-external-secret.yaml).
- Full runbook (admission + GitOps digest-pin + license + air-gap): [`docs/CONSUMER-ENFORCEMENT.md`](docs/CONSUMER-ENFORCEMENT.md).
- Revocation (a valid signature is not a promise the artifact is still fit to run): [`policy/check-revocation.sh`](policy/check-revocation.sh), [`policy/gen-revocation-policy.sh`](policy/gen-revocation-policy.sh), [`docs/REVOCATION.md`](docs/REVOCATION.md).
- Signing keys and rotation: [`docs/KEY-MANAGEMENT.md`](docs/KEY-MANAGEMENT.md).
- Acceptance (tamper is inert at every layer): [`policy/acceptance-tamper-test.sh`](policy/acceptance-tamper-test.sh) / [`.github/workflows/acceptance.yml`](.github/workflows/acceptance.yml).

Trust anchor: cosign keyless, issuer `token.actions.githubusercontent.com`,
identity = this repo's signing workflows on a `v*` tag, **plus** the calling
repository recorded in the certificate. No public key to distribute; image/blob
signing needs no stored secret.

Because the signing workflows are reusable, the certificate subject names the
*called* workflow, not the caller — so both are enforced: an allowlist of
caller repositories at signing time, and `githubWorkflowRepository` pinning at
verification time. Verify with the subject alone and any repository calling
these public workflows would pass.
