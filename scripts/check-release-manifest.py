#!/usr/bin/env python3
"""Validate a release coordination manifest.

    check-release-manifest.py <releases/<version>.yaml> [...]
    check-release-manifest.py --images <manifest>     # emit image:tag refs, one per line
    check-release-manifest.py --binaries <manifest>   # emit repo<TAB>version<TAB>tarball<TAB>binary
    check-release-manifest.py --crates <manifest>     # emit crate<TAB>version
    check-release-manifest.py --components <manifest> # emit name<TAB>repo<TAB>version<TAB>ref

Seven repositories ship as one product. Which versions belong together is a
fact that otherwise lives only in someone's head or in a chat message, and the
first time that matters is when a customer asks "which operator works with the
agent I have?" — or when a measurements manifest quietly omits a component
nobody remembered to add.

So the release is declared once, here, and the signing workflows read it. That
also means a component missing from a release is a validation error rather
than a silent omission from the signed inventory.

The changelogs live here too (`changelogs/<name>.md`), so this script also
checks that every component the manifest declares actually has release notes
for the version it declares. A release that ships without notes for one of its
components is a release a customer cannot read, and the failure is silent
otherwise: the aggregation would simply print an empty section.

Exit 0 = valid, 1 = invalid, 2 = usage/parse error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

SCHEMA = "ebpfsentinel.release/v1"
STATUSES = {"rc", "stable", "yanked"}
ARCHES = {"amd64", "arm64"}
RELEASE_RE = re.compile(r"^\d{4}\.(?:[1-9]|1[0-2])\.\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IMAGE_RE = re.compile(r"^[a-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)+$")
CRATE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# A full commit sha, and nothing looser. The release workflows build from this
# ref, so a branch name would mean the artifacts a release published cannot be
# rebuilt from the manifest that describes them, and a tag can be moved after
# the fact. Fill it with `git rev-parse origin/main` in the component checkout.
REF_RE = re.compile(r"^[0-9a-f]{40}$")


def images_of(component: dict) -> list[str]:
    """A component may publish several images (an agent and its warden broker).

    `image:` therefore accepts a string or a list; both spellings mean the same
    thing to every consumer, which reads this helper rather than the raw field.
    """
    image = component.get("image")
    if image is None:
        return []
    if isinstance(image, str):
        return [image]
    if isinstance(image, list):
        return [str(i) for i in image]
    return []


def changelog_errors(doc: dict, changelog_dir: Path) -> list[str]:
    """Every declared component must have release notes for its version.

    Checked here rather than in the aggregation step: at aggregation time the
    release is already being signed, and the only signal a missing section
    gives is an empty heading nobody reads.
    """
    errs: list[str] = []
    for c in doc.get("components") or []:
        if not isinstance(c, dict):
            continue
        name, version = c.get("name"), c.get("version")
        if not name or not version:
            continue  # already reported by validate()
        path = changelog_dir / f"{name}.md"
        if not path.is_file():
            errs.append(f"component {name}: no changelog at {path}")
            continue
        heading = re.compile(rf"^## \[{re.escape(str(version))}\]", re.MULTILINE)
        if not heading.search(path.read_text()):
            errs.append(
                f"component {name}: {path} has no '## [{version}]' section — "
                "rename [Unreleased] when declaring the release"
            )
    return errs


def validate(doc: dict, path: Path) -> list[str]:
    errs: list[str] = []

    if doc.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}, got {doc.get('schema')!r}")

    release = str(doc.get("release", ""))
    if not RELEASE_RE.match(release):
        errs.append(f"release must be YYYY.M.X, got {release!r}")
    elif path.stem != release:
        errs.append(f"filename {path.name} does not match release {release!r}")

    if not DATE_RE.match(str(doc.get("date", ""))):
        errs.append(f"date must be YYYY-MM-DD, got {doc.get('date')!r}")

    status = doc.get("status")
    if status not in STATUSES:
        errs.append(f"status must be one of {sorted(STATUSES)}, got {status!r}")
    if status == "yanked" and not doc.get("yanked_reason"):
        # A yanked release without a stated reason forces every reader to guess
        # whether it was a build mistake or a security problem.
        errs.append("status 'yanked' requires yanked_reason")

    components = doc.get("components")
    if not isinstance(components, list) or not components:
        return errs + ["components must be a non-empty list"]

    seen: set[str] = set()
    for i, c in enumerate(components):
        where = f"components[{i}]"
        if not isinstance(c, dict):
            errs.append(f"{where}: must be a mapping")
            continue

        name = c.get("name", "")
        if not name:
            errs.append(f"{where}: missing name")
        elif not NAME_RE.match(str(name)):
            # The name selects a changelog file and an SBOM filename, so keep
            # it to something that cannot escape a directory.
            errs.append(f"{where}: name must match {NAME_RE.pattern}, got {name!r}")
        elif name in seen:
            errs.append(f"{where}: duplicate component name {name!r}")
        else:
            seen.add(name)

        where = f"component {name or i}"
        if not REPO_RE.match(str(c.get("repo", ""))):
            errs.append(f"{where}: repo must be owner/name, got {c.get('repo')!r}")
        if not c.get("version"):
            errs.append(f"{where}: missing version")
        if not c.get("license"):
            errs.append(f"{where}: missing license — it is part of what we ship")

        ref = c.get("ref")
        if not ref:
            errs.append(f"{where}: missing ref, the commit this release is built from")
        elif not REF_RE.match(str(ref)):
            errs.append(
                f"{where}: ref must be a full 40-character commit sha, got {ref!r}. "
                "A branch moves and a tag can be moved, and the build reads this."
            )

        raw_image = c.get("image")
        if raw_image is not None and not isinstance(raw_image, (str, list)):
            errs.append(f"{where}: image must be a registry path or a list of them")
        for image in images_of(c):
            if not IMAGE_RE.match(image):
                errs.append(f"{where}: image must be a tagless registry path, got {image!r}")

        binaries = c.get("binaries", [])
        if not isinstance(binaries, list):
            errs.append(f"{where}: binaries must be a list")
            binaries = []

        # A component can also ship as crates.io packages and nothing else —
        # measured from the registry's own checksum for the published version.
        crates = c.get("crates", [])
        if not isinstance(crates, list):
            errs.append(f"{where}: crates must be a list of crate names")
            crates = []
        for crate in crates:
            if not CRATE_RE.match(str(crate)):
                errs.append(f"{where}: invalid crate name {crate!r}")

        if not images_of(c) and not binaries and not crates:
            errs.append(
                f"{where}: declares neither an image, binaries nor crates — nothing to measure"
            )

        for b in binaries:
            if not isinstance(b, dict):
                errs.append(f"{where}: each binary must be a mapping")
                continue
            for field in ("name", "tarball"):
                if not b.get(field):
                    errs.append(f"{where}: binary missing {field!r}")
            tarball = str(b.get("tarball", ""))
            if tarball and ("{version}" not in tarball or "{arch}" not in tarball):
                errs.append(
                    f"{where}: binary tarball {tarball!r} must template both "
                    "{version} and {arch}"
                )
            bad = set(b.get("arches", [])) - ARCHES
            if bad:
                errs.append(f"{where}: unknown arches {sorted(bad)}")
            if not b.get("arches"):
                errs.append(f"{where}: binary {b.get('name')!r} lists no arches")

    compat = doc.get("compatibility")
    if not isinstance(compat, dict):
        errs.append("compatibility must be a mapping")
    else:
        # The kernel floor is the single most-asked deployment question and the
        # one that silently fails at load time when it is wrong.
        if not compat.get("kernel_min"):
            errs.append("compatibility.kernel_min is required")
        if not compat.get("kubernetes"):
            errs.append("compatibility.kubernetes is required")

    return errs


def load(path: Path) -> dict:
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        sys.exit(f"error: {path}: {exc}")
    if not isinstance(doc, dict):
        sys.exit(f"error: {path}: expected a mapping at the top level")
    return doc


def default_changelog_dir(manifest: Path) -> Path:
    # releases/<version>.yaml -> ../changelogs
    return manifest.resolve().parent.parent / "changelogs"


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("manifests", nargs="+", type=Path)
    ap.add_argument(
        "--changelog-dir",
        type=Path,
        default=None,
        help="where changelogs/<component>.md live (default: sibling of releases/)",
    )
    ap.add_argument(
        "--no-changelog-check",
        action="store_true",
        help="skip the per-component release-notes check",
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--images", action="store_true", help="emit image:tag refs")
    group.add_argument("--binaries", action="store_true", help="emit binary download rows")
    group.add_argument("--crates", action="store_true", help="emit crate<TAB>version rows")
    group.add_argument(
        "--components", action="store_true", help="emit name<TAB>repo<TAB>version rows"
    )
    args = ap.parse_args()

    def check(path: Path, doc: dict) -> list[str]:
        errs = validate(doc, path)
        if not args.no_changelog_check:
            errs += changelog_errors(doc, args.changelog_dir or default_changelog_dir(path))
        return errs

    emitting = args.images or args.binaries or args.crates or args.components
    if emitting:
        if len(args.manifests) != 1:
            sys.exit("error: the emitting flags take exactly one manifest")
        manifest = args.manifests[0]
        doc = load(manifest)
        errs = check(manifest, doc)
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1
        for c in doc["components"]:
            if args.components:
                print("\t".join([c["name"], c["repo"], str(c["version"]), str(c["ref"])]))
            if args.images:
                for image in images_of(c):
                    print(f"{image}:{c['version']}")
            if args.crates:
                for crate in c.get("crates", []):
                    print("\t".join([str(crate), str(c["version"])]))
            if args.binaries:
                for b in c.get("binaries", []):
                    for arch in b["arches"]:
                        tarball = b["tarball"].format(version=c["version"], arch=arch)
                        print("\t".join([c["repo"], str(c["version"]), tarball, b["name"], arch]))
        return 0

    failed = False
    for path in args.manifests:
        doc = load(path)
        errs = check(path, doc)
        if errs:
            failed = True
            print(f"release-manifest: {path} is invalid")
            for e in errs:
                print(f"  - {e}")
        else:
            print(
                f"release-manifest: {path} valid "
                f"({doc['release']}, {len(doc['components'])} components, {doc['status']})"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
