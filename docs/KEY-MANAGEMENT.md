# Key management

eBPFsentinel signs with two independent key pairs plus one keyless identity.
They are separate on purpose: each answers a different question, for a
different audience, and a compromise of one must not forge the other.

| Key | Signs | Answers | Held in |
|---|---|---|---|
| **Release signing** (Ed25519 + ML-DSA-65) | `measurements.json` → `measurements.signed` | "is this the artifact we published?" | `RELEASE_SIGNING_KEY_*` secrets in this repo |
| **License signing** (Ed25519 + ML-DSA-65) | customer `.lic` files, activation keys | "is this customer entitled to run it?" | offline, in the enterprise release process — never in this repo |
| **cosign keyless** (no key) | images, blobs, SBOM attestations | "is this the artifact we published?" (connected sites) | nothing stored — Fulcio short-lived certs |

Both key-based pairs are dual-signed: an Ed25519 signature for today and an
ML-DSA-65 (FIPS 204) signature so a future quantum adversary cannot forge a
manifest or a license retroactively. A verifier must accept only when **both**
signatures check out.

## Why not reuse the license keys

Release measurements and licenses have different blast radii. Whoever can sign
a measurements manifest can claim a modified binary is genuine; whoever can
sign a license can mint entitlements. Reusing one pair for both means the
compromise of the CI secret — which by construction is reachable from a
workflow run — also mints licenses. Keep them apart, and keep the license keys
out of CI entirely.

## Generating the release signing pair

Run this **offline**, on a machine that does not have the private keys of any
other role, using the `ebpfsentinel-license` tool from an enterprise release:

```bash
ebpfsentinel-license keygen \
  --private-key    release-signing-ed25519.key \
  --public-key     release-signing-ed25519.pub \
  --pq-private-key release-signing-mldsa.key \
  --pq-public-key  release-signing-mldsa.pub
```

Then:

1. Store the two `.key` files in the org's secret manager (and an offline
   backup). They never touch a developer laptop's working tree.
2. Load them as repository secrets `RELEASE_SIGNING_KEY_ED25519` and
   `RELEASE_SIGNING_KEY_MLDSA` (file *contents*).
3. Commit the two `.pub` files to `policy/keys/` in this repo. They are public
   by design — that is how customers get them.

`issue-measurements.yml` fails closed if either secret is unset or if
`policy/keys/` does not hold the matching public keys, and re-verifies every
manifest it signs against those public keys before publishing.

## Rotation

Rotate on a fixed schedule (yearly) and immediately on suspected compromise.

1. Generate a new pair as above; keep the old public keys in `policy/keys/`
   under a dated name (`release-signing-ed25519.2026.pub`) so already-published
   manifests stay verifiable.
2. Swap the repository secrets, replace the current `.pub` files, commit.
3. Re-issue the measurements manifest for every release still under support,
   so supported releases verify under the current key.
4. Announce the change in `policy/cosign-public.md` and in the release notes.
5. On compromise, also publish a revocation entry — see
   [`docs/REVOCATION.md`](REVOCATION.md).

The keyless (cosign) identity needs no rotation: certificates are short-lived
and the trust anchor is the workflow identity, not a key. Changing the repo,
workflow filename, or tag scheme *is* an identity change and must be treated
like a rotation — update `policy/verify.sh`, both admission policies, and
`policy/cosign-public.md` together.

## What must never happen

- A private key committed to any repository, including this one.
- The same pair signing both licenses and release measurements.
- A measurements release published without its public keys attached — the
  customer then has an envelope they cannot check.
- Verification code that accepts one of the two signatures when the other is
  missing or malformed.
