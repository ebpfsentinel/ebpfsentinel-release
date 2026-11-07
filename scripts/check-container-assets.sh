#!/usr/bin/env bash
# Checks the container deployment a release publishes beside its binaries: a
# compose.yaml and the agent's seccomp profile, ebpfsentinel-agent.json, in one
# directory a reader downloads or unpacks and runs `docker compose up` from.
#
#   check-container-assets.sh <dir> <reference-profile> <version> [image-prefix]
#
# <dir> holds compose.yaml and ebpfsentinel-agent.json as they will ship.
# <reference-profile> is the agent repository's dist/seccomp copy: the shipped
# profile must equal it byte for byte, so a profile edited upstream and not
# re-shipped, or the reverse, fails the build instead of reaching a reader.
# <version> is the release version the image tags must already carry.
# [image-prefix] defaults to ghcr.io/ebpfsentinel/ebpfsentinel.
#
# The compose file must work from that directory alone: no build context, no
# path climbing out of it, the profile named by its relative path, and every
# image the published one at this release's tag rather than the 0.0.0-dev
# placeholder the source carries.
set -uo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 <dir> <reference-profile> <version> [image-prefix]" >&2
  exit 2
fi
dir="$1"
reference="$2"
version="$3"
prefix="${4:-ghcr.io/ebpfsentinel/ebpfsentinel}"
compose="${dir}/compose.yaml"
profile="${dir}/ebpfsentinel-agent.json"

fail=0
bad() { echo "::error::$1"; fail=1; }

for f in "$compose" "$profile"; do
  if [ -L "$f" ]; then
    bad "${f} is a symlink; the release ships the file itself"
  elif [ ! -s "$f" ]; then
    bad "${f} is missing or empty"
  fi
done
[ -s "$reference" ] || bad "reference profile ${reference} is missing or empty"
[ "$fail" -eq 0 ] || exit 1

if ! cmp -s "$profile" "$reference"; then
  bad "${profile} differs from ${reference}: the shipped seccomp profile must be the agent repository's, byte for byte"
fi
if ! python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$profile" 2>/dev/null; then
  bad "${profile} is not valid JSON"
fi

if grep -nE '^[[:space:]]*build[[:space:]]*:' "$compose"; then
  bad "${compose} names a build context; the release runs the published images"
fi
if grep -nE '(^|[=:[:space:]"'"'"'])\.\./' "$compose"; then
  bad "${compose} names a path outside its own directory"
fi
if ! grep -qE 'seccomp=\./ebpfsentinel-agent\.json' "$compose"; then
  bad "${compose} does not point the agent at ./ebpfsentinel-agent.json"
fi
if grep -n ':0\.0\.0-dev' "$compose"; then
  bad "${compose} still carries the 0.0.0-dev placeholder; the build stamps the release version"
fi

images="$(grep -E '^[[:space:]]*image[[:space:]]*:' "$compose" \
  | sed -E 's/^[[:space:]]*image[[:space:]]*:[[:space:]]*//; s/[[:space:]]*(#.*)?$//; s/^"(.*)"$/\1/')"
if [ -z "$images" ]; then
  bad "${compose} names no image"
fi
while IFS= read -r image; do
  [ -n "$image" ] || continue
  case "$image" in
    "${prefix}:${version}"|"${prefix}"-*":${version}") ;;
    *) bad "${compose} runs ${image}, not an image of this release (${prefix}*:${version})" ;;
  esac
done <<< "$images"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if ! (cd "$dir" && docker compose -f compose.yaml config -q); then
    bad "${compose} does not parse as a compose file"
  fi
fi

[ "$fail" -eq 0 ] || exit 1
echo "container assets in ${dir}: compose.yaml and ebpfsentinel-agent.json OK for ${version}"
