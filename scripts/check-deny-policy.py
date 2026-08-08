#!/usr/bin/env python3
"""Check a workspace's deny.toml against the central policy floor.

    check-deny-policy.py <deny.toml> [--baseline configs/deny-baseline.toml]
                                     [--workspace <name>]

cargo-deny already fails a build that violates the config it was given. What it
cannot notice is the config itself being weakened — an added `ignore = [...]`,
a flipped `unknown-git`, a license quietly appended. That is the drift this
catches, and it is the drift an attacker with a merged PR would rely on.

Exit 0 = compliant, 1 = violation, 2 = usage/parse error.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import date
from pathlib import Path


def load(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        sys.exit(f"error: {path} not found")
    except tomllib.TOMLDecodeError as exc:
        sys.exit(f"error: {path} is not valid TOML: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("deny", type=Path)
    ap.add_argument(
        "--baseline",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "configs" / "deny-baseline.toml",
    )
    ap.add_argument("--workspace", default="")
    args = ap.parse_args()

    cfg = load(args.deny)
    req = load(args.baseline).get("require", {})
    if not req:
        sys.exit(f"error: {args.baseline} has no [require] section")

    ws = args.workspace or args.deny.resolve().parent.name
    violations: list[str] = []

    # An exception without an expiry is a silent policy change, so `expires` is
    # mandatory and enforced — a lapsed grant simply stops applying.
    today = date.today()
    granted: dict[tuple[str, str, str], str] = {}
    for e in req.get("exceptions", []):
        key = (e.get("workspace", ""), e.get("rule", ""), str(e.get("value", "")))
        raw = e.get("expires")
        if not raw or not e.get("reason"):
            violations.append(f"baseline exception {key} must carry both `reason` and `expires`")
            continue
        try:
            expires = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        except ValueError:
            violations.append(f"baseline exception {key} has an unparseable expires {raw!r}")
            continue
        if expires < today:
            continue  # lapsed: no longer grants anything
        granted[key] = str(expires)

    def excepted(rule: str, value: str = "") -> bool:
        return (ws, rule, value) in granted

    if req.get("graph_all_features") and cfg.get("graph", {}).get("all-features") is not True:
        violations.append("[graph] all-features must be true — features hide advisories")

    advisories = cfg.get("advisories", {})
    ignored = advisories.get("ignore", [])
    if req.get("advisories_ignore_must_be_empty"):
        for entry in ignored:
            ident = entry if isinstance(entry, str) else str(entry.get("id", entry))
            if not excepted("advisories_ignore", ident):
                violations.append(
                    f"[advisories] ignore contains {ident!r} with no exception granted in "
                    f"{args.baseline.name}"
                )

    sources = cfg.get("sources", {})
    for key, field in (("sources_unknown_registry", "unknown-registry"),
                       ("sources_unknown_git", "unknown-git")):
        want = req.get(key)
        if want and sources.get(field) != want:
            violations.append(
                f"[sources] {field} is {sources.get(field)!r}, policy requires {want!r}"
            )
    if req.get("allow_git_must_be_empty"):
        for url in sources.get("allow-git", []):
            if not excepted("allow_git", url):
                violations.append(f"[sources] allow-git contains {url!r} with no exception granted")

    want_wildcards = req.get("bans_wildcards")
    if want_wildcards and cfg.get("bans", {}).get("wildcards") != want_wildcards:
        violations.append(
            f"[bans] wildcards is {cfg.get('bans', {}).get('wildcards')!r}, "
            f"policy requires {want_wildcards!r}"
        )

    superset = set(req.get("licenses_allow_superset", []))
    if superset:
        for lic in cfg.get("licenses", {}).get("allow", []):
            if lic not in superset and not excepted("license", lic):
                violations.append(
                    f"[licenses] allow contains {lic!r}, which is not in the approved superset"
                )

    if violations:
        print(f"deny-policy: {args.deny} violates the central floor ({ws})")
        for v in violations:
            print(f"  - {v}")
        print(f"\nEither fix the config, or request an exception in {args.baseline}.")
        return 1

    print(f"deny-policy: {args.deny} complies with the central floor ({ws})")
    # Surface what was waived — a passing check that hides its exceptions is
    # how a temporary grant becomes permanent.
    mine = {k: v for k, v in granted.items() if k[0] == ws}
    for (_, rule, value), expires in sorted(mine.items()):
        print(f"  waived: {rule} {value} (expires {expires})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
