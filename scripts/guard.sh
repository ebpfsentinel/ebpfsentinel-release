#!/usr/bin/env bash
# Repo self-checks for the trust anchor.
#
# Everything here is an invariant that, if it silently drifted, would weaken
# the guarantee this repo exists to provide. Run in CI on every PR; run it
# locally with `./scripts/guard.sh` before pushing.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
ok()  { echo "  PASS: $1"; }
bad() { echo "  FAIL: $1"; fail=1; }

# ---------------------------------------------------------------------------
echo "[1] third-party actions are pinned to a commit SHA"
# A mutable tag on an action means an upstream account compromise silently
# changes what our signing identity executes.
unpinned="$(grep -hoE '^\s*-?\s*uses:\s*[^ ]+' .github/workflows/*.yml \
  | sed -E 's/^\s*-?\s*uses:\s*//' \
  | grep -v '^ebpfsentinel/ebpfsentinel-release/' \
  | grep -vE '@[0-9a-f]{40}$' || true)"
if [ -n "$unpinned" ]; then
  bad "actions not pinned to a SHA:"
  echo "$unpinned" | sed 's/^/    /'
else
  ok "all third-party actions pinned"
fi

# ---------------------------------------------------------------------------
echo "[2] our own reusable workflows are called by tag, not SHA"
# The keyless identity is 'this workflow at refs/tags/v*'. A SHA ref would
# produce a certificate no published policy accepts.
selfrefs="$(grep -hoE 'uses:\s*ebpfsentinel/ebpfsentinel-release/[^ ]+' .github/workflows/*.yml \
  | sed -E 's/^uses:\s*//' | grep -vE '@v[0-9]+$' || true)"
if [ -n "$selfrefs" ]; then
  bad "self-references not on a v* tag:"
  echo "$selfrefs" | sed 's/^/    /'
else
  ok "self-references use a v* tag"
fi

# ---------------------------------------------------------------------------
echo "[3] caller allowlists agree across signing and verification"
# sign-image.yml, sign-blob.yml and verify.sh each hold the same list. If they
# drift, either a legitimate repo cannot sign, or verification accepts an
# origin we no longer sign for.
python3 - <<'PY'
import re, sys, yaml

def from_workflow(path):
    env = yaml.safe_load(open(path)).get("env", {})
    return sorted(x.strip() for x in env.get("ALLOWED_CALLERS", "").split("\n") if x.strip())

def from_verify(path):
    src = open(path).read()
    m = re.search(r'ALLOWED_SOURCE_REPOS="\$\{ALLOWED_SOURCE_REPOS:-\\\n(.*?)\}"', src, re.S)
    if not m:
        print("  FAIL: could not locate ALLOWED_SOURCE_REPOS in", path)
        sys.exit(1)
    return sorted(x.strip().replace("${ORG}", "ebpfsentinel")
                  for x in m.group(1).split("\n") if x.strip())

lists = {
    ".github/workflows/sign-image.yml": from_workflow(".github/workflows/sign-image.yml"),
    ".github/workflows/sign-blob.yml": from_workflow(".github/workflows/sign-blob.yml"),
    "policy/verify.sh": from_verify("policy/verify.sh"),
}
ref = lists[".github/workflows/sign-image.yml"]
if not ref:
    print("  FAIL: allowlist is empty")
    sys.exit(1)
bad = {k: v for k, v in lists.items() if v != ref}
if bad:
    print("  FAIL: allowlists disagree")
    for k, v in lists.items():
        print("   ", k, "->", v)
    sys.exit(1)
print(f"  PASS: {len(ref)} repositories, consistent across all three")
PY
[ $? -eq 0 ] || fail=1

# ---------------------------------------------------------------------------
echo "[4] no private key material committed"
leaked="$(grep -rlE 'BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY' \
  --exclude-dir=.git . 2>/dev/null || true)"
if [ -n "$leaked" ]; then
  bad "possible private key in:"
  echo "$leaked" | sed 's/^/    /'
else
  ok "no PEM private keys in the tree"
fi
if ls policy/keys/*.key >/dev/null 2>&1; then
  bad "policy/keys/ contains a .key file — only .pub belongs there"
else
  ok "policy/keys/ holds no private keys"
fi

# ---------------------------------------------------------------------------
echo "[5] revocation list is well-formed"
if command -v jq >/dev/null 2>&1; then
  LIST=policy/revocations.json
  schema="$(jq -r '.schema // empty' "$LIST" 2>/dev/null)"
  serial="$(jq -r '.serial // empty' "$LIST" 2>/dev/null)"
  if [ "$schema" != "ebpfsentinel.revocations/v1" ]; then
    bad "revocations.json schema is '$schema'"
  elif ! printf '%s' "$serial" | grep -qE '^[0-9]+$'; then
    bad "revocations.json has no numeric serial"
  else
    incomplete="$(jq -r '.revocations[] | select(
        (.kind | IN("image","binary") | not)
        or (.digest // "" | test("^sha256:[0-9a-f]{64}$") | not)
        or ((.reason // "") == "") or ((.advisory // "") == "")
      ) | .digest // "<no digest>"' "$LIST")"
    if [ -n "$incomplete" ]; then
      bad "incomplete revocation entries: $incomplete"
    else
      ok "revocations.json valid (serial $serial)"
    fi
  fi
else
  echo "  SKIP: jq not installed"
fi

# ---------------------------------------------------------------------------
echo "[6] shell scripts parse"
for f in policy/*.sh scripts/*.sh; do
  [ -f "$f" ] || continue
  if bash -n "$f" 2>/dev/null; then ok "$f"; else bad "$f does not parse"; fi
done

# ---------------------------------------------------------------------------
echo "[7] workflows and policies are valid YAML"
python3 - <<'PY'
import glob, sys, yaml
bad = []
files = sorted(set(glob.glob(".github/workflows/*.yml")
                   + glob.glob("policy/*.yaml")
                   + glob.glob(".github/*.yml")))
for f in files:
    try:
        # Manifests are multi-document (---), workflows are not; load_all covers both.
        list(yaml.safe_load_all(open(f)))
    except Exception as e:
        bad.append(f"{f}: {e}")
if bad:
    print("  FAIL:")
    for b in bad:
        print("   ", b)
    sys.exit(1)
print("  PASS: all YAML parses")
PY
[ $? -eq 0 ] || fail=1

echo
if [ "$fail" -eq 0 ]; then
  echo "guard: OK"
else
  echo "guard: FAILED"
fi
exit "$fail"
