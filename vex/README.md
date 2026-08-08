# VEX statements

One file per component, named after the image basename:

```
vex/ebpfsentinel.openvex.json
vex/ebpfsentinel-enterprise.openvex.json
vex/ebpfsentinel-operator.openvex.json
vex/ebpfsentinel-dashboard.openvex.json
```

`sign-image.yml` picks up the file matching the image being signed, rewrites
every statement's `products` to the exact digest, and attaches it as an
`openvex` attestation. A component with no file simply gets no VEX
attestation — silence is the correct default.

## Why these live here and not in the product repos

A VEX statement is us telling a customer **not** to act on a scanner finding.
That is exactly the kind of assertion someone under deadline pressure will
write loosely in their own repo. Here it needs a PR against the trust anchor,
reviewed by the release owners, and it passes `scripts/check-vex.py`.

## Authoring

`products` is written as a placeholder — the workflow overwrites it with the
signed digest, so do not hand-maintain it:

```json
{
  "vulnerability": { "name": "CVE-2025-12345" },
  "products": [{ "@id": "pkg:oci/ebpfsentinel" }],
  "status": "not_affected",
  "justification": "vulnerable_code_not_in_execute_path",
  "impact_statement": "The advisory is in the crate's async runtime path; the agent only calls the blocking API, which does not reach the affected code.",
  "timestamp": "2026-08-08T00:00:00Z"
}
```

Rules the validator enforces, and the reasoning:

- **`not_affected` needs a `justification` from the OpenVEX vocabulary.** A
  scanner-facing tool has to be able to act on it; prose cannot be reasoned
  about automatically. Add `impact_statement` as well — that is what a human
  auditor reads.
- **`affected` needs an `action_statement`.** Telling a customer they are
  affected without telling them what to do leaves them worse off than a plain
  scanner report would have.

Write `under_investigation` when that is the truth. It is a real status, and
an honest one beats a `not_affected` you have not verified — that one is a
statement you will have to defend.

## Verifying as a consumer

```bash
cosign verify-attestation --type openvex \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/ebpfsentinel/ebpfsentinel-release/.github/workflows/sign-image.yml@refs/tags/v' \
  --certificate-github-workflow-repository ebpfsentinel/ebpfsentinel \
  ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest> \
  | jq -r '.payload | @base64d | fromjson | .predicate'
```
