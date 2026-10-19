# Key management

eBPFsentinel signs with four independent key pairs plus one keyless identity.
They are separate on purpose: each answers a different question, for a
different audience, and a compromise of one must not forge the other.

| Key | Signs | Answers | Held in |
|---|---|---|---|
| **Release signing** (Ed25519 + ML-DSA-65) | `measurements.json` → `measurements.signed` | "is this the artifact we published?" | `RELEASE_SIGNING_KEY_*` secrets in this repo |
| **License signing** (Ed25519 + ML-DSA-65) | customer `.lic` files, activation keys | "is this customer entitled to run it?" | private halves offline, never in this repo or any CI secret; public halves in `policy/keys/` |
| **Content signing** (Ed25519 + ML-DSA-65) | `content-manifest.json` → `content-manifest.sig` | "is this the content we published?" | `CONTENT_SIGNING_KEY_*` secrets in the private anchor, which is what cuts a bundle |
| **Content keyless** (no key) | the same `content-manifest.json` → `content-manifest.cosign.bundle` | "who published this content?" | nothing stored - Fulcio short-lived certs, identity pinned to the cutting workflow |
| **cosign keyless** (no key) | images, blobs, SBOM attestations | "is this the artifact we published?" (connected sites) | nothing stored - Fulcio short-lived certs |
| **Repository signing** (OpenPGP, Ed25519) | apt `InRelease` and `Release.gpg`, dnf `repomd.xml.asc`, every `.rpm` in the pool | "is this index the one the publisher wrote?" | `REPOSITORY_SIGNING_KEY` secret in this repo, fingerprint in the `REPOSITORY_SIGNING_FINGERPRINT` variable |

The three document pairs are dual-signed: an Ed25519 signature for today and an
ML-DSA-65 (FIPS 204) signature so a future quantum adversary cannot forge a
manifest or a license retroactively. A verifier must accept only when **both**
signatures check out.

## Why not reuse the license keys

Release measurements and licenses have different blast radii. Whoever can sign
a measurements manifest can claim a modified binary is genuine; whoever can
sign a license can mint entitlements. Reusing one pair for both means the
compromise of the CI secret - which by construction is reachable from a
workflow run - also mints licenses. Keep them apart, and keep the license keys
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
   by design - that is how customers get them.

`issue-measurements.yml` fails closed if either secret is unset or if
`policy/keys/` does not hold the matching public keys, and re-verifies every
manifest it signs against those public keys before publishing.

The enterprise agent verifies against the same public keys, compiled in.
`build-enterprise.yml` reads them through
`scripts/signing-keys.sh policy/keys release-signing` and passes them to the
binary and image builds as `RELEASE_SIGNING_KEYS`: the agent
checks its measurements manifest and its integrity manifest with them before it
unlocks a licence, and a build handed none runs the open source feature set
whatever key it is given. The script fails when either current file is missing,
so that build never leaves this pipeline.

## Generating the content signing pair

Same tool, same offline machine, a third set of filenames:

```bash
ebpfsentinel-license keygen \
  --private-key    content-signing-ed25519.key \
  --public-key     content-signing-ed25519.pub \
  --pq-private-key content-signing-mldsa.key \
  --pq-public-key  content-signing-mldsa.pub
```

Then:

1. Store the two `.key` files in the org's secret manager and an offline backup.
2. Load them as `CONTENT_SIGNING_KEY_ED25519` and `CONTENT_SIGNING_KEY_MLDSA` in
   `ebpfsentinel-private-release`, which is what cuts and signs a bundle. They
   are not loaded here: this repository publishes the public halves and signs no
   content.
3. Commit the two `.pub` files to `policy/keys/` in this repo.

Why a third pair rather than the release one: content is cut whenever a rule is
written, which is far more often than a release is built, so this key is in use
every week. A key in weekly use must not be the key that says what a binary is,
and it must not be the key that mints entitlements. Whoever holds it can make
an agent match on a pattern of their choosing, which is serious and is not the
same as being able to claim a modified binary is genuine.

The public halves are published for the same reason the licence ones are: a
bundle arrives over the portal's wire, and a key that arrived down the same wire
settles nothing. They are compiled into the enterprise agent through
`scripts/signing-keys.sh policy/keys content-signing` as `CONTENT_SIGNING_KEYS`,
shipped in every enterprise release tarball and attached to every
`measurements/v*` release. A build handed none refuses every bundle rather than
applying an unverified one, and `build-enterprise.yml` fails closed if either
file is missing.

