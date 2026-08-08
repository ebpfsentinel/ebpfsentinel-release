# Coordinating a release across seven repositories

Seven repos ship as one product. Which versions belong together is a fact, and
until it is written down it lives in someone's memory — which is where it is
when a customer asks "does operator 2026.6.1 work with the agent I installed in
March?", and where it was when a component quietly missed the signed inventory
because nobody remembered to add it to a list.

So each release is declared once, in `releases/<version>.yaml`, and the signing
workflow reads it. That is the important property: the manifest is not
documentation that can drift from reality. If a component is not in it, it does
not get measured, does not get signed, and does not appear in the changelog.

## Cutting a release

1. **Release each component** from its own repo. Each build calls
   `sign-image.yml` / `sign-blob.yml`, so artifacts are signed as they are
   published.

2. **Declare the release here.** Copy the template, fill it in, validate:

   ```bash
   cp releases/TEMPLATE.yaml releases/2026.6.1.yaml
   $EDITOR releases/2026.6.1.yaml
   ./scripts/check-release-manifest.py releases/2026.6.1.yaml
   ```

   Open it as a PR. This is the moment the release becomes real, and the
   review is a review of the whole product, not of one repo's diff.

3. **Issue the measurements.** Run `issue-measurements` with the version. It
   reads the manifest and produces one signed release containing:

   | Asset | What it is |
   |---|---|
   | `measurements.signed` | dual-signed inventory of every binary sha256 and image digest |
   | `release-<version>.yaml` | the manifest itself — the compatibility matrix |
   | `CHANGELOG-<version>.md` | every component's release notes, aggregated |
   | `sboms-<version>.tar.gz` | each image's SBOM, verified against its own source repo |
   | `SHA256SUMS{,.sig,.crt}` | keyless signature covering all of the above |
   | `release-signing-*.pub` | the public keys, so air-gapped verification needs no network |

4. **Flip `status` to `stable`** when the release has soaked, in a second PR.

## Status

`rc` → `stable` → possibly `yanked`.

Marking a release `yanked` makes `issue-measurements` refuse to run for it: a
signed statement of "here is what we shipped" is exactly what you do not want
to publish for something you have withdrawn.

Yanking a manifest is **not** the same as revoking the artifacts. The manifest
governs our publishing; a customer already running the images is unaffected by
it. Stopping those requires the revocation list — [`REVOCATION.md`](REVOCATION.md).
Do both, in that order.

## Compatibility

`kernel_min` and `kubernetes` are required because they are the two questions
every deployment asks and the two failures that surface late — a kernel too old
fails at eBPF load time, in production, on the node.

Record `breaking_changes` even when the list feels obvious. It is what a
customer reads to decide whether the upgrade is safe, and "we assumed they'd
know" is not a plan.

## Why the aggregation lives here

The changelog and SBOM aggregation could run in any repo. They run here because
this is the only place that knows the full component set, and because the SBOM
aggregation *verifies* each attestation against that component's own source
repository before including it — using the `repo` field from the manifest as
the pin. An SBOM collected without that check would be a convenient bundle of
unverified claims.
