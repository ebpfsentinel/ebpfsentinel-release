#!/usr/bin/env bash
# Check a digest against the eBPFsentinel revocation list.
#
#   check-revocation.sh <revocations.json> <sha256:digest> [<sha256:digest>...]
#
# Exit codes:
#   0  every digest is clean
#   2  the list is malformed, or older than one already seen (replay)
#   3  at least one digest is revoked
#
# Verify the list's signature BEFORE trusting it (see docs/REVOCATION.md);
# this script checks content, not provenance.
#
# Replay protection: the highest serial seen is remembered in
# ${XDG_STATE_HOME:-$HOME/.local/state}/ebpfsentinel/revocation-serial, and a
# list with a lower serial is rejected. Override with SERIAL_STATE=/path, or
# SERIAL_STATE=/dev/null to disable (not recommended — an attacker who can
# replace the file you fetch can then serve an older, shorter list).
set -euo pipefail

LIST="${1:-}"
shift || true
if [ -z "$LIST" ] || [ "$#" -eq 0 ]; then
  echo "usage: $0 <revocations.json> <sha256:digest>..." >&2
  exit 2
fi
if [ ! -r "$LIST" ]; then
  echo "ERROR: cannot read revocation list: $LIST" >&2
  exit 2
fi
command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required" >&2; exit 2; }

schema="$(jq -r '.schema // empty' "$LIST")"
if [ "$schema" != "ebpfsentinel.revocations/v1" ]; then
  echo "ERROR: unexpected schema '$schema' (want ebpfsentinel.revocations/v1)" >&2
  exit 2
fi

serial="$(jq -r '.serial // empty' "$LIST")"
if ! printf '%s' "$serial" | grep -qE '^[0-9]+$'; then
  echo "ERROR: list has no numeric serial" >&2
  exit 2
fi

STATE="${SERIAL_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/ebpfsentinel/revocation-serial}"
if [ "$STATE" != /dev/null ]; then
  if [ -r "$STATE" ]; then
    seen="$(cat "$STATE")"
    if printf '%s' "$seen" | grep -qE '^[0-9]+$' && [ "$serial" -lt "$seen" ]; then
      echo "ERROR: revocation list serial $serial is older than serial $seen already seen — possible replay" >&2
      exit 2
    fi
  fi
  mkdir -p "$(dirname "$STATE")" 2>/dev/null || true
  printf '%s\n' "$serial" > "$STATE" 2>/dev/null || true
fi

rc=0
for digest in "$@"; do
  if ! printf '%s' "$digest" | grep -qE '^sha256:[0-9a-f]{64}$'; then
    echo "ERROR: not a digest: $digest" >&2
    exit 2
  fi
  hit="$(jq -r --arg d "$digest" \
    '.revocations[] | select(.digest == $d)
     | "  name:     \(.name)\n  release:  \(.release)\n  reason:   \(.reason)\n  advisory: \(.advisory)\n  revoked:  \(.revoked_at)"' \
    "$LIST")"
  if [ -n "$hit" ]; then
    echo "REVOKED: $digest"
    echo "$hit"
    rc=3
  else
    echo "ok: $digest is not revoked (list serial $serial)"
  fi
done

exit "$rc"
