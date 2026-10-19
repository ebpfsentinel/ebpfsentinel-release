# The apt and dnf repositories

`apt-get install ebpfsentinel` and `dnf install ebpfsentinel` are how an
estate installs software it did not write, and how it gets the next version
without anybody remembering to. The release pipeline builds a `.deb` and an
`.rpm` for each architecture, signs them like every other release asset, and
this repository serves them behind the two index formats those tools read.

Served from the `gh-pages` branch of this repository, at
`https://ebpfsentinel.github.io/ebpfsentinel-release`:

```text
apt/pool/main/e/ebpfsentinel/*.deb       every version ever published
apt/dists/stable/Release                 the index
apt/dists/stable/InRelease               clearsigned, what a current apt reads
apt/dists/stable/Release.gpg             detached, what an older apt reads
rpm/stable/{x86_64,aarch64}/*.rpm        every version ever published
rpm/stable/*/repodata/repomd.xml.asc     the dnf index signature
ebpfsentinel.asc                         the signing key, armored
ebpfsentinel.gpg                         the same key, for /etc/apt/keyrings
```

## Adding the repository

Debian and Ubuntu:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.gpg \
  | sudo tee /etc/apt/keyrings/ebpfsentinel.gpg > /dev/null
gpg --show-keys --with-fingerprint /etc/apt/keyrings/ebpfsentinel.gpg
echo "deb [signed-by=/etc/apt/keyrings/ebpfsentinel.gpg] https://ebpfsentinel.github.io/ebpfsentinel-release/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/ebpfsentinel.list
sudo apt-get update && sudo apt-get install ebpfsentinel
```

Fedora, RHEL and derivatives:

```bash
sudo rpm --import https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.asc
sudo curl -fsSL -o /etc/yum.repos.d/ebpfsentinel.repo \
  https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.repo
sudo dnf install ebpfsentinel
```

The repository file is published beside the key and this workflow writes it,
so the two cannot drift; it is a `curl` rather than a `dnf config-manager`
call because the two dnf generations disagree about the flag that adds a
repository from a URL. What it contains:

```ini
[ebpfsentinel]
name=eBPFsentinel
baseurl=https://ebpfsentinel.github.io/ebpfsentinel-release/rpm/stable/$basearch
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.asc
```

`signed-by` on the apt side and `repo_gpgcheck=1` on the dnf side are not
decoration. Without the first, the key is trusted for every repository the
host has; without the second, dnf checks the packages and not the index that
told it which packages exist.

The key a host imports arrives from the repository it is about to trust,
which no package repository avoids. What makes it checkable is the
fingerprint, published in `docs/KEY-MANAGEMENT.md`, in the installation
documentation and in the release notes, and the fact that the same packages
can be verified on their own against the release's cosign bundle without
trusting this key at all.

## Publishing

1. Cut the release as usual ([`RELEASES.md`](RELEASES.md)) and publish it.
   The packages are assets of that release and are listed in its signed
   `SHA256SUMS`.
2. Run **Publish package repository** with the release version. It
   downloads the assets, verifies `SHA256SUMS` against the release signing
   identity, refuses any package the sums do not list, signs each `.rpm`,
   rebuilds both indexes over the whole pool and pushes `gh-pages`.

The workflow is not called by `cut-release.yml`, and that is deliberate: an
index covers every version ever published, so publishing it is an act on the
repository rather than a step of one release. It is also the step most likely
to be run again on its own, after a key rotation or a tree repair.

Re-running it for a version already published is safe: the packages are
identical, re-signing an rpm with the same key is a no-op, and the push is
skipped when nothing changed.

## Retention

Old versions stay in the pool, forever by default. A rollback is the first
thing an operator reaches for, and `apt-get install ebpfsentinel=<version>`
only works while the file is still there. Removing a version is a decision
taken deliberately: delete it from `pool/` or from `rpm/stable/<arch>/` on
the `gh-pages` branch and re-run the workflow, which rebuilds the indexes
around what is left.

A version withdrawn for a security reason is removed **and** revoked - see
[`REVOCATION.md`](REVOCATION.md). Deleting a file stops new installations;
it says nothing to a host that already has it.

## Checking a publication

From a clean container, not from the machine that published:

```bash
# apt
docker run --rm -it debian:13 bash -c '
  apt-get update -qq && apt-get install -y -qq curl gnupg ca-certificates >/dev/null
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.gpg \
    > /etc/apt/keyrings/ebpfsentinel.gpg
  echo "deb [signed-by=/etc/apt/keyrings/ebpfsentinel.gpg] https://ebpfsentinel.github.io/ebpfsentinel-release/apt stable main" \
    > /etc/apt/sources.list.d/ebpfsentinel.list
  apt-get update && apt-cache policy ebpfsentinel'

# dnf
docker run --rm -it fedora:43 bash -c '
  rpm --import https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.asc
  curl -fsSL -o /etc/yum.repos.d/ebpfsentinel.repo \
    https://ebpfsentinel.github.io/ebpfsentinel-release/ebpfsentinel.repo
  dnf -q --refresh list ebpfsentinel --showduplicates'
```

Both must list the new version **and** the previous ones. An index that lost
its history is the failure this tree is most likely to have: it still
installs, so nothing looks wrong until a rollback is needed.

## When something is wrong

| Symptom | Cause |
|---|---|
| `NO_PUBKEY` on `apt-get update` | the host imported no key, or the key rotated and the host holds only the old one |
| `The following signatures were invalid` | the index was signed by a key that is not the one the host trusts; check the fingerprint against `KEY-MANAGEMENT.md` |
| dnf: `repomd.xml GPG signature verification error` | `repomd.xml.asc` is missing or stale, which means the index was rebuilt and not re-signed; re-run the workflow |
| a version installs but its predecessor is gone | the pool lost a file; restore it on `gh-pages` and re-run the workflow |
| the workflow fails before downloading anything | `REPOSITORY_SIGNING_KEY` or `REPOSITORY_SIGNING_FINGERPRINT` is unset on this repository |
