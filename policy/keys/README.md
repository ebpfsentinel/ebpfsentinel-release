# Release signing public keys

The public half of the release signing pair. Public by design — this directory
is how customers obtain the keys that verify a signed measurements manifest
(and, at air-gapped sites, the only trust material they need).

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

**Not yet populated.** `issue-measurements.yml` fails closed until the real
public keys are committed here. Generate the pair offline and commit only the
`.pub` files — see [`../../docs/KEY-MANAGEMENT.md`](../../docs/KEY-MANAGEMENT.md).

Superseded keys stay in this directory under a dated name
(`release-signing-ed25519.<year>.pub`) so manifests signed before a rotation
remain verifiable.
