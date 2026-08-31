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
- **Every TLS probe plan carries the build id of the binary its offsets were resolved against**, so two scans that disagree on an offset can say whether the binary changed or the resolution did. A stripped binary reports no build id rather than failing the plan
- **A symbol the scan could not resolve is skipped instead of probed at offset zero**, which previously reported a probe that could never fire as a successful attach

#### Kernel verification at boot

- **Kernel helper probe runs before the version gate**, so a node that cannot start says which helper is missing rather than only which kernel version it wanted
- **Four boot outcomes**, each logged distinctly: verified, unverified (the probe itself could not run, agent continues), degraded (some eBPF objects lack a helper and are skipped) and refused (no object can load, exit code 2)
- **`GET /api/v1/ebpf/kernel-features`** on the enterprise API, reporting the probe result without issuing further kernel syscalls
- **An unverified boot is greppable three ways**: a WARN level, a `helper_support="unverified"` log field, and a message stating that helper support was not verified

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
- **A promotion reloads the datapath rather than adopting programs left on the interface.** An adopted attachment belongs to the previous generation of maps, so the node would run a datapath whose services write to maps nothing reads. Leftover attachments found after a step-down are reported as a diagnostic
- **Packet mirroring reports unavailable on a node with no active datapath** instead of accepting the request and capturing nothing
- **API: unassigning a role no longer needs a DELETE request body.** `DELETE /api/v1/rbac/assignments/{subject}/{role_id}` names the pair in the path. The old `DELETE /api/v1/rbac/assignments` is deprecated and kept for one release, with its body now optional and `?subject=&role_id=` accepted instead, because several HTTP clients and intermediaries strip or refuse a body on DELETE
- **API: reloading the custom roles is a POST on an action rather than a PUT on the collection.** `POST /api/v1/rbac/roles/reload` replaces `PUT /api/v1/rbac/roles`, which promised to replace the collection the path names and instead reloaded the custom roles while leaving the built-in ones in place. The old spelling is deprecated and kept for one release

### Fixed

- Integer overflow in the analytics engine, found by fuzzing
- SIEM exporters no longer write index-lifecycle policy keys they never read
- An IPv6 rate-limit response is refused rather than writing the rate limiter's default entry
- Multi-cluster federation settings are validated at config load time
- **Alerts were never delivered on a node running in HA mode.** The datapath event channel was only ever consumed in standalone mode, so a promoted leader produced alerts that reached neither the API, nor SIEM export, nor the automated response engine
- **Packet mirroring stopped working from the second promotion onward.** The mirror configuration handle was taken once at startup and kept across reloads, so it wrote to the previous datapath generation. The write succeeded and no frames were captured
- **A node could load a datapath on top of its own teardown** when promotion and step-down overlapped, leaving the recorded role disagreeing with what was attached
- **The enterprise API accepted unauthenticated requests on port 8444**, and the role used for access decisions was read from a caller-supplied header rather than from verified credentials

### Security

- Migrated off unmaintained dependencies (`rustls-pemfile`, `bincode`)
- `rand` bumped to 0.9 and `SigningKey::from_bytes` adopted, clearing RUSTSEC-2026-0097
- CA private key and leaf key material zeroized on drop
- A warning is emitted when a SIEM exporter disables TLS certificate verification
