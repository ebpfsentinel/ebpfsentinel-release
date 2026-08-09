# Changelog — ebpfsentinel-enterprise

All notable changes to the enterprise layer are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versioning follows **CalVer**: `YYYY.M.RELEASE` (year, month without leading zero, release index within that month).

Within each release, entries are grouped **Added → Changed → Fixed → Security**, and each group is split into thematic subsections so a reader can scan one area at a time.

## [Unreleased]

First public release of the enterprise layer. Everything below is new relative to the OSS agent it extends.

### Added

#### Licensing

- **Dual-signed licence format (v2)**: Ed25519 plus post-quantum ML-DSA-65. Ed25519-only v1 licences are no longer accepted
- **Machine fingerprint binding** and distributed licence checks
- **Air-gap activation workflow**: offline request/response exchange, no outbound network needed
- **Encrypted feature modules** decrypted lazily against the licence, with derived AES keys zeroized after use
- **Feature binding to a signed binary-measurement manifest**: an enterprise feature refuses to run against a binary that is not the measured one
- **Signed per-node vCPU ceiling** enforced at runtime
- **Verbatim dual-signed token exposed on `/api/v1/license`** so a remote party can verify entitlement itself rather than trusting a self-report
- **Binary hardening**: crypto-verified feature guard, runtime integrity self-verification, anti-debugging detection, periodic re-validation
- **`sign-manifest` / `verify-manifest`** subcommands on the licence CLI, used by the release measurements pipeline

#### Data loss prevention

- **Pluggable DLP engine** behind a scanner trait, with a hardened Vectorscan wrapper (scratch pool, streaming, error propagation)
- **Custom pattern definitions** with a merger and validation pass
- **Block mode** with per-pattern action decisions
- **TLS deep inspection** with bypass lists and a certificate authority, plus a MITM proxy path
- **Extended-TLS probe layer**: Go, Java, static BoringSSL, kTLS and GnuTLS detectors, discovery wired end-to-end
- **Captured TLS plaintext matched with Vectorscan** instead of the OSS regex path

#### Machine learning and anomaly detection

- **Traffic feature extraction pipeline** with baseline profiling and anomaly scoring
- **ONNX Runtime native inference** behind an inference-engine trait with a model holder
- **EWMA streaming engine** and **CUSUM change-point detection**, both mapped to MITRE ATT&CK, fused into one score
- **Random Cut Forest** (anomstream) wired as a parallel detector
- **HyperLogLog cardinality estimation** replacing exact sets, with `dst_ip` and flow cardinality features
- **Count-Min Sketch heavy-hitter detection**
- **DNS entropy and character-bigram Markov model**
- **TLS fingerprint clustering**: Mini-Batch K-Means with browser-seeded centroids and outlier detection
- **TLSH payload similarity** C2 beaconing detection with a per-flow hash ring, periodicity estimation and an allowlist
- **IDS rule suggestion from ML anomalies**, false-positive feedback and training-data export

#### TLS intelligence

- **JA4+ threat database**, behavioural anomaly detection, PQC compliance checks, crypto policy enforcement
- **Per-destination cipher baseline** and TLS version downgrade detection
- **Server fingerprint tracking per SNI** with JA4S change detection
- **SNI / certificate CN / SAN mismatch detection** with wildcard-aware matching
- **Session resumption anomaly tracking** with multi-destination ticket reuse detection
- **Container-aware peer-group rarity detection** for fingerprint deviation from a workload baseline
- **ClientHello timestamps fed into the beaconing detector** for periodic C2 handshake detection
- **ONNX TLS feature extraction** with 8-dimension ClientHello vectorization

#### Multi-tenancy

- **Tenant model with namespace scoping**, tenant-isolated alert streams and audit logs
- **Sequential unlimited `tenant_id`** replacing the 31-tenant bitmask
- **Subnet (IPv4/IPv6), VLAN and interface based tenant resolution** with full eBPF wiring
- **Container cgroups attributed to tenants** in the eBPF datapath
- **Per-tenant resource quotas** and tenant-aware RBAC
- **Self-service tenant API**: dynamic CRUD, suspend/activate lifecycle, per-operation policy checks
- **Live propagation of tenant map changes to the kernel**

#### RBAC

- **Per-domain permission model** with security domains, a permission hierarchy and built-in roles
- **Per-resource prefix matching** with wildcard support and a resource filtering API
- **Role inheritance** with circular-reference detection, effective grant resolution and hot reload
- **Enforcement middleware**, role-to-user bindings and audit logging

#### SIEM export

- **Export framework** with a durable redb buffer, circuit breaker and multi-connector fan-out
- **Connectors**: Splunk HEC, Elasticsearch (ECS), OpenSearch, Wazuh, Microsoft Sentinel (CEF), QRadar (LEEF), generic syslog, OTLP, S3 and ClickHouse
- **At-least-once OTLP delivery** with retry and backoff
- **Retroactive IOC matching** over the historical buffer

#### High availability

