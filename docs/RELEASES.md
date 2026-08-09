# Cutting a release

Several repositories ship as one product, and **this is the only one that
publishes**. The component repositories build and sign; nothing they produce
reaches a customer until it is published from here.

That is deliberate. A customer who has to visit five repositories to assemble
one deployment has no way to tell which combination we actually tested, and a
component that publishes on its own is a component that can quietly miss the
signed inventory because nobody remembered to add it to a list.

So each release is declared once, in `releases/<version>.yaml`, and every
workflow reads it. The manifest is not documentation that can drift from
reality: if a component is not in it, it does not get built, does not get
measured, does not get signed and does not appear in the changelog.

Components carry their own versions — they ship on their own cadence, and a
single train version would force a bump on four repositories because one of
them changed. The manifest is what states which versions belong together.

## Steps

1. **Write the release notes.** Each component's notes live in
   `changelogs/<component>.md`. Rename its `## [Unreleased]` section to the
   version that component is about to ship. The product repositories carry no
   `CHANGELOG.md`; this is the source of truth.

2. **Declare the release.** Copy the template, fill it in, validate:

   ```bash
   cp releases/TEMPLATE.yaml releases/2026.6.1.yaml
   $EDITOR releases/2026.6.1.yaml
   ./scripts/check-release-manifest.py releases/2026.6.1.yaml
   ```

   The check fails if a declared component has no notes for the version it
   declares. Open it as a PR: this is the moment the release becomes real, and
   the review is a review of the whole product, not of one repo's diff.

3. **Cut it.** Run `cut-release` with the version. It dispatches each
   component's `release.yml` at the version the manifest declares, waits for
   all of them, pulls their `release-bundle` / `release-bundle-signatures`
   artifacts and publishes ONE draft release `v<version>` here, with the
   aggregated notes.

   Artifacts are pulled, not pushed: the alternative is a token with write
   access to this repository sitting in five other repositories' secrets.

   Needs `RELEASE_ORCHESTRATION_TOKEN` — a token with `actions:write` and
   `contents:read` on every component repository.

4. **Review the draft and publish it.**

5. **Issue the measurements.** Run `issue-measurements` with the same version.
   It reads the manifest and produces one signed release containing:

   | Asset | What it is |
   |---|---|
   | `measurements.signed` | dual-signed inventory of every binary sha256 and image digest |
   | `release-<version>.yaml` | the manifest itself — the compatibility matrix |
   | `CHANGELOG-<version>.md` | every component's release notes, aggregated |
   | `sboms-<version>.tar.gz` | each image's SBOM, verified against its own source repo |
   | `SHA256SUMS{,.sig,.crt}` | keyless signature covering all of the above |
   | `release-signing-*.pub` | the public keys, so air-gapped verification needs no network |

6. **Flip `status` to `stable`** when the release has soaked, in a second PR.

If one component fails to build, fix it and re-run `cut-release` with `only:
<component>` rather than rebuilding the whole set.

## What a component repository still owns

Building, testing and signing. Its `release.yml` takes the version as a
required input — it is never inferred from a tag, because these repositories
carry no release tags and any inference would restart at `.1` every month and
disagree with the manifest. Running it by hand produces the same signed
artifacts; it just does not publish them.

Everything shipped is Linux: the agent only runs there, and the console is
reached through a browser. There is no desktop client: the Tauri shell that
once wrapped the dashboard has been deleted, so there is no installer to
build, sign or measure.

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