A content manifest also carries a keyless cosign bundle over the same bytes, and
that half is **required rather than additional**: the cutting workflow verifies
it against its own pinned identity and refuses to package a bundle missing
either half, the portal serves no shelf that holds a manifest without it, and an
agent refuses a bundle whose keyless half is absent or is not a cosign bundle.
The agent does not verify that half - a Fulcio chain, a signed certificate
timestamp and a Rekor entry need a network and a trusted clock an enclave does
not have - so the pair this one does not check is kept on disk for a person to
check with cosign. The two answer different questions: this pair says the
content was signed with a key an agent carries, and the keyless half says who
asked for the signature.

## Generating the license signing pair

Same tool, same offline machine, different filenames - and unlike the release
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

`keygen` prints the pair's key id, the first sixteen hex characters of the
SHA-256 of both public halves. Every licence the pair signs carries it, and it
is the name the agent files the pair under.

Then:

1. Store the two `.key` files in the org's secret manager and an offline backup.
   They are never loaded as a repository secret here, and never reachable from a
   workflow run - that separation is the entire reason there are two pairs.
2. Commit the two `.pub` files to `policy/keys/`.
3. Compile the same public keys into the enterprise agent, which verifies a
   licence at load time and is the check that actually gates the software. The
   agent keeps each pair as raw bytes under
   `crates/enterprise-agent/keys/license/<key id>/` (`ed25519.pub.bin`,
   `ml-dsa-65.pub.bin`) and lists it in `LICENSE_KEYS`; a test fails if a
   directory is committed and not listed, or named by an id its bytes do not
   produce.

The public halves must be published, because a licence arrives over a web
session and a customer cannot authenticate it against a key that arrived down
the same wire. They are therefore attached to every `measurements/v*` release
and shipped inside every enterprise release tarball, beside the
`ebpfsentinel-license` binary that consumes them. Both `build-enterprise.yml`
and `issue-measurements.yml` fail closed if either file is missing.

## Generating the repository signing key

apt and dnf predate Sigstore and verify an index with OpenPGP: there is no way
to hand `apt-get update` a cosign bundle. The repository key exists for that
one job and signs nothing else - not a measurement, not a licence, not an
image - and nothing it signs is the only evidence of anything, since every
package it indexes is also in the release's `SHA256SUMS` and carries its own
cosign bundle.

Generate it on the same offline machine as the others, with no expiry on the
primary key and a passphrase:

```bash
gpg --quick-generate-key "eBPFsentinel package repository <release@ebpfsentinel.io>" \
  ed25519 sign never
gpg --list-keys --with-colons release@ebpfsentinel.io | awk -F: '/^fpr:/ { print $10; exit }'
gpg --armor --export-secret-keys <fingerprint> > repository-signing.asc
```

Then:

1. Load the armored private key as the repository secret
   `REPOSITORY_SIGNING_KEY` and its passphrase as
   `REPOSITORY_SIGNING_PASSPHRASE`; keep an offline backup of both.
2. Set the repository **variable** `REPOSITORY_SIGNING_FINGERPRINT` to the
   full fingerprint. `publish-package-repository.yml` refuses to run without
   it and refuses to sign with a key that does not match it, so a swapped
   secret fails the run rather than publishing an index no installed host
   accepts.
3. Publish the fingerprint in
   [`docs/PACKAGE-REPOSITORY.md`](PACKAGE-REPOSITORY.md), in the installation
   documentation and in the release notes. A host fetches the public key from
   the repository it is about to trust, which is unavoidable; the fingerprint
   published elsewhere is what makes that fetch checkable.

The public half is **not** committed to `policy/keys/`. That directory holds
raw Ed25519 and ML-DSA-65 public keys and `scripts/guard.sh` checks the length
of every file in it; an armored OpenPGP key there would fail the guard. It is
exported by the workflow and published in the repository tree it signs.

## Rotation

Rotate on a fixed schedule (yearly) and immediately on suspected compromise.