- **Peer discovery and leader election**, state replication framework with concrete providers and consumers
- **Manual failover API**, recovery sync and failover event emission
- **Automatic initial sync** for recovering followers
- **Split-brain detection** in the heartbeat loop with a role-aware acknowledgement
- **Active-active multi-interface** operation with per-node interface assignments, fail-closed mode and cluster health tracking
- **`GET /api/v1/ha/replication`** status endpoint

#### Multi-cluster federation

- **Cluster registry and federation API** backed by redb
- **Federated policy distribution** with dry-run, per-cluster overrides and status tracking
- **Federated alert aggregation** with UUIDv7 deduplication, real HTTP transport and redb persistence
- **Management / member role separation**, member-side policy apply receiver
- **mTLS client-certificate authentication** with fingerprint pinning
- **`tenant_id` carried on federated alerts**

#### Compliance

- **Report engine** with HA, multi-tenant and multi-cluster infrastructure evidence sections
- **54 controls** across PCI-DSS v4.0, HIPAA, GDPR Art. 32 and SOC 2
- **EU and French templates**: NIS2, DORA, SecNumCloud, HDS, plus network segmentation validation
- **PDF reports** from an A4 layout with auto-pagination and a text fallback
- **Scheduled delivery** over SMTP email and webhook

#### Analytics and forensics

- **Analytics store** on redb with per-minute aggregation, minute-to-hour reaggregation and retention cleanup
- **Top talkers, alert and IOC summary APIs** with period filtering and delta computation
- **Trend detection** with Welford statistics, anomaly flagging and CSV/text export
- **Network forensics**: ring-buffer capture engine, event-triggered captures, timeline reconstruction API
- **Packet mirroring control** wired to the `IDS_MIRROR_CONFIG` eBPF map
- **Flow query API** for threat hunting
- **Every program bridged to analytics** through a SIEM event tap with component-specific extraction

#### Automated response

- **Policy engine** with SOAR webhook integration, cooldown tracking and an audit trail
- **eBPF enforcement**: `BlockIp`, `RateLimitIp` and `IsolateFlow` reach the OSS IPS blacklist and rate limiter in every mode (standalone, HA, fleet)
- **Persistent redb state** for response policies, webhook endpoints and dynamic tenants across restarts

#### Advanced L7

- **`L7InspectEngine`** with a Vectorscan-backed SQLi / XSS / LFI / RCE / exfiltration pattern catalogue
- **Per-protocol policy engines**: Redis, MongoDB, Kafka, SQL, LDAP, SSH
- **Additional detectors**: MQTT, AMQP, NATS, Cassandra
- **Alert enrichment** with OWASP, MITRE and PCI-DSS mapping

#### AI/LLM security

- **Shadow AI detection**, AI-aware DLP, exfiltration tracking and encrypted DNS policy enforcement

#### Privilege isolation

- **Rootless enterprise warden** with a proc-TLS extension protocol
- **Extended-TLS process scan brokered through the warden** when running rootless
- **Split rootless dist / compose / Helm assets**

#### Container awareness

- **Docker and Kubernetes enrichers**, `container` field on every alert to match the OSS schema

#### Fleet and observability

- **Fleet management endpoints**
- **70 Prometheus metrics** across 12 enterprise features on an OpenMetrics endpoint
- **Forensics and federation alert SSE streams**
- **OpenAPI documentation with Swagger UI** on every endpoint
- **Standalone OSS datapath alerts surfaced at `/api/v1/alerts`**

#### Air-gap

- **Feed bundle import/export** verified with Ed25519 + SHA-256, offline CLI workflow and startup enforcement with feature detection
- **Feed loading into threat intel** with path-traversal protection, RBAC enforcement, auto-import and compliance integration

#### Build and test

- **Vendored Vectorscan build** with auto-download, and a distroless static-binary Dockerfile
- **Enterprise fuzz targets** covering AI security, fleet, forensics, response, SIEM, TLS intelligence, analytics and HA heartbeat
- **Integration test suites** with auto-generated licences and two-node failover election
- **Full security tooling in CI**

### Changed

- `TenantAppService` migrated to lock-free `ArcSwap`
- `NoOpEbpfActivator` replaced by `OssEbpfActivator` backed by real OSS service handles, doing real eBPF attach/detach
- ML primitives (`OnlineStats`, `FeatureNormalizer`, `EwmaEngine`, `CusumEngine`, `CountMinSketch`, `AnomalyThresholds`) migrated onto anomstream, dropping the local implementations
- Enterprise Dockerfile takes the OSS sources from a configurable repository URL instead of a local path dependency
- HA moved to the Team tier

### Fixed

- Integer overflow in the analytics engine, found by fuzzing
- SIEM exporters no longer write index-lifecycle policy keys they never read
- An IPv6 rate-limit response is refused rather than writing the rate limiter's default entry
- Multi-cluster federation settings are validated at config load time

### Security

- Migrated off unmaintained dependencies (`rustls-pemfile`, `bincode`)
- `rand` bumped to 0.9 and `SigningKey::from_bytes` adopted, clearing RUSTSEC-2026-0097
- CA private key and leaf key material zeroized on drop
- A warning is emitted when a SIEM exporter disables TLS certificate verification
