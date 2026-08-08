#!/usr/bin/env python3
"""Validate an OpenVEX document before it is signed.

    check-vex.py <doc.openvex.json> [<doc.openvex.json> ...]

A VEX statement is an assertion a customer will use to *stop* investigating a
CVE. A malformed or unjustified one is worse than no statement at all, so the
rules that matter are enforced here rather than trusted to review:

  - `not_affected` requires a machine-readable `justification` from the
    OpenVEX vocabulary; prose alone is not actionable.
  - `affected` requires an `action_statement` — telling someone they are
    affected without telling them what to do is an unfinished thought.
  - every statement names at least one vulnerability and one product.

Exit 0 = valid, 1 = invalid, 2 = usage/parse error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONTEXT = "https://openvex.dev/ns"
STATUSES = {"not_affected", "affected", "fixed", "under_investigation"}
# https://github.com/openvex/spec — the closed vocabulary is the point: a
# free-text reason cannot be reasoned about by a tool.
JUSTIFICATIONS = {
    "component_not_present",
    "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
}


def check(path: Path) -> list[str]:
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: not readable as JSON: {exc}"]

    errs: list[str] = []
    ctx = doc.get("@context", "")
    if not str(ctx).startswith(CONTEXT):
        errs.append(f"@context must start with {CONTEXT}, got {ctx!r}")
    for field in ("@id", "author", "timestamp", "version"):
        if not doc.get(field):
            errs.append(f"missing required document field {field!r}")

    statements = doc.get("statements")
    if not isinstance(statements, list):
        return errs + ["`statements` must be a list"]

    for i, st in enumerate(statements):
        where = f"statements[{i}]"
        vuln = st.get("vulnerability") or {}
        name = vuln.get("name") if isinstance(vuln, dict) else vuln
        if not name:
            errs.append(f"{where}: no vulnerability name")
        if not st.get("products"):
            errs.append(f"{where}: no products")

        status = st.get("status")
        if status not in STATUSES:
            errs.append(f"{where}: status {status!r} is not one of {sorted(STATUSES)}")
            continue

        if status == "not_affected":
            just = st.get("justification")
            if just not in JUSTIFICATIONS:
                errs.append(
                    f"{where}: not_affected needs a justification from the OpenVEX "
                    f"vocabulary, got {just!r}"
                )
            if not st.get("impact_statement") and not just:
                errs.append(f"{where}: not_affected with neither justification nor impact_statement")
        elif status == "affected" and not st.get("action_statement"):
            errs.append(f"{where}: affected requires an action_statement")

    return errs


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print(__doc__)
        return 2

    failed = False
    for path in paths:
        errs = check(path)
        if errs:
            failed = True
            print(f"vex: {path} is invalid")
            for e in errs:
                print(f"  - {e}")
        else:
            n = len(json.loads(path.read_text()).get("statements", []))
            print(f"vex: {path} valid ({n} statement{'s' if n != 1 else ''})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
