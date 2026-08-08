# Hardening the trust anchor

Every guarantee this repo makes reduces to one assumption: **what is on the
`v*` tags is what we put there**. Nothing in Sigstore, Kyverno or the dual
signatures protects against an attacker who can push to this repository — they
would simply sign their artifact with our identity, legitimately.

So the controls below are not hygiene. They are the actual root of trust, and
they live in GitHub settings, not in code. This document exists so they can be
*audited*: each one states what it prevents and how to check it.

`scripts/guard.sh` (run by [`guard.yml`](../.github/workflows/guard.yml) on
every PR) enforces the invariants that *are* expressible in the repo. The rest
of this page is what only a repo admin can set.

---

## 1. Branch protection on `main`

| Setting | Value | Prevents |
|---|---|---|
| Require a pull request before merging | on | direct push of a malicious workflow |
| Required approvals | ≥ 1 (2 once there is a second maintainer) | a single compromised account shipping a change |
| Require review from Code Owners | on | a change to `.github/workflows/` or `policy/` merged without the owner |
| Dismiss stale approvals on new commits | on | approve-then-swap |
| Require status checks: `guard` | on | merging with a drifted invariant |
| Require branches up to date before merging | on | a merge that silently reverts a fix |
| Require signed commits | on | commits attributed to a maintainer who did not write them |
| Require linear history | on | a merge commit smuggling unreviewed content |
| Block force pushes / deletions | on | rewriting the reviewed history |
| Include administrators | **on** | the whole table above being bypassable by the one account most worth stealing |

`Include administrators` is the one people turn off. Leave it on: an admin who
needs an exception can disable the rule deliberately, and that action is
logged.

## 2. Tag protection on `v*`

Consumers pin `…/sign-image.yml@v1`. That tag is a **mutable pointer** —
whoever can move it controls what runs inside every product repo's signing job.

Create a **ruleset** targeting tags matching `v*`:

- Restrict creations to the release owners.
- Block updates (a `v1` bump is deliberate: delete + recreate, reviewed).
- Block deletions.
- Require signed commits on the target.

```bash
gh api repos/ebpfsentinel/ebpfsentinel-release/rulesets --jq '.[] | {name, target, enforcement}'
```

The `@v1` design is a trade-off we accept: consumers get security fixes without
a PR in eight repos, at the cost of a pointer we must guard. Anyone wanting the
stricter posture can pin `@<sha>` in their own repo instead — the caller
allowlist still applies, only the published Kyverno identity regexp expects a
tag, so a SHA-pinned caller must adjust their own verification.

## 3. Environment approval on every `id-token: write` job

An OIDC token minted by this repo *is* the signing identity. Any job that can
mint one can sign anything.

Create an Environment named `release-signing`:

- **Required reviewers**: the release owners.
- **Deployment branches and tags**: `main` and `v*` only.
- Hold the `RELEASE_SIGNING_KEY_*` and `RELEASE_READ_TOKEN` secrets at the
  *environment* level, not the repository level, so a workflow run from an
  unapproved ref cannot read them.

Then reference it from the operational workflows:

```yaml
jobs:
  issue:
    environment: release-signing
```

> Note the asymmetry: the two reusable signing workflows
> (`sign-image.yml`, `sign-blob.yml`) deliberately do **not** use an
> environment — they run on behalf of a *caller* repo and a human approval on
> every product build would be unworkable. Their control is the
> `ALLOWED_CALLERS` gate plus verification-time repository pinning. The
> operational workflows (`issue-measurements`, `issue-revocations`) are
> low-frequency and human-triggered, so they take the approval.

## 4. Actions configuration

| Setting | Value | Prevents |
|---|---|---|
| Actions permissions | *Allow select actions*: this org + the SHA-pinned third parties | a typosquatted action entering via a PR |
| Fork pull request workflows | *Require approval for all outside collaborators* | a drive-by PR running code with repo context |
| Send write tokens to workflows from fork PRs | off | a fork PR obtaining a write token |
| Default `GITHUB_TOKEN` permissions | **read-only** | a workflow that forgot its `permissions:` block getting write |
| Allow GitHub Actions to create/approve PRs | off | a workflow self-approving |
| Self-hosted runners | **none** | a persistent runner retaining secrets between jobs |

Every workflow here also declares `permissions: {}` at the top level and grants
the minimum per job. Keep it that way — it is the difference between a bug in
one job and a repo-wide write.

## 5. Secrets

- Only three secrets exist: `RELEASE_SIGNING_KEY_ED25519`,
  `RELEASE_SIGNING_KEY_MLDSA`, `RELEASE_READ_TOKEN`. Image and blob signing is
  keyless and needs **no** stored secret.
- `RELEASE_READ_TOKEN` is a fine-grained token, read-only, scoped to
  `ebpfsentinel-enterprise` contents, with the shortest workable expiry. It
  exists only to download the license tool.
- License signing keys are **never** stored here or in any CI system — see
  [`KEY-MANAGEMENT.md`](KEY-MANAGEMENT.md).
- Enable **secret scanning** and **push protection** on the repo.

```bash
gh api repos/ebpfsentinel/ebpfsentinel-release --jq '.security_and_analysis'
```

## 6. Accounts and organization

- 2FA required org-wide, hardware keys or passkeys for anyone with write here.
- The release owners are the smallest set that can operate the release; review
  it whenever someone changes role.
- Org-level: block PATs with write access to this repo where possible, and
  require approval for OAuth/GitHub App installations.
- No outside collaborators. No bot with write access except Dependabot
  (which opens PRs; it does not merge them).

## 7. Dependabot

[`dependabot.yml`](../.github/dependabot.yml) opens weekly `github-actions`
PRs. SHA pinning without it means pinning to a version that stops receiving
security fixes — the pin is only safe because something proposes the moves.
Dependabot PRs go through the same review as any other; `guard.sh` re-checks
that the new pin is a SHA.

## 8. Audit

Quarterly, and after any personnel change:

```bash
# Invariants that live in the repo
./scripts/guard.sh

# Who can write, and how the branch is protected
gh api repos/ebpfsentinel/ebpfsentinel-release/collaborators --jq '.[] | {login, permissions}'
gh api repos/ebpfsentinel/ebpfsentinel-release/branches/main/protection

# What the v* tags point at, and whether anything moved
git ls-remote --tags origin 'v*'

# Signing events: every OIDC certificate we ever minted is in Rekor
cosign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/ebpfsentinel/ebpfsentinel-release/' \
  ghcr.io/ebpfsentinel/<component>:<tag>
```

The last one is the property worth internalizing: the transparency log means a
signature minted with a stolen identity **cannot be hidden**. Detection is
possible even when prevention failed — but only if someone looks.

## 9. If the identity is compromised

1. Revoke the affected digests — [`REVOCATION.md`](REVOCATION.md). This is the
   only control that stops artifacts already in the field.
2. Rotate the release signing keys — [`KEY-MANAGEMENT.md`](KEY-MANAGEMENT.md).
3. Delete and recreate `v1` from a reviewed commit; audit every workflow file
   in the range.
4. Search Rekor for signatures under our identity that do not correspond to a
   release we made, and revoke each one.
5. Publish an advisory. Customers pinning digests are unaffected by anything
   published after their pin — say so explicitly, it is the question they
   will ask.
