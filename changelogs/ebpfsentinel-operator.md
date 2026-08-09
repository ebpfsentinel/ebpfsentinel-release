# Changelog — ebpfsentinel-operator

All notable changes to the Kubernetes operator are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versioning follows **CalVer**: `YYYY.M.RELEASE` (year, month without leading zero, release index within that month).

## [Unreleased]

First public release of the Kubernetes operator.

### Added

#### Custom resources

- **36 CRDs** covering the agent and its feature surface, with license-gated enterprise controllers
- **`EbpfSentinelAgent`**: `AttachMode` and container-awareness settings
- **`TLSIntelligenceConfig`**: seven sub-capabilities, aligned with the JA4+ engine
- **`ConnectionTrackingConfig`**: matches the kernel netfilter conntrack architecture
- **`JA4Config`**: JA4S fingerprinting and session tracking
- **`DLPPolicy`**: `DlpMode`, `ExtendedTlsConfig` and `TlsProxyConfig` with certificate checking
- **Load balancer CRDs** aligned with the agent LB API (Maglev hashing, L2 DSR, VIP announcement)

#### Deployment

- **Helm chart** shipping the CRDs, agent defaults and enterprise feature configuration
- **`operator_managed` forced in the rendered ConfigMap**, so a hand edit on the cluster cannot silently diverge from the CR
- **Distroless operator image**

#### Supply chain

- **Images cosign-signed keyless** through the `ebpfsentinel-release` reusable workflow, for both the OSS and enterprise agent images

### Changed

- Requeue intervals expressed with `Duration::from_mins`
- CI audits with the `cargo-audit` CLI instead of `rustsec/audit-check`

### Security

- `quinn-proto` bumped to 0.11.16 and `anyhow` to 1.0.103, clearing RUSTSEC-2026-0185 and RUSTSEC-2026-0190
