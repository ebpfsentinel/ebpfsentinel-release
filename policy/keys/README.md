# Signing public keys

The public halves of the two signing pairs. Public by design - this directory
is how customers obtain the keys that verify what we hand them (and, at
air-gapped sites, the only trust material they need).

Two pairs, because they answer different questions and a compromise of one must
not forge the other. See [`../../docs/KEY-MANAGEMENT.md`](../../docs/KEY-MANAGEMENT.md).

## Release signing

| File | Algorithm | Verifies |
|---|---|---|
| `release-signing-ed25519.pub` | Ed25519 | `measurements.signed` (classical signature) |
| `release-signing-mldsa.pub` | ML-DSA-65 (FIPS 204) | `measurements.signed` (post-quantum signature) |

Both must verify. A manifest that satisfies only one is not valid.

```bash
ebpfsentinel-license verify-manifest \
  --input measurements.signed \
  --public-key release-signing-ed25519.pub \
  --pq-public-key release-signing-mldsa.pub
```

Every `measurements/v*` release attaches copies of these files, so a customer
verifying offline does not need to fetch this repo.

The enterprise agent carries them too. `build-enterprise.yml` reads this pair,
and every superseded pair still here, through `scripts/release-signing-keys.sh`
and compiles them into the agent, which verifies its measurements manifest and
its integrity manifest against them before it unlocks a licence. The script
fails when either current file is missing, so a release cannot build an agent
that never unlocks.

## License signing

| File | Algorithm | Verifies |
|---|---|---|
| `license-signing.pub` | Ed25519 | a customer `.lic` file (classical signature) |
| `license-signing-pq.pub` | ML-DSA-65 (FIPS 204) | a customer `.lic` file (post-quantum signature) |

Same rule: both must verify.

A pair is named by its key id, the first sixteen hex characters of the SHA-256
of both public halves. `ebpfsentinel-license keygen` prints it, every licence
signed since keys were named carries it, and `inspect` shows it as
`Signing key`. The agent carries each pair it trusts under that id, so a
licence is checked against the pair it names and a refusal says which pair the
build lacks.

```bash
ebpfsentinel-license inspect ebpfsentinel-<org>.lic \
  --public-key license-signing.pub \
  --pq-public-key license-signing-pq.pub
```

A licence is delivered over a web session, and a checksum published by the same
system that published the file proves nothing against somebody who controls
that system. So the keys that settle it deliberately do not travel down that
wire: they ship in every enterprise release tarball, beside the
`ebpfsentinel-license` binary that consumes them, and are attached to every
`measurements/v*` release. Obtained once, out of band, and kept.

The same two keys verify an offline bundle - the set of keys and revocations an
estate with no route to us carries across an air gap:

```bash
ebpfsentinel-license bundle offline-bundle.json \
  --public-key license-signing.pub \
  --pq-public-key license-signing-pq.pub
```

The private halves are generated and held offline and never enter this
repository or any CI secret, which is what keeps a workflow compromise from
minting entitlements.

## Populating and rotating

**Not yet populated.** `issue-measurements.yml` and `build-enterprise.yml` fail
closed until the real public keys are committed here - a release that shipped an
envelope customers cannot check is worse than no release. Generate each pair
offline and commit only the `.pub` files; the procedure and the rotation
schedule are in
[`../../docs/KEY-MANAGEMENT.md`](../../docs/KEY-MANAGEMENT.md).

Superseded keys stay in this directory under a dated name
(`release-signing-ed25519.<year>.pub`, `license-signing.<year>.pub`) so
documents signed before a rotation remain verifiable.

`scripts/guard.sh` decodes every `.pub` here and checks its length against the
algorithm the filename declares, so a truncated file or a pair committed under
swapped names fails the pull request rather than an air-gapped install.