1. Generate a new pair as above; keep the old public keys in `policy/keys/`
   under a dated name (`release-signing-ed25519.2026.pub` beside
   `release-signing-mldsa.2026.pub`) so already-published manifests stay
   verifiable. The next enterprise build compiles the dated pair in beside the
   current one, so an agent already released keeps verifying the manifests
   issued for it.
2. Swap the repository secrets, replace the current `.pub` files, commit.
3. Re-issue the measurements manifest for every release still under support,
   so supported releases verify under the current key.
4. Announce the change in `policy/cosign-public.md` and in the release notes.
5. On compromise, also publish a revocation entry - see
   [`docs/REVOCATION.md`](REVOCATION.md).

Rotating the **license** pair has no repository secret to swap, and one extra
constraint: an agent already deployed carries the old public keys compiled in,
so a licence signed under the new pair is refused until that agent is upgraded.
Add the new pair to the agent under its own key id directory and keep the old
one beside it: an agent carries every pair it trusts and checks a licence
against the one it names, so both generations verify on the same build. Sign
under the new pair only for releases whose agents carry it, keep the old public
key in `policy/keys/` under its dated name and in the agent for as long as any
licence signed with it is still inside its term, and revoke rather than re-sign
if the old private half is what was compromised.

Rotating the **content** pair has the same compiled-in constraint as the
licence one and a shorter rope: an agent already deployed carries the old public
keys, and a bundle signed under the new pair is refused by it until it is
upgraded. So the new pair is published and compiled in first, bundles keep being
signed under the old one until a release carrying the new one is out, and only
then does the signing switch over. The dated copy of the old pair stays in
`policy/keys/` for as long as any bundle signed with it may still be imported
across an air gap, which is longer than it sounds: an enclave takes content in
on its own schedule. On compromise there is no grace period, because whoever
holds that key can publish a rule set of their own choosing to every estate that
fetches: swap the pair, cut a release that carries only the new one, and say so.
The keyless half rotates by itself and needs none of this, which is also what it
is worth: it names the workflow rather than a key, so the identity survives every
rotation of this pair and is the thing a reader can still check a year later.

Rotating the **repository** key is the one rotation with installed hosts on
the other end: every machine that added the repository holds the old public
key, and an index signed under a key they do not have stops their updates.
Generate the new key, add it to the keyring the hosts already trust by
publishing both keys in `ebpfsentinel.asc` for a full support cycle, swap the
secret and the fingerprint variable, republish, and only then drop the old key
from the exported keyring. Announce the new fingerprint everywhere the old one
was published. On compromise there is no grace period: swap immediately,
republish, and say so in the release notes, because an attacker holding that
key can serve a package to a host that trusts it.

The keyless (cosign) identity needs no rotation: certificates are short-lived
and the trust anchor is the workflow identity, not a key. Changing the repo,
workflow filename, or tag scheme *is* an identity change and must be treated
like a rotation - update `policy/verify.sh`, both admission policies, and
`policy/cosign-public.md` together.

## What must never happen

- A private key committed to any repository, including this one.
- The same pair signing both licenses and release measurements.
- The content pair signing anything but a content manifest, or the release or
  licence pair signing a content manifest. A key used weekly and a key that says
  what a binary is are two different exposures.
- A content bundle published with one half of its signature. Both are required,
  the cutting workflow fails on an absent half, and every reader of a bundle
  refuses one.
- A measurements release published without its public keys attached - the
  customer then has an envelope they cannot check.
- A licence delivered without the public keys being obtainable somewhere the
  customer did not get the licence from. A digest published beside a file, by
  the same system, proves nothing about who wrote the file.
- The license signing private keys loaded as a repository secret, in this repo
  or any other. They are the one pair CI must never be able to reach.
- The content signing private keys loaded as a secret in this repository. This
  is the customer's trust anchor and it publishes the public halves; the private
  ones live in the private anchor, which is what cuts a bundle.
- A reader treating the keyless half as the only signature, or as an optional
  extra. Dropping it leaves content nobody can trace to a workflow; relying on
  it alone leaves an enclave with nothing it can check at all.
- Verification code that accepts one of the two signatures when the other is
  missing or malformed.
- The repository signing key used for anything but an index and the packages
  in it. It lives in CI, so it is the most reachable key we hold, and a
  measurement or a licence signed with it would inherit that exposure.
