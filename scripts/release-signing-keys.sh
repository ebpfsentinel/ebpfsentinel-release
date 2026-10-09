#!/usr/bin/env bash
# Prints the release signing public keys in the form the enterprise agent
# compiles in: `<Ed25519 base64>:<ML-DSA-65 base64>` pairs separated by spaces,
# the current pair first and every superseded pair after it.
#
# The agent verifies its measurements and integrity manifests against these,
# so a build handed none of them holds every licence back to the open source
# feature set. That is why this fails rather than printing nothing: a release
# that builds without the keys ships an agent that never unlocks.
#
# A superseded pair stays trusted because a manifest is signed after the binary
# is built, by whichever key is current that day, and an agent must not stop
# verifying the manifests issued for it because the key moved on afterwards.
#
# Usage: release-signing-keys.sh <policy/keys directory>
set -euo pipefail

dir="${1:?usage: release-signing-keys.sh <policy/keys directory>}"

read_key() {
  local file="$1"
  if [ ! -s "$file" ]; then
    echo "::error file=${file}::missing or empty - see docs/KEY-MANAGEMENT.md" >&2
    exit 1
  fi
  tr -d '[:space:]' < "$file"
}

# One substitution per assignment: in `a="$(x):$(y)"` only the last one's
# status reaches `set -e`, so a missing first half would pass.
ed_key="$(read_key "${dir}/release-signing-ed25519.pub")"
ml_key="$(read_key "${dir}/release-signing-mldsa.pub")"
pairs="${ed_key}:${ml_key}"

shopt -s nullglob
for ed in "${dir}"/release-signing-ed25519.*.pub; do
  suffix="${ed#"${dir}"/release-signing-ed25519.}"
  ml="${dir}/release-signing-mldsa.${suffix}"
  if [ ! -f "$ml" ]; then
    echo "::error file=${ed}::superseded Ed25519 key has no ML-DSA-65 half named release-signing-mldsa.${suffix}" >&2
    exit 1
  fi
  ed_key="$(read_key "$ed")"
  ml_key="$(read_key "$ml")"
  pairs="${pairs} ${ed_key}:${ml_key}"
done
for ml in "${dir}"/release-signing-mldsa.*.pub; do
  suffix="${ml#"${dir}"/release-signing-mldsa.}"
  if [ ! -f "${dir}/release-signing-ed25519.${suffix}" ]; then
    echo "::error file=${ml}::superseded ML-DSA-65 key has no Ed25519 half named release-signing-ed25519.${suffix}" >&2
    exit 1
  fi
done

printf '%s\n' "$pairs"
