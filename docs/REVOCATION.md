# Revocation

A signature says "we published this". It never stops saying that — not when
the artifact turns out to ship a critical CVE, not when a build machine is
found compromised. Revocation is the separate channel that says "we published
this **and you must stop running it**".

Without it the only lever is deleting the image from the registry, which does
nothing for a site that already pulled it and everything wrong for a site
trying to reproduce a past deployment.

## The list

`policy/revocations.json` is the source of truth, in git, reviewed like code.

```json
{
  "schema": "ebpfsentinel.revocations/v1",
  "serial": 7,
  "updated_at": "2026-07-01T09:12:00Z",
  "revocations": [
    {
      "kind": "image",
      "name": "ghcr.io/ebpfsentinel/ebpfsentinel",
      "digest": "sha256:<64 hex>",
      "release": "2026.6.1",
      "reason": "IPS blacklist bypass on established flows",
      "advisory": "https://github.com/ebpfsentinel/ebpfsentinel/security/advisories/GHSA-xxxx-xxxx-xxxx",
      "revoked_at": "2026-07-01T09:12:00Z"
    }
  ]
}
```

`kind` is `image` or `binary`. `digest` is the OCI index digest for images and
the sha256 of the executable for binaries — the same values the measurements
manifest records, so a revocation can always be matched against what a site
actually installed.

### serial

`serial` increments by at least one on every publish and **never goes
backwards**. It is what makes replay detectable: an adversary who can
intercept the fetch cannot simply serve yesterday's shorter list, because a
verifier that has already seen serial 7 rejects a list claiming serial 6. Cache
the highest serial you have seen; treat a lower one as an attack, not as a
stale cache.

This is also why the list is published even when it is empty — a site with no
list at all cannot tell "nothing is revoked" from "the fetch was blocked".

## Publishing

`.github/workflows/issue-revocations.yml`, run on `workflow_dispatch`:

1. validates the schema and that `serial` is strictly greater than the
   currently published one;
2. dual-signs the list with the release signing keys (Ed25519 + ML-DSA-65),
   so it verifies offline exactly like a measurements manifest;
3. cosign-keyless signs it for the transparency log;
4. replaces the `revocations/current` release, and also publishes an immutable
   `revocations/v<serial>` release so the history stays auditable.

`revocations/current` is deliberately mutable — a revocation list that could
not be updated would be useless. The immutability guarantee lives in the
per-serial tags and in the monotonic serial, not in the pointer.

## Consuming

**Bare metal.** Fetch, verify, then check a digest before installing:

```bash
gh release download revocations/current -R ebpfsentinel/ebpfsentinel-release -D rev
./verify.sh sums rev/SHA256SUMS rev/SHA256SUMS.sig rev/SHA256SUMS.crt   # provenance
ebpfsentinel-license verify-manifest \
  --input rev/revocations.signed \
  --public-key release-signing-ed25519.pub \
  --pq-public-key release-signing-mldsa.pub                              # offline path

./check-revocation.sh rev/revocations.json sha256:<digest>
```

`check-revocation.sh` exits 0 when the digest is clean, 3 when it is revoked
(printing the reason and advisory), and 2 on a malformed or stale list. Wire it
into your install path so a revoked digest fails the install rather than
producing a warning nobody reads.

**Kubernetes.** Signature verification cannot express revocation — a revoked
image still carries a valid signature. Generate a companion deny policy and
apply it alongside `kyverno-verify-images.yaml`:

```bash
./gen-revocation-policy.sh rev/revocations.json > kyverno-deny-revoked.yaml
kubectl apply -f kyverno-deny-revoked.yaml
```

Regenerate it whenever the serial advances — a GitOps job on a schedule is the
right home for this. The generated policy is a static list of digests, so it
keeps working in air-gapped clusters with no callback to us.

## Revoking something

1. Open the advisory first. The list links to it; an entry with no explanation
   gets ignored or worked around.
2. Add the entry, bump `serial`, update `updated_at`. One PR, reviewed.
3. Run `issue-revocations`.
4. Publish a fixed release and issue its measurements manifest, so sites have
   somewhere to go. Revoking without a replacement strands them.
5. If the cause is key or CI compromise rather than a code defect, rotate the
   signing keys too — see [`KEY-MANAGEMENT.md`](KEY-MANAGEMENT.md) — and revoke
   every artifact signed after the suspected compromise, not just the one that
   was found.

Entries are never removed. A digest that was unsafe stays unsafe.
