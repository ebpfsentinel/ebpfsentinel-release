# Security policy

This repository is the **trust anchor** for eBPFsentinel: it holds the signing
identity used for every published image and binary, the policies customers
enforce with, and the revocation list. A compromise here is a compromise of
every artifact we ship. Treat findings against it as high severity by default.

## Reporting a vulnerability

Report privately — do not open a public issue.

- GitHub **Security Advisories** → *Report a vulnerability* on this repository
  (preferred; gives us a private fork to develop the fix in).
- Or email **security@ebpfsentinel.io**.

Include: what you found, how to reproduce it, the affected repository/tag or
image digest, and the impact you believe it has. If you have a proof of
concept, send it — it shortens triage considerably.

We acknowledge within **3 business days** and give an initial assessment
within **10 business days**. We will tell you what we decided and why, even
when the answer is "not a vulnerability".

## Disclosure

Coordinated. We ask for **90 days** before public disclosure, or until a fixed
release is available if that comes sooner. If a vulnerability is being
actively exploited we will move faster and say so. We credit reporters in the
advisory unless you prefer otherwise.

## Scope

In scope, and what we consider a valid finding:

- Any way to obtain a signature under our release identity without a build in
  an authorized repository — the caller allowlist in the signing workflows, or
  a bypass of `githubWorkflowRepository` pinning at verification time.
- Any way to make `policy/verify.sh`, the Kyverno policy, the Policy
  Controller policy, or `policy/check-revocation.sh` accept a tampered,
  unsigned, or **revoked** artifact.
- Replay or downgrade of the revocation list (serving an older serial).
- Injection into the reusable workflows through their `workflow_call` inputs.
- Secret exposure through workflow logs, artifacts, or release assets.
- Weaknesses in the dual-signature scheme (Ed25519 + ML-DSA-65) as used here.

Out of scope:

- Vulnerabilities in the product itself — report those against the product
  repository, or here if you cannot determine which one.
- Findings that require an attacker to already hold repository admin, an
  organization owner account, or our signing secrets.
- Reports from automated scanners with no demonstrated impact.
- The absence of a signature on artifacts we never claimed to sign.

## Verifying what you received

Before reporting that an artifact looks wrong, confirm it is one of ours:

```bash
./policy/verify.sh image ghcr.io/ebpfsentinel/<component>@sha256:<digest>
```

An artifact that fails verification is not an eBPFsentinel artifact — but we
still want to hear about it, because it means someone is distributing one.

## Hardening of this repository

The controls protecting the signing identity, and how to audit that they are
in place, are documented in [`docs/REPO-HARDENING.md`](docs/REPO-HARDENING.md).
Key handling is in [`docs/KEY-MANAGEMENT.md`](docs/KEY-MANAGEMENT.md).
