#!/usr/bin/env bash
# Verify an eBPFsentinel image, blob or SHA256SUMS against the release
# signing identity.
#
# Two things are checked, not one:
#   1. the certificate SUBJECT  — our signing workflow on a v* tag;
#   2. the certificate SOURCE REPOSITORY — the repo that called that workflow.
#
# (2) matters because Sigstore records the *called* reusable workflow as the
# subject, so the subject alone does not prove who asked for the signature.
# Without it, a signature minted by an unrelated repository calling our public
# reusable workflow would verify here.
set -euo pipefail

ORG="${ORG:-ebpfsentinel}"
ISSUER="https://token.actions.githubusercontent.com"
ID_RE="^https://github.com/${ORG}/ebpfsentinel-release/.github/workflows/(sign-image|sign-blob)\.yml@refs/tags/v.*$"

# Repositories whose releases we sign. Keep in sync with ALLOWED_CALLERS in
# .github/workflows/sign-{image,blob}.yml.
ALLOWED_SOURCE_REPOS="${ALLOWED_SOURCE_REPOS:-\
${ORG}/ebpfsentinel
${ORG}/ebpfsentinel-enterprise
${ORG}/ebpfsentinel-operator
${ORG}/ebpfsentinel-dashboard
${ORG}/ebpfsentinel-release
${ORG}/anomstream}"

# SOURCE_REPO=<owner>/<repo> pins one exact origin. Unset means "any of the
# repositories listed above", which is still a closed set.
if [ -n "${SOURCE_REPO:-}" ]; then
  CANDIDATE_REPOS="$SOURCE_REPO"
else
  CANDIDATE_REPOS="$ALLOWED_SOURCE_REPOS"
fi

FLAGS=(--certificate-oidc-issuer "$ISSUER" --certificate-identity-regexp "$ID_RE")
[ "${OFFLINE:-0}" != 0 ] && FLAGS+=(--offline)

usage() {
  cat >&2 <<EOF
usage:
  $0 image <ref@sha256:digest>
  $0 blob  <file> <file.sig> <file.crt>
  $0 sums  <SHA256SUMS> <SHA256SUMS.sig> <SHA256SUMS.crt>

env:
  ORG=...          override the org (default: ${ORG})
  SOURCE_REPO=...  pin the exact repository the artifact was released from,
                   e.g. SOURCE_REPO=${ORG}/ebpfsentinel. Unset accepts any
                   eBPFsentinel product repository.
  OFFLINE=1        air-gapped verification (no Rekor network call)
  REVOCATIONS=...  path to a verified revocations.json; the digest is also
                   checked against it (see docs/REVOCATION.md)
EOF
  exit 2
}

# A valid signature does not mean an artifact is still fit to run — that is
# what the revocation list is for. Checked only when the caller supplies one,
# because silently skipping it would be worse than not offering it.
check_revoked() {
  local digest="$1"
  [ -n "${REVOCATIONS:-}" ] || return 0
  local checker
  checker="$(dirname "$0")/check-revocation.sh"
  if [ ! -x "$checker" ]; then
    echo "ERROR: REVOCATIONS is set but $checker is missing or not executable" >&2
    return 1
  fi
  "$checker" "$REVOCATIONS" "$digest"
}

# Run a cosign verify subcommand once per candidate source repository and
# succeed on the first match. Fails closed: no candidate => no verification.
try_repos() {
  local subcmd="$1"; shift
  local repo last_err=""
  while IFS= read -r repo; do
    repo="$(echo "$repo" | xargs)"
    [ -z "$repo" ] && continue
    if last_err="$(cosign "$subcmd" "${FLAGS[@]}" \
        --certificate-github-workflow-repository "$repo" "$@" 2>&1)"; then
      echo "$last_err"
      echo "source repository: $repo"
      return 0
    fi
  done <<EOF
$CANDIDATE_REPOS
EOF
  echo "$last_err" >&2
  echo "ERROR: no valid signature from ${ORG} release identity for any of:" >&2
  echo "$CANDIDATE_REPOS" >&2
  return 1
}

cmd="${1:-}"
shift || usage

case "$cmd" in
  image)
    [ "$#" -eq 1 ] || usage
    try_repos verify "$1"
    case "$1" in
      *@sha256:*) check_revoked "${1##*@}" ;;
      *) echo "note: reference is not digest-pinned, revocation not checked" >&2 ;;
    esac
    ;;
  blob | sums)
    [ "$#" -eq 3 ] || usage
    if [ "${OFFLINE:-0}" != 0 ]; then
      try_repos verify-blob --bundle "${1}.bundle" "$1"
    else
      try_repos verify-blob --signature "$2" --certificate "$3" "$1"
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
