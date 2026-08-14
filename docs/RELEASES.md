# Cutting a release

Several repositories ship as one product, and **this is the only one that
builds it**. Component repositories hold source and run their own CI; they do
not produce anything a customer can install. Every tarball, every image, every
crate version and every signature comes out of one `cut-release` run here.

That is deliberate. A customer who has to visit five repositories to assemble
one deployment has no way to tell which combination we actually tested, and a
component that publishes on its own is a component that can quietly miss the
signed inventory because nobody remembered to add it to a list. When the only
thing that can push to `ghcr.io/ebpfsentinel/*` is a release run, the signed
inventory is complete by construction rather than by discipline.

So each release is declared once, in `releases/<version>.yaml`, and every
workflow reads it. The manifest is not documentation that can drift from
reality: if a component is not in it, it does not get built, does not get
measured, does not get signed and does not appear in the changelog.

Components carry their own versions - they ship on their own cadence, and a
single train version would force a bump on four repositories because one of
them changed. The manifest is what states which versions belong together, and
`ref` is what states which commit of each one was built.

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

   Each component needs a `ref`: the full 40-character commit sha to build.
   Take it from the checkout you tested, not from a branch name, which moves:

   ```bash
   git -C ../ebpfsentinel rev-parse origin/main
   ```

   The check fails if a declared component has no notes for the version it
   declares, or if a `ref` is missing or is not a full sha. Open it as a PR:
   this is the moment the release becomes real, and the review is a review of
   the whole product, not of one repo's diff.

3. **Cut it.** Run `cut-release` with the version. It reads the manifest, then
   calls one build workflow per component - `build-ebpfsentinel`,
   `build-enterprise`, `build-operator`, `build-dashboard`, `build-anomstream`.
   Each checks its component out at the pinned `ref`, compiles it, pushes and
   signs its images, and uploads its tarballs as run artifacts. The final
   `publish` job checks that every binary and every image the manifest declares
   actually exists, then creates ONE draft release `v<version>` here with the
   aggregated notes.

   The build workflows are *called*, not dispatched, so everything happens in a
   single run: artifacts are already in scope, there is nothing to poll for and
   no token with write access to this repository sitting in another repo's
   secrets.

   `dry-run` compiles everything and pushes none of it - no image, no crate, no
   release. Use it to prove a manifest builds before the version numbers become
   permanent.

4. **Review the draft and publish it.**

5. **Issue the measurements.** Run `issue-measurements` with the same version.
   It reads the manifest and produces one signed release containing:

   | Asset | What it is |
   |---|---|
   | `measurements.signed` | dual-signed inventory of every binary sha256 and image digest |
   | `release-<version>.yaml` | the manifest itself - the compatibility matrix |
   | `CHANGELOG-<version>.md` | every component's release notes, aggregated |
   | `sboms-<version>.tar.gz` | each image's SBOM, verified against the signing identity |
   | `SHA256SUMS{,.sig,.crt}` | keyless signature covering all of the above |
   | `release-signing-*.pub` | the public keys, so air-gapped verification needs no network |
   | `license-signing*.pub` | the other pair, the one that says a customer `.lic` is ours |

6. **Flip `status` to `stable`** when the release has soaked, in a second PR.

If one component fails to build, fix it, update its `ref` in the manifest, and
re-run `cut-release` with `only: <component>` rather than rebuilding the whole
set.

## One-time prerequisites

| What | Where | Why |
|---|---|---|
| `COMPONENT_CHECKOUT_TOKEN` | repository secret here | a fine-grained PAT with `contents: read` on the five component repositories. `GITHUB_TOKEN` cannot read another repository, and enterprise and dashboard are private. |
| GHCR package access | each package's settings | add `ebpfsentinel-release` under *Manage Actions access* with the **Write** role, for every image and chart. That is what lets this repository's `GITHUB_TOKEN` push them. |
| `crates-io` environment | repository environments here | holds `CARGO_REGISTRY_TOKEN` for the anomstream publish, and is where a required-reviewer gate goes if you want one. A publish cannot be undone, only yanked. |

## What a component repository still owns

Source, tests and CI. `ci.yml` runs the gates on every change; `docker.yml`
builds the images with `push: false` so a broken Dockerfile fails in the pull
request that broke it. Neither publishes anything, and neither knows what
version it is: versions live in the manifest, and the release run stamps them
into the tree it checked out.

Everything shipped is Linux: the agent only runs there, and the console is
reached through a browser. There is no desktop client: the Tauri shell that
once wrapped the dashboard has been deleted, so there is no installer to
build, sign or measure.

## Status

`rc` -> `stable` -> possibly `yanked`.

Marking a release `yanked` makes `issue-measurements` refuse to run for it: a
signed statement of "here is what we shipped" is exactly what you do not want
to publish for something you have withdrawn.

Yanking a manifest is **not** the same as revoking the artifacts. The manifest
governs our publishing; a customer already running the images is unaffected by
it. Stopping those requires the revocation list - [`REVOCATION.md`](REVOCATION.md).
Do both, in that order.

## Compatibility

`kernel_min` and `kubernetes` are required because they are the two questions
every deployment asks and the two failures that surface late - a kernel too old
fails at eBPF load time, in production, on the node.

Record `breaking_changes` even when the list feels obvious. It is what a
customer reads to decide whether the upgrade is safe, and "we assumed they'd
know" is not a plan.

## Why it all lives here

The build steps could live in each component repository, and they used to. They
moved because a release is a statement about a set of artifacts, and that
statement is only worth something if nothing outside it can add to the set.
With the build here, the pinned `ref` in the manifest is the only input, the
signing identity has exactly one authorized caller, and the changelog, the SBOM
aggregation and the measurements manifest all describe the same run that
produced the artifacts.
