#!/usr/bin/env bash
# Verify an eBPFsentinel image or release blob against the org's keyless
# signing identity. For bare-metal / non-Kubernetes customers (clusters use
# the Kyverno policy instead).
#
# Requires: cosign >= 2.x
#
#   ./verify.sh image ghcr.io/ebpfsentinel/ebpfsentinel-dashboard@sha256:...
#   ./verify.sh blob  ebpfsentinel-agent-amd64.tar.gz  *.sig  *.crt
#   ./verify.sh sums  SHA256SUMS  SHA256SUMS.sig  SHA256SUMS.crt
#
# Air-gapped / no network to Rekor?  Set OFFLINE=1. Images verify from the
# transparency-log entry embedded in the signature (no Rekor call). Blobs
# verify from the cosign *.bundle that ships alongside *.sig/*.crt — pass the
# blob as usual; the bundle at "<file>.bundle" is used automatically.
set -euo pipefail

ORG="${ORG:-ebpfsentinel}"
ISSUER="https://token.actions.githubusercontent.com"
# Matches both reusable signing workflows on a release tag.
ID_RE="^https://github.com/${ORG}/ebpfsentinel-release/.github/workflows/(sign-image|sign-blob)\.yml@refs/tags/v.*$"

# Common identity flags; add --offline when OFFLINE is set (skip Rekor).
FLAGS=(--certificate-oidc-issuer "$ISSUER" --certificate-identity-regexp "$ID_RE")
[ "${OFFLINE:-0}" != 0 ] && FLAGS+=(--offline)

usage() {
  cat >&2 <<EOF
usage:
  $0 image <ref@sha256:digest>
  $0 blob  <file> <file.sig> <file.crt>
  $0 sums  <SHA256SUMS> <SHA256SUMS.sig> <SHA256SUMS.crt>

Override the org with ORG=... (default: ${ORG}).
Set OFFLINE=1 for air-gapped verification (no Rekor network call).
EOF
  exit 2
}

cmd="${1:-}"
shift || usage

case "$cmd" in
  image)
    [ "$#" -eq 1 ] || usage
    cosign verify "${FLAGS[@]}" "$1"
    ;;
  blob | sums)
    [ "$#" -eq 3 ] || usage
    if [ "${OFFLINE:-0}" != 0 ]; then
      # Offline: the *.bundle carries the signature, cert, and inclusion proof.
      cosign verify-blob "${FLAGS[@]}" --bundle "${1}.bundle" "$1"
    else
      cosign verify-blob "${FLAGS[@]}" --signature "$2" --certificate "$3" "$1"
    fi
    if [ "$cmd" = "sums" ]; then
      echo "SHA256SUMS signature OK — now check the files:"
      echo "  sha256sum -c $1"
    fi
    ;;
  *)
    usage
    ;;
esac

echo "OK: $cmd verified against ${ORG} release identity."
