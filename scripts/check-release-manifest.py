#!/usr/bin/env python3
"""Validate a release coordination manifest.

    check-release-manifest.py <releases/<version>.yaml> [...]
    check-release-manifest.py --images <manifest>     # emit image:tag refs, one per line
    check-release-manifest.py --binaries <manifest>   # emit repo<TAB>version<TAB>tarball<TAB>binary

Seven repositories ship as one product. Which versions belong together is a
fact that otherwise lives only in someone's head or in a chat message, and the
first time that matters is when a customer asks "which operator works with the
agent I have?" — or when a measurements manifest quietly omits a component
nobody remembered to add.

So the release is declared once, here, and the signing workflows read it. That
also means a component missing from a release is a validation error rather
than a silent omission from the signed inventory.

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

        image = c.get("image")
        if image and not IMAGE_RE.match(str(image)):
            errs.append(f"{where}: image must be a tagless registry path, got {image!r}")

        binaries = c.get("binaries", [])
        if not isinstance(binaries, list):
            errs.append(f"{where}: binaries must be a list")
            binaries = []
        if not image and not binaries:
            errs.append(f"{where}: declares neither an image nor binaries — nothing to measure")

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


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("manifests", nargs="+", type=Path)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--images", action="store_true", help="emit image:tag refs")
    group.add_argument("--binaries", action="store_true", help="emit binary download rows")
    args = ap.parse_args()

    if args.images or args.binaries:
        if len(args.manifests) != 1:
            sys.exit("error: --images/--binaries take exactly one manifest")
        doc = load(args.manifests[0])
        errs = validate(doc, args.manifests[0])
        if errs:
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1
        for c in doc["components"]:
            if args.images and c.get("image"):
                print(f"{c['image']}:{c['version']}")
            if args.binaries:
                for b in c.get("binaries", []):
                    for arch in b["arches"]:
                        tarball = b["tarball"].format(version=c["version"], arch=arch)
                        print("\t".join([c["repo"], str(c["version"]), tarball, b["name"], arch]))
        return 0

    failed = False
    for path in args.manifests:
        errs = validate(load(path), path)
        if errs:
            failed = True
            print(f"release-manifest: {path} is invalid")
            for e in errs:
                print(f"  - {e}")
        else:
            doc = load(path)
            print(
                f"release-manifest: {path} valid "
                f"({doc['release']}, {len(doc['components'])} components, {doc['status']})"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
