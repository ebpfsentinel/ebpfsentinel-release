# Component changelogs

One file per component, named after the component's `name` in
[`releases/<version>.yaml`](../releases/TEMPLATE.yaml). These files are the
source of truth: the product repositories no longer carry a `CHANGELOG.md`,
because a release note that lives next to the code is a release note that has
to be found in five places before a customer can read one story.

`issue-measurements.yml` reads them straight from the checkout to build the
aggregated `CHANGELOG-<release>.md`. Nothing is fetched over the network, so a
component whose section is missing fails the release rather than quietly
publishing an empty one.

## Rules

- Format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
  are CalVer `YYYY.M.X` and appear as `## [2026.8.1] - 2026-08-14`.
- Every component listed in a release manifest must have a section whose
  heading matches the version that manifest declares for it. `guard.sh` checks
  this, so a missing section fails the PR, not the release.
- Unreleased work accumulates under `## [Unreleased]`, which is renamed to the
  version when the release is declared.
- No story or epic identifiers. They rot, and a customer cannot resolve them.

## Where to write

A change is written here in the same pull request that declares the release,
not in the product repository. That is one extra commit against this repo per
release, and it buys a single place where the whole product's history reads in
order.
