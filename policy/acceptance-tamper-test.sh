#!/usr/bin/env bash
# Acceptance: prove a MODIFIED artifact is inert at every layer.
#
# The acceptance criterion: a tampered artifact must be rejected by
#   (a) cosign signature verification    — a bad digest has no signature
#   (c) signed measurements manifest      — a tampered manifest fails verify
# and, when a cluster is reachable,
#   (b) Kubernetes admission             — Kyverno denies the unsigned digest
#
# Every check here PASSES when tamper is correctly REJECTED. A tamper that
# slips through is an acceptance FAILURE and exits non-zero.
#
# Usage:
#   acceptance-tamper-test.sh \
#     --image  ghcr.io/ebpfsentinel/ebpfsentinel@sha256:<digest> \
#     [--manifest measurements.signed] \   # + .sig/.crt beside it, from a release
#     [--rogue  ghcr.io/ebpfsentinel/<unsigned-image>@sha256:<digest>]  # for (b)
#
# Env: ORG (default ebpfsentinel). Requires cosign; kubectl+Kyverno only for (b).
set -uo pipefail

ORG="${ORG:-ebpfsentinel}"
ISSUER="https://token.actions.githubusercontent.com"
ID_RE="^https://github.com/${ORG}/ebpfsentinel-release/.github/workflows/(sign-image|sign-blob)\.yml@refs/tags/v.*$"

IMAGE="" MANIFEST="" ROGUE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --rogue) ROGUE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

pass=0 fail=0
ok()   { echo "  PASS: $1"; pass=$((pass + 1)); }
bad()  { echo "  FAIL: $1"; fail=$((fail + 1)); }

cosign_verify_image() {
  cosign verify \
    --certificate-oidc-issuer "$ISSUER" \
    --certificate-identity-regexp "$ID_RE" \
    "$1" >/dev/null 2>&1
}

# ── (a) cosign signature layer ────────────────────────────────────────────
if [ -n "$IMAGE" ]; then
  echo "[a] cosign signature layer"
  if cosign_verify_image "$IMAGE"; then
    ok "genuine signed image verifies"
  else
    bad "genuine signed image did NOT verify (check identity/tag or the image)"
  fi

  # Tamper: flip the last hex nibble of the digest → a digest with no signature.
  base="${IMAGE%@*}"; digest="${IMAGE##*@}"; hex="${digest#sha256:}"
  last="${hex: -1}"; case "$last" in f) new=e ;; *) new=f ;; esac
  tampered="${base}@sha256:${hex%?}${new}"
  if cosign_verify_image "$tampered"; then
    bad "tampered digest verified — signature layer is NOT enforcing"
  else
    ok "tampered digest correctly rejected (no signature under our identity)"
  fi
else
  echo "[a] skipped — no --image given"
fi

# ── (c) signed measurements manifest layer ────────────────────────────────
if [ -n "$MANIFEST" ]; then
  echo "[c] signed measurements manifest layer"
  if cosign verify-blob \
      --certificate-oidc-issuer "$ISSUER" \
      --certificate-identity-regexp "$ID_RE" \
      --signature "${MANIFEST}.sig" --certificate "${MANIFEST}.crt" \
      "$MANIFEST" >/dev/null 2>&1; then
    ok "genuine signed manifest verifies"
  else
    bad "genuine signed manifest did NOT verify"
  fi

  tmp="$(mktemp)"; { cat "$MANIFEST"; printf 'x'; } > "$tmp"
  if cosign verify-blob \
      --certificate-oidc-issuer "$ISSUER" \
      --certificate-identity-regexp "$ID_RE" \
      --signature "${MANIFEST}.sig" --certificate "${MANIFEST}.crt" \
      "$tmp" >/dev/null 2>&1; then
    bad "tampered manifest verified — manifest layer is NOT enforcing"
  else
    ok "tampered manifest correctly rejected"
  fi
  rm -f "$tmp"
else
  echo "[c] skipped — no --manifest given"
fi

# ── (b) Kubernetes admission layer (needs a cluster + Kyverno + policy) ────
if [ -n "$ROGUE" ] && command -v kubectl >/dev/null 2>&1 && kubectl version >/dev/null 2>&1; then
  echo "[b] Kyverno admission layer"
  ns="acceptance-$$"; kubectl create namespace "$ns" >/dev/null 2>&1 || true
  if kubectl -n "$ns" run rogue --image "$ROGUE" --restart=Never >/dev/null 2>&1; then
    bad "unsigned image was admitted — Kyverno policy not enforcing"
    kubectl -n "$ns" delete pod rogue >/dev/null 2>&1 || true
  else
    ok "unsigned image correctly denied at admission"
  fi
  kubectl delete namespace "$ns" >/dev/null 2>&1 || true
else
  echo "[b] skipped — no --rogue image or no reachable cluster"
fi

echo
echo "acceptance: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
