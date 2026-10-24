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

Each component also carries the notes of its version, lifted from
`changelogs/<name>.md` by the same reader `aggregate-changelog.py` uses and
sorted into what a customer weighs before an upgrade: security, features and
fixes. A group heading nobody mapped fails the index rather than dropping its
entries, and the notes go out as plain text, so the portal renders no markdown
it was handed. The release's own `breaking_changes` travel beside them as its
upgrade notes, which is the one thing a reader must not miss between two
versions.

Exit 0 = written, 1 = a manifest or a checksum file is wrong.
"""

from __future__ import annotations

import argparse
import importlib.util
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

# Where a Keep a Changelog group lands. Matched on the heading's first word,
# so `### Added - \`crate\`` sorts like `### Added`.
GROUPS = {
    "Added": "features",
    "Changed": "features",
    "Deprecated": "features",
    "Removed": "features",
    "Performance": "features",
    "Fixed": "fixes",
    "Security": "security",
}

INLINE = (
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
)


def _changelog_reader():
    """The section reader the aggregated changelog is built with, not a copy of it."""
    path = Path(__file__).with_name("aggregate-changelog.py")
    spec = importlib.util.spec_from_file_location("aggregate_changelog", path)
    if spec is None or spec.loader is None:
        raise IndexError_(f"{path}: cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.section


section = _changelog_reader()


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


def plain_text(markdown: str) -> str:
    """One line a screen prints as text: links, emphasis and code marks removed."""
    text = " ".join(markdown.split())
    for pattern, replacement in INLINE:
        text = pattern.sub(replacement, text)
    return text


def notes(body: str, where: str) -> dict[str, list[dict]]:
    """A changelog section, as entries sorted by what a reader weighs them for."""
    grouped: dict[str, list[dict]] = {"security": [], "features": [], "fixes": []}
    group: str | None = None
    topic: str | None = None
    current: list[str] | None = None

    def close() -> None:
        if current is not None and group is not None:
            grouped[group].append({"topic": topic, "text": plain_text(" ".join(current))})

    for line in body.splitlines():
        if line.startswith("### "):
            close()
            current = None
            word = line[4:].split()[0] if line[4:].split() else ""
            if word not in GROUPS:
                raise IndexError_(f"{where}: no group for the heading {line.strip()!r}")
            group, topic = GROUPS[word], None
        elif line.startswith("#### "):
            close()
            current = None
            topic = plain_text(line[5:])
        elif line.startswith("- "):
            close()
            if group is None:
                raise IndexError_(f"{where}: an entry sits under no group")
            current = [line[2:]]
        elif line.strip() and current is not None and line[:1].isspace():
            current.append(line.strip())
        elif line.strip():
            close()
            current = None
    close()
    return grouped


def changes(changelog_dir: Path, name: str, version: str) -> dict[str, list[dict]]:
    path = changelog_dir / f"{name}.md"
    body = section(path.read_text(), version) if path.is_file() else None
    if body is None:
        raise IndexError_(f"{path}: no section for {version}, which a manifest declares")
    return notes(body, f"{path} [{version}]")


def checksum(sums: dict[str, str] | None, name: str, where: Path) -> str | None:
    if sums is None:
        return None
    if name not in sums:
        raise IndexError_(f"{where}: no checksum for {name}, which the manifest declares")
    return sums[name]


def entry(manifest_path: Path, changelog_dir: Path) -> dict | None:
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
                "changes": changes(changelog_dir, component["name"], str(component["version"])),
            }
        )

    compatibility = manifest.get("compatibility") or {}
    return {
        "version": version,
        "date": str(manifest["date"]),
        "status": manifest["status"],
        "kernel_min": str(compatibility.get("kernel_min", "")),
        "kubernetes": str(compatibility.get("kubernetes", "")),
        "breaking_changes": [plain_text(str(item)) for item in manifest.get("breaking_changes") or []],
        "components": components,
    }


def build(releases_dir: Path, changelog_dir: Path) -> dict:
    releases = []
    for path in sorted(releases_dir.glob("*.yaml")):
        if path.name == "TEMPLATE.yaml":
            continue
        listed = entry(path, changelog_dir)
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
    parser.add_argument("--changelog-dir", type=Path, default=Path(__file__).parent.parent / "changelogs")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        index = build(args.releases_dir, args.changelog_dir)
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
