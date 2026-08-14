# Key management

eBPFsentinel signs with two independent key pairs plus one keyless identity.
They are separate on purpose: each answers a different question, for a
different audience, and a compromise of one must not forge the other.

| Key | Signs | Answers | Held in |
|---|---|---|---|
| **Release signing** (Ed25519 + ML-DSA-65) | `measurements.json` → `measurements.signed` | "is this the artifact we published?" | `RELEASE_SIGNING_KEY_*` secrets in this repo |
| **License signing** (Ed25519 + ML-DSA-65) | customer `.lic` files, activation keys | "is this customer entitled to run it?" | private halves offline, never in this repo or any CI secret; public halves in `policy/keys/` |
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

## Generating the license signing pair

Same tool, same offline machine, different filenames — and unlike the release
pair, the private halves are loaded nowhere in CI. They are used by the signing
process that issues customer licences, which runs on a host with no inbound
internet route.

```bash
ebpfsentinel-license keygen \
  --private-key    license-signing.key \
  --public-key     license-signing.pub \
  --pq-private-key license-signing-pq.key \
  --pq-public-key  license-signing-pq.pub
```

Then:

1. Store the two `.key` files in the org's secret manager and an offline backup.
   They are never loaded as a repository secret here, and never reachable from a
   workflow run — that separation is the entire reason there are two pairs.
2. Commit the two `.pub` files to `policy/keys/`.
3. Compile the same public keys into the enterprise agent, which verifies a
   licence at load time and is the check that actually gates the software.

The public halves must be published, because a licence arrives over a web
session and a customer cannot authenticate it against a key that arrived down
the same wire. They are therefore attached to every `measurements/v*` release
and shipped inside every enterprise release tarball, beside the
`ebpfsentinel-license` binary that consumes them. Both `build-enterprise.yml`
and `issue-measurements.yml` fail closed if either file is missing.

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

Rotating the **license** pair has no repository secret to swap, and one extra
constraint: an agent already deployed carries the old public keys compiled in,
so a licence signed under the new pair is refused until that agent is upgraded.
Sign under the new pair only for releases whose agents carry it, keep the old
public key in `policy/keys/` under its dated name for as long as any licence
signed with it is still inside its term, and revoke rather than re-sign if the
old private half is what was compromised.

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
- A licence delivered without the public keys being obtainable somewhere the
  customer did not get the licence from. A digest published beside a file, by
  the same system, proves nothing about who wrote the file.
- The license signing private keys loaded as a repository secret, in this repo
  or any other. They are the one pair CI must never be able to reach.
- Verification code that accepts one of the two signatures when the other is
  missing or malformed.
