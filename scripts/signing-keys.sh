#!/usr/bin/env bash
# Prints one family of signing public keys in the form the enterprise agent
# compiles in: `<Ed25519 base64>:<ML-DSA-65 base64>` pairs separated by spaces,
# the current pair first and every superseded pair after it.
#
# Two families live in `policy/keys` and this script reads either one:
#
#   release-signing  the measurements and integrity manifests - what a binary is
#   content-signing  a content bundle's manifest - what a subscription delivers
#
# They are separate pairs because content is cut far more often than a release
# is, and a key in use every day must not be the key that says what a binary
# is. The agent carries both rings and verifies each document against its own.
#
# A build handed no release keys holds every licence back to the open source
# feature set, and a build handed no content keys refuses every bundle. That is
# why this fails rather than printing nothing.
#
# A superseded pair stays trusted because a manifest is signed after the thing
# it describes was built, by whichever key is current that day, and an agent
# must not stop verifying the manifests issued for it because the key moved on
# afterwards.
#
# Usage: signing-keys.sh <policy/keys directory> <family>
set -euo pipefail

dir="${1:?usage: signing-keys.sh <policy/keys directory> <family>}"
family="${2:?usage: signing-keys.sh <policy/keys directory> <family>}"

case "$family" in
  release-signing|content-signing) ;;
  *)
    echo "::error::unknown key family '${family}' - release-signing or content-signing" >&2
    exit 1
    ;;
esac

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
ed_key="$(read_key "${dir}/${family}-ed25519.pub")"
ml_key="$(read_key "${dir}/${family}-mldsa.pub")"
pairs="${ed_key}:${ml_key}"

shopt -s nullglob
for ed in "${dir}"/"${family}"-ed25519.*.pub; do
  suffix="${ed#"${dir}"/"${family}"-ed25519.}"
  ml="${dir}/${family}-mldsa.${suffix}"
  if [ ! -f "$ml" ]; then
    echo "::error file=${ed}::superseded Ed25519 key has no ML-DSA-65 half named ${family}-mldsa.${suffix}" >&2
    exit 1
  fi
  ed_key="$(read_key "$ed")"
  ml_key="$(read_key "$ml")"
  pairs="${pairs} ${ed_key}:${ml_key}"
done
for ml in "${dir}"/"${family}"-mldsa.*.pub; do
  suffix="${ml#"${dir}"/"${family}"-mldsa.}"
  if [ ! -f "${dir}/${family}-ed25519.${suffix}" ]; then
    echo "::error file=${ml}::superseded ML-DSA-65 key has no Ed25519 half named ${family}-ed25519.${suffix}" >&2
    exit 1
  fi
done

printf '%s\n' "$pairs"
