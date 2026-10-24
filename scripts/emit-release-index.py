#!/usr/bin/env python3
"""Write the index of published releases that the customer portal vendors.

    emit-release-index.py [--releases-dir DIR] [--out FILE]

The portal shows each customer the releases they may run, what every asset is
called, the checksum it carries and the command that verifies it. It never
hosts a copy: every download link points at a release of this repository. So
what it needs is a list, and the list is derived from the manifests here rather
than typed a second time, which is how a portal ends up advertising a tarball
name the build never produced.

A release is listed once its manifest exists and it has not been yanked. Its
checksums come from `releases/<version>.sums`, the concatenation of every
`<bundle>-SHA256SUMS` the published release carries, committed with the flip to
`stable` (docs/RELEASES.md, step 7). Until that file exists each asset is
listed with no checksum, and the portal says where the signed list is instead
of inventing one.

Crate-only components are left out: a library is resolved by a dependent's
`cargo build` from the registry, and nobody downloads it from a portal.

Exit 0 = written, 1 = a manifest or a checksum file is wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SCHEMA = "ebpfsentinel.release-index/v1"
REPOSITORY = "ebpfsentinel/ebpfsentinel-release"

# The checksum file each signed blob bundle is published under, named after the
# bundle by cut-release.yml. A component with no tarball has no such file.
SUMS_FILE = {
    "ebpfsentinel": "ebpfsentinel-SHA256SUMS",
    "ebpfsentinel-enterprise": "enterprise-SHA256SUMS",
}

# The demo lab rides the agent's bundle and carries no version in its name, so
# `releases/latest/download/` resolves before anybody has picked a release.
LAB = "ebpfsentinel-demo.tar.gz"
LAB_COMPONENT = "ebpfsentinel"

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class IndexError_(Exception):
    """A manifest or a checksum file this script refuses to publish from."""


def version_key(version: str) -> tuple[int, ...]:
    """CalVer compares as numbers, so 2026.10.1 sorts after 2026.9.3."""
    return tuple(int(part) for part in version.split("."))


def read_sums(path: Path) -> dict[str, str]:
    """`<sha256>  <name>` per line, as `sha256sum` writes it."""
    sums: dict[str, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not SHA256.match(parts[0]):
            raise IndexError_(f"{path}:{number}: not a sha256sum line")
        name = parts[1].lstrip("*")
        if name in sums and sums[name] != parts[0]:
            raise IndexError_(f"{path}:{number}: {name} listed twice with two digests")
        sums[name] = parts[0]
    return sums


def images_of(component: dict) -> list[str]:
    image = component.get("image")
    if image is None:
        return []
    return [image] if isinstance(image, str) else list(image)


def files_of(component: dict) -> list[str]:
    """Every tarball the manifest declares, once per architecture."""
    names: list[str] = []
    for binary in component.get("binaries") or []:
        for arch in binary.get("arches") or []:
            name = binary["tarball"].format(version=component["version"], arch=arch)
            if name not in names:
                names.append(name)
    if component["name"] == LAB_COMPONENT:
        names.append(LAB)
    return names


def checksum(sums: dict[str, str] | None, name: str, where: Path) -> str | None:
    if sums is None:
        return None
    if name not in sums:
        raise IndexError_(f"{where}: no checksum for {name}, which the manifest declares")
    return sums[name]


def entry(manifest_path: Path) -> dict | None:
    manifest = yaml.safe_load(manifest_path.read_text())
    if manifest.get("status") == "yanked":
        return None
    version = str(manifest["release"])
    sums_path = manifest_path.with_suffix(".sums")
    sums = read_sums(sums_path) if sums_path.exists() else None

    components = []
    for component in manifest.get("components") or []:
        images = images_of(component)
        names = files_of(component)
        if not images and not names:
            continue
        components.append(
            {
                "name": component["name"],
                "version": str(component["version"]),
                "license": component["license"],
                "images": images,
                "sums": SUMS_FILE.get(component["name"]) if names else None,
                "files": [
                    {"name": name, "sha256": checksum(sums, name, sums_path)}
                    for name in names
                ],
            }
        )

    compatibility = manifest.get("compatibility") or {}
    return {
        "version": version,
        "date": str(manifest["date"]),
        "status": manifest["status"],
        "kernel_min": str(compatibility.get("kernel_min", "")),
        "kubernetes": str(compatibility.get("kubernetes", "")),
        "components": components,
    }


def build(releases_dir: Path) -> dict:
    releases = []
    for path in sorted(releases_dir.glob("*.yaml")):
        if path.name == "TEMPLATE.yaml":
            continue
        listed = entry(path)
        if listed is not None:
            releases.append(listed)
    for sums_path in releases_dir.glob("*.sums"):
        if not sums_path.with_suffix(".yaml").exists():
            raise IndexError_(f"{sums_path}: no manifest declares this release")
    releases.sort(key=lambda r: version_key(r["version"]), reverse=True)
    return {"schema": SCHEMA, "repository": REPOSITORY, "releases": releases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--releases-dir", type=Path, default=Path(__file__).parent.parent / "releases")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        index = build(args.releases_dir)
    except (IndexError_, KeyError, ValueError) as error:
        print(f"emit-release-index: {error}", file=sys.stderr)
        return 1
    text = json.dumps(index, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
