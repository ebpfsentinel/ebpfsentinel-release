# Centralized code security

Signing proves an artifact is the one we built. It says nothing about whether
what we built was safe to ship. That is this lane's job, and it is centralized
here for one reason: **a repository must not be able to lower its own bar.**

Every product repo could run `cargo audit` itself — they already do. What they
could also do is add an `ignore = ["RUSTSEC-…"]`, flip `unknown-git` to
`allow`, or delete the job, in a PR reviewed by whoever happened to be around.
With the policy here, each of those changes is a PR against the trust anchor,
gated by CODEOWNERS and the branch protection in
[`REPO-HARDENING.md`](REPO-HARDENING.md).

## What runs

Reusable workflow: [`.github/workflows/security-scan.yml`](../.github/workflows/security-scan.yml).

| Lane | Catches | Default |
|---|---|---|
| Dependency policy floor | a `deny.toml` weakened relative to central policy | always |
| `cargo audit --deny warnings` | known RUSTSEC advisories in the lockfile | always |
| `cargo deny check` | licenses, bans, sources, duplicate versions | always |
| Secret scan (gitleaks, full history) | credentials committed at any point, including ones later deleted | on |
| Dependency review | a PR *introducing* a high-severity dependency | on (PRs) |
| CodeQL | code-level vulnerability patterns | off |
| OpenSSF Scorecard | repository-posture regressions | off |

CodeQL is off by default: its Rust support is recent, and the dependency lanes
plus the repo's own `clippy -D warnings` carry more weight per minute of CI.
Turn it on per repo when you want the Security-tab findings.

Scorecard is off because it only works on public repositories, and
`scorecard-publish` is *separately* off because publishing makes the repo's
posture readable by anyone — a reasonable default for an OSS project, not one
to enable silently on a repo that just became public.

## Adopting it

In each product repo:

```yaml
# .github/workflows/security.yml
name: security
on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"   # advisories appear without anyone pushing

permissions: {}

jobs:
  scan:
    permissions:
      contents: read
      security-events: write
      pull-requests: read
    uses: ebpfsentinel/ebpfsentinel-release/.github/workflows/security-scan.yml@v1
    with:
      workspace: .
```

The weekly schedule matters more than it looks: a lockfile that was clean on
merge is not clean forever, and nothing about a quiet repository makes it safe.

## The dependency policy floor

[`configs/deny-baseline.toml`](../configs/deny-baseline.toml) defines the part
of a `deny.toml` that may not differ between workspaces, and
[`scripts/check-deny-policy.py`](../scripts/check-deny-policy.py) enforces it:

- `[graph] all-features = true` — an advisory reachable only through an
  optional feature is still an advisory.
- `[advisories] ignore` empty, unless granted below.
- `[sources] unknown-registry`/`unknown-git` = `deny`, `allow-git` empty.
- `[bans] wildcards = deny`.
- `[licenses] allow` ⊆ the approved superset.

Everything else stays per-workspace, because the license sets legitimately
differ: AGPL for OSS and the operator, `LicenseRef-Proprietary` for Enterprise
and the dashboard, Apache-2.0 for anomstream.

Run it locally exactly as CI does:

```bash
./scripts/check-deny-policy.py ../ebpfsentinel/deny.toml --workspace ebpfsentinel
```

## Exceptions

An advisory that genuinely does not apply, or an unmaintained transitive crate
waiting on an upstream bump, is granted in `[[require.exceptions]]` — in *this*
repo, with a `reason` and a mandatory `expires`:

```toml
[[require.exceptions]]
workspace = "ebpfsentinel-operator"
rule = "advisories_ignore"
value = "RUSTSEC-2025-0012"
reason = "backoff unmaintained, transitive via the kube 0.98 ecosystem; resolves on the next kube major bump"
expires = "2027-04-30"
```

Two properties are deliberate. **Expiry is enforced** — past the date the grant
stops applying and the workspace fails again, so a temporary waiver cannot
become permanent by inattention. And **granted exceptions are printed on every
successful run**, because a green check that hides what it waived is how an
exception survives for three years without anyone deciding it should.

Requesting one is a PR here. Rejecting one is a normal outcome: the alternative
to a waiver is usually a dependency bump, and that is the outcome we want.
