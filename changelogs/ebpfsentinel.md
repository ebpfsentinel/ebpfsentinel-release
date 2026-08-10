# Changelog — ebpfsentinel

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versioning follows **CalVer**: `YYYY.M.RELEASE` (year, month without leading zero, release index within that month). Tags use the `v` prefix: `v2026.3.1`.

Within each release, entries are grouped **Added → Changed → Fixed → Security**, and each group is split into thematic subsections so a reader can scan one area (datapath, deployment, API…) at a time.

## [Unreleased]

### Added

#### Kernel feature reporting
- **`GET /api/v1/ebpf/kernel-features`**: what the running kernel actually accepts, probed once at startup and served from cache. Reports every (program type, helper) pair each compiled object needs, and separates "the kernel refused this helper" from "the probe could not run". The probe itself needs `CAP_BPF`, which the rootless BPF-token path deliberately does not hold, so on a token deployment the answer is `not_probed` - and a `not_probed` result never refuses a program
- **`kernel_helpers_missing` on `/readyz`**: names each object whose required helpers the kernel rejected, so an agent that will never see traffic says so instead of coming up healthy
- **Conntrack kfunc metrics**: `kfunc_state_new`, `kfunc_state_established`, `kfunc_state_related`, `kfunc_state_invalid`, `kfunc_marked` and `kfunc_read_errors`. The kernel connection state was already being read out of `nf_conn` and then discarded, which left seven connection-tracking counters permanently at zero and the three kfunc lookup counters unexported; both are now wired through. A guard test fails the build if a counter slot has no exported label

#### Attach diagnostics
- **`attach_blocked` on `/readyz` and `GET /api/v1/ebpf/status`**: one entry per program that loaded but could not attach, carrying a sentence an operator can act on - the occupying program's id and XDP mode, whether a BPF link holds it (so whether anyone but its owner can replace it), and whether the requested and occupied modes conflict. The `nested_xdp` flag is read back from rtnetlink rather than guessed from an errno, because the kernel answers `EBUSY` and `EEXIST` for the same underlying situation
- Docker and Kubernetes nested XDP, where the runtime or CNI already owns the interface's single XDP slot, is now diagnosable from the endpoint instead of from a bare `File exists (os error 17)`

#### Uprobe inventory
- **`GET /api/v1/ebpf/uprobes`**: every TLS uprobe currently attached, with the library path, its device and inode, the symbol, and the file offset the probe actually landed on. The offset the link was created at is now recorded at attach time rather than resolved again for reporting, so what the endpoint returns is what the kernel is running. Libraries are counted by inode, so one library mapped by twenty processes counts once
- The inventory is dropped when the datapath is detached, so a node that has torn down its programs stops reporting TLS inspection it is no longer doing

#### Ring-buffer observability
- **`ringbuf_events_total{source}`**, **`ringbuf_events_dropped_total{source,reason}`** and **`ringbuf_latency_seconds{source}`**: every record userspace drains, discards or is late to pick up, per producing program. Ring pressure was previously invisible between the kernel counter and the pipeline

### Changed

#### eBPF toolchain
- **aya 0.14.0, aya-obj 0.3.0, aya-ebpf 0.2.1**. `ebpf-common` pinned aya directly instead of through the workspace, so the dependency graph carried two aya versions and every `Pod` implementation targeted the older trait; the pin is now unified
- **`aya-build`, `aya-log` and `aya-log-ebpf` removed.** The log call sites were `#[cfg(debug_assertions)]` and kernel objects are built in release, so the shipped program bytes are byte-identical
- **All map declarations migrated to BTF map definitions** across every kernel object. The legacy `maps` ELF section is gone; loading now goes through the BTF `.maps` section exclusively

#### Datapath
- **DNS ring records are tiered.** A 192-byte record carries query-shaped traffic where a 576-byte record was reserved before, so the 256 KB DNS ring holds 1365 in-flight records instead of 455
- **Interface indices are read through the kernel context accessor** at all nine sites that previously read the raw field behind `unsafe`
- **XDP re-attach is idempotent.** An agent restart that finds its own program already on the interface readopts it instead of creating a second link. Pinned maps are still wiped at startup - the kernel offers no way to ask whether a live process still holds a pin - but the wipe now states its reason in the log

### Fixed

#### DLP
- **SSL libraries whose backing file was unlinked while mapped are now found.** The `/proc/<pid>/maps` parser truncated any path containing a space and mishandled the `(deleted)` marker, so an unlinked mapping was a silent miss. Worse than a miss after an in-place package upgrade: the old path then names a replacement inode while running processes keep the old one mapped, so resolution by name would probe the wrong file at the wrong ELF offsets. Unlinked mappings now resolve through `/proc/<pid>/map_files/`, which requires `CAP_SYS_ADMIN` to look up an entry; where that capability is absent the mapping is skipped exactly as before
- **A brief warden outage no longer rebuilds the entire uprobe set.** The scan collapsed "the broker is unreachable" into "nothing is mapped", so every warden restart tore down and re-attached every probe; unreachability is now an error and the reconcile pass holds the current set

#### Kernel-side error handling
- **A failed connection-state read no longer downgrades an established flow to new.** `xdp-firewall` left the status word at zero on a failed probe read, which every branch reads as "no state bits set"; it now returns an unknown sentinel, so a stale BTF offset degrades visibly instead of silently changing which rules match
- **A failed L7 payload read no longer emits a truncated record.** `tc-dns` advertised the declared length over a zeroed payload; the record is now discarded and counted
- **A failed dynptr adjustment no longer reports the L2 header as the L7 protocol.** The probe read the dynptr's current start regardless of whether the adjustment succeeded

### Security

- **Cross-connection payload disclosure in L7 events (`tc-ids`).** The ring-buffer reservation was not zeroed before use, so a failed payload read submitted whatever the ring last held, under this packet's header and at this packet's length - userspace was handed another connection's bytes as if they belonged to this one. The reservation is now discarded on a failed read and the failure is counted

## [2026.6.1] - 2026-06-16

### Added

#### Kernel Netfilter Integration (kernel 6.9+)
- **Kernel-native connection tracking**: conntrack delegated to the in-kernel netfilter engine via kfuncs (`bpf_skb_ct_lookup`, `bpf_xdp_ct_lookup`, `bpf_ct_release`) — userspace shadow CT tables removed
- **Flow termination via netfilter**: `kill_flow` marks flows `IPS_DYING` in the IDS block and XDP drop paths so the kernel tears down the connection
- **Kernel-native NAT**: `bpf_ct_set_nat_info` delegation at every DNAT/SNAT application site
- **BPF token delegation end-to-end**: load and attach all eBPF programs with a BPF token alone — no `CAP_BPF`/`CAP_SYS_ADMIN`/`CAP_PERFMON`
- **Rootless eBPF loading**: userns launcher self-maps and loads the program set without root
- **kfunc bindings spanning kernel 5.18–6.9**: netfilter CT allocate/lookup/NAT, 6.4–6.5 dynptr (`SkbDynptr`/`XdpDynptr`), 6.3 XDP metadata, 6.9 arena pages, IPsec/FOU-GUE steering, in-kernel container resolution, per-tenant RCU enforcement
- **Userspace conntrack coherence**: `/proc/net/nf_conntrack` reader, conntrack event stream over SSE, and `conntrack watch`/`list`/`status` CLI subcommands

#### Privilege Isolation (warden)
- **warden privilege broker + rootless agent**: the agent self-bootstraps its user namespace and loads its own eBPF; the warden brokers the host-netns operations it cannot do rootless (conntrack flush, route, gratuitous ARP, pcap)
- **warden-proto control plane**: typed protocol crate over a shared control socket with a reconnecting client for warden-restart resilience
- **Split deployment assets**: rootless `Dockerfile.agent`, `Dockerfile.warden`, split DaemonSet / docker-compose / systemd units, Helm warden sidecar
- **AppArmor unprivileged-userns handling**: per-binary profile with sysctl fallback
- **Tailored agent seccomp profile**: Docker default plus an `unshare`/`mount`/`bpf` allow-list (replaces `seccomp=unconfined`)
- **Host cgroupfs mounted read-only** so the container resolver can attribute egress cgroup ids

#### Container & Kubernetes Awareness
- **cgroup attribution**: `cgroup_id` on packet/DLP/DNS events, cgroup resolver with LRU cache, port/adapter/alert plumbing
- **Docker + Kubernetes enrichers**: Docker Engine API client and Kubernetes API enrichment of alerts
- **tc-ids container attribution**: egress hook + `src_port` rule matching tag locally-originated traffic with a non-zero cgroup id
- **netkit support**: native TC-program attach on Cilium netkit pod interfaces (kernel 6.7+) via `BPF_LINK_CREATE` + `BPF_NETKIT_PRIMARY`, with device detection, pod namespace discovery, and a hot-plug watcher that attaches/detaches as pods come and go
- **Container/K8s context** surfaced on both the REST and gRPC alert streams

#### TLS Intelligence (JA4+)
- **JA4S ServerHello fingerprinting**: `TlsServerHello` parser + `compute_ja4s`, dedicated JA4S endpoint
- **New MITRE mappings**: TLS version downgrade, `SniCertMismatch` (T1557), `SessionResumeAnomaly`, and container-aware `PeerGroupAnomaly`
- **Fingerprint persistence**: JA4/JA4S caches backed by a redb store
- **Inline TLS record parsing** for JA4 enrichment in the L7 path

#### L7 Firewall
- **IMAP and POP3** parsers in the OSS dispatcher plus an `L7ExtendedParser` extension port
- **Userspace stream reassembler** with HTTP `Content-Length` completion
- **Deeper L7 capture**: `MAX_L7_PAYLOAD` raised to 2048, `EVENTS` ring buffer to 4 MiB, `L7_PORTS` capacity to 256 with a `MAX_L7_PORTS` validator
- **Source/destination MAC filtering** through the firewall rule create API

#### Load Balancer
- **Maglev consistent-hash** backend selection
- **L2 DSR forwarding** (`mode: l2dsr`)
- **L2 VIP announcer**: bounded XDP ARP responder + gratuitous-ARP failover, REST/CLI surface with hot-reload, and an L2 self-binding whitelist
- **RSS-hash IP_HASH**: NIC RSS hash drives `IP_HASH` backend selection

#### Hardware Offload
- **NIC metadata on events**: RSS hash, RSS hash type, and hardware RX timestamps on packet/DDoS/ratelimit events
- **VLAN tag recovery** via `bpf_xdp_metadata_rx_vlan_tag` for hardware-stripped tags

#### NAT, IPsec & Overlays
- **IPsec xfrm interface steering** and **FOU/GUE overlay encapsulation** on NAT rules
- **IPsec-aware datapath**: ESP/AH SAD lookup detects protected traffic, tunnel-aware DNAT matching via `NAT_MATCH_XFRM`
- **IPv4 fragment drop**: `tc-scrub` `drop_fragments` policy

#### Authentication & API
- **EdDSA + JWKS** JWT verification, async `AuthProvider` with JWKS refresh and tenant claims
- **Operator-managed identity endpoint**
- **Server-Sent Events** alert stream with domain-scoped filtering
- **IPS blacklist write API** + STIX URL indicator surfacing
- **New REST endpoints**: conntrack status (`max_connections`), geoip status/lookup, zone + policy CRUD, gateway CRUD and routes, `dns/status`, threat-intel feed refresh with `last_fetched`
- **Configurable write-API rate limit**, loopback-exempt by default
- **Dedicated metrics listener** on `metrics_port` to match deployment manifests
- **OpenAPI spec emitted via xtask**; `geoip_lookups_total` hit/miss counter and per-domain GeoIP surfacing

### Changed

#### Platform requirements
- **Minimum kernel raised 6.6 → 6.9**, enforced as a mandatory startup gate with no API-only fallback
- **eBPF loads via BPF token by default**; capabilities are demoted to a fallback and the agent runs rootless under a user namespace

#### Connection tracking
- **Connection tracking is kernel netfilter only**: `CT_TABLE_V4/V6` shadow maps and the userspace TCP state machine were removed

#### Deployment & architecture
- **Privilege-split deployment**: warden broker + rootless agent across Docker, docker-compose, Helm, systemd, and the integration harness (the combined single-container/launcher topology was retired)
- **Per-domain config reload locks** replace the single global reload mutex
- **Architecture cleanup**: Prometheus metrics adapter moved out of infrastructure, HTTP driving adapter moved to the agent crate, kernel-version gate collapsed onto a single `kernel_probe` source of truth
- **Arena event paths**: zero-copy arena paths were added and then narrowed to a RingBuf fallback where `BPF_MAP_TYPE_ARENA` proved non-functional under load
- Rust toolchain refreshed; `actions/checkout` and other CI action majors bumped

### Fixed

#### Datapath
- **SYN cookies**: use kernel `bpf_tcp_raw` syncookies so legit clients complete the handshake under flood; keyed with a SipHash-2-4 PRF + CSPRNG secret; IPv6 SYN+ACK forged from VLAN-correct addresses
- **DDoS protections now arm**: wired `DDOS_SYN_CONFIG`, `ICMP_CONFIG`, `CONNTRACK_CONFIG`, and `AMP_PROTECT_CONFIG` (previously never written → disabled)
- **tc-scrub kernel hang** on forwarded packets fixed by coalescing IPv4 header rewrites and correcting the MSS/timestamp checksum
- **Firewall deny enforcement**: explicit deny rules of any shape now apply to already-established flows and tear down the kernel conntrack entry mid-flow
- **DDoS/ratelimit datapath revived**: load `xdp-ratelimit` non-device-bound so the firewall→ratelimit tail-call wires; demote fast-path rules to the array scan to preserve rule priority
- **PKT_CTX pinned by name** so `xdp-firewall-reject` shares the parent's populated scratch buffer
- **TC chaining**: return `TCX_NEXT` on pass for mprog cooperation, allow multi-interface attach without reload error, retry XDP attach on `EBUSY` after restart
- **tc-dns** loads the actual DNS payload length (the fixed-512 load left short packets empty)
- **uprobe-dlp** isolated under its own pin path so its `EVENTS` ring buffer never aliases the packet buffer
- **L7 reassembler** parses idle-flushed buffers instead of discarding them and trims stale ringbuf bytes via carried payload length
- **QoS** rate unified to bits/sec with `ns_per_byte` storage and classifier match-key parsing
- **Metrics** expose real eBPF map-counter deltas instead of a poll heartbeat; OTLP exports counted as `alerts_exported` instead of mislabeled drops

#### Build & Platform
- **tc-ids loads when L7 is enabled** so L7/encrypted-DNS capture works without IDS
- **Config reload**: synchronous validation, awaited completion, SIGHUP handler installed before readiness; EdDSA/JWKS counted when validating JWT auth
- **Non-blocking pcap loop** honours the duration deadline on quiet links
- **musl/Docker builds**: typed `SIOCGIF*` ioctl constants, platform-portable `msg_controllen` cast, config dir staged at 0755 for rootless traversal
- **TLS API 500s** fixed via `TlsConnectInfo`/`ConnectInfo` injection and axum 0.8 `into_make_service()`
- Dependency bumps: `rustls-webpki` 0.103.13, `lettre` 0.11.22

### Security

- **Webhook/feed SSRF hardening**: stopped following redirects, validate the resolved IP at connect time, and closed numeric-IP / mapped-IPv6 / DNS-rebinding bypasses
- **RBAC write enforcement** added to 16 mutating API endpoints
- **Config disclosure**: webhook `Authorization` header values and `api_key_salt` masked in `sanitized()` (were leaking via `GET /api/v1/config`)
- **Path traversal**: reject `..` in the key/cert path allowlist (`starts_with` was bypassable)
- **JWKS**: plaintext fetch restricted to loopback, inline refresh cooldown caps unauthenticated DoS amplification
- **No error-detail leakage** in HTTP 500 bodies — logged server-side, generic message returned
- **DoS guards**: reject overflowing Redis bulk length, bound STIX/JSON feed parsing to `max_iocs`, compile-time-safe DNS header bounds, runtime capture-id path-safety

## [2026.3.2] - 2026-03-28

### Added

#### Agent Architecture
- **API-only mode**: agent runs without eBPF privileges for development, testing, and management-plane-only deployments
- **Agent runtime as reusable library**: extracted startup/reload/shutdown modules, `load_ebpf_programs()`, state providers/consumers as pub API for enterprise extension
- **Hot-reload eBPF lifecycle**: `EbpfProgramManager` with per-program loading/unloading, `CancellationToken` readers, XDP chain rewiring, dynamic metrics
- **Configurable XDP attach mode**: auto/native/generic/offloaded with smart fallback and startup logging
- **Parallel event dispatch**: per-source worker partitioning, parallel alert sender dispatch, parallel threat intel feed fetches

#### Detection & Response
- **MITRE ATT&CK v18 mapping**: technique registry wired into all alerts, REST API/gRPC/CLI filtering by tactic/technique, coverage endpoint and dashboard
- **JA4+ TLS fingerprinting**: ClientHello parser → JA4/JA4S/JA4H hash computation → flow cache → alert enrichment → REST API + gRPC + CLI + Prometheus metrics
- **Post-quantum TLS**: X25519MLKEM768 hybrid key exchange for server TLS, PQ `CryptoProvider` at startup for all outbound clients, public API for enterprise mTLS
- **OTLP Logs export**: fire-and-forget via official opentelemetry-rust gRPC/HTTP client
- **Manual response actions**: time-bounded block/throttle via CLI/API with TTL auto-expiry and audit trail
- **Manual packet capture**: on-demand PCAP via CLI/API, duration-limited, libpcap format
- **Auto-capture**: event-triggered PCAP on high-severity alerts
- **Auto-response**: automated TTL-bounded actions on detection events
- **DoH/DoT detection**: encrypted DNS detection with built-in resolver domain list, custom resolvers, metrics
- **DNS over TCP**: capture on port 53 alongside existing UDP support
- **STIX 2.1 feed parsing**: multi-engine distribution to threat intel, DNS blocklist, domain reputation, L7 firewall
- **Contextual MITRE mapping**: per-destination-port technique selection for IDS, threat intel, firewall, ratelimit, L7, IPS alerts
- **Alert pipeline integration**: firewall, ratelimit, L7, IPS, DNS blocklist, reputation, and encrypted DNS events routed through the unified alert system

#### eBPF Datapath
- **QoS EDT pacing enforced**: `bpf_skb_set_tstamp` in eBPF datapath (previously metrics-only)
- **BPF MTU guard**: `bpf_check_mtu` in xdp-firewall and xdp-ratelimit with `mtu_exceeded` metric
- **XDP load balancer integration**: tail-call chain with standalone fallback, shared asm/checksum patterns
- **XDP firewall reject**: tail-called `xdp-firewall-reject` program for TCP RST / ICMP unreachable
- **XDP SYN cookie refactor**: extracted as tail-called `xdp-ratelimit-syncookie` with shared helpers
- **TC socket cookie**: wired in TC programs for flow correlation
- **IDS packet mirroring**: `bpf_clone_redirect` support
- **Conntrack lazy timeout eviction**: DevMap/CpuMap infrastructure, SYN cookie helpers
- **Per-CPU LRU**: coarse timestamps, ECN marking, SKB linearization, MTU check
- **Tenant-aware eBPF**: `tenant_id` field on all entry structs, VLAN/subnet LPM resolution, `tenant_matches()` helper, `TenantRateLimitBucket`, `TenantVlanMapManager`
- **BPF compiler barrier**: fix verifier packet pointer tracking after `bpf_xdp_adjust_tail`
- **Shared `emit_packet_event!` macro**: deduplicated across tc-ids/threatintel/qos/nat-ingress/nat-egress with NPTv6 helpers

#### CLI
- **`watch`**: real-time alert streaming
- **`investigate`**: deep inspection of IPs, flows, and connections
- **`alerts stats`**: alert statistics and trends
- **`risk-score`**: network risk score computation
- **`top-talkers`**: top sources/destinations by volume
- **`network-flows`**: active flow listing
- **Enhanced `status`**: expanded health and operational metrics

#### Kubernetes & Deployment
- **Production Helm chart**: JSON schema validation, ServiceAccount, NOTES.txt, full values reference
- **PrometheusRule**: 8 alerting rules for agent health and detection
- **Fine-grained capabilities**: replace privileged mode in docker-compose and systemd
- **Configurable `securityContext`**, PodDisruptionBudget, container resource limits, optional NetworkPolicy
- **CAP_NET_RAW**: added to systemd service, captures directory at `/var/lib/ebpfsentinel/captures`

#### CI/CD & Quality
- **Miri + cargo-careful CI jobs**: `deny(unsafe_op_in_unsafe_fn)` in ebpf-common
- **32 property-based tests (proptest)**: DNS, STIX, CIDR, L7 parsers
- **Realistic benchmark scripts**: SYN/UDP/ICMP flood, IDS payload scenarios, rule-count impact with 2-VM delta method
- **DLP TLS tests**: real traffic validation of all OSS regex patterns (PCI/PII/credentials)
- **Integration test suite expansion**: new suites, API schema validation, timing fixes
- **Fuzz testing CI job**: critical parsers in security workflow
- **Helm lint CI job**
- **CI composite actions**: deduplicated workflows, removed redundant audit job
- **Least-privilege CI/CD permissions**: all workflows hardened
- **Per-worker Prometheus metrics**: parallel event dispatch observability

### Changed

- Agent runtime extracted as library with pub startup/reload/shutdown API
- Fingerprint cache migrated to interior mutability (eliminated last RwLock from hot path)
- `AlertDestination::Otlp` simplified to unit variant (endpoint lives in `OtlpExportConfig`)
- Config file permissions enforced to 640 across all environments
- JWT validation leeway explicitly set to zero
- SMTP TLS disabled now emits a warning
- gRPC timeouts configured, eBPF crash cleanup on shutdown
- eBPF Rust 2024 edition: `unsafe` blocks added, unused imports removed, `transmute` replaced
- Config examples updated with PQ mode, OTLP export, DoH resolver settings
- QUICKSTART.md added alongside Helm chart

### Fixed

- **eBPF verifier failures**: tc-conntrack, tc-nat, uprobe-dlp, xdp-firewall, xdp-ratelimit compatibility fixes
- **DLP auto-detect SSL library**: OpenSSL/BoringSSL path detection for uprobe attachment
- **JA4 pipeline**: end-to-end wiring — compute in L7 events, cache, enrich alerts, real cache in API
- **OTLP config**: wired tests, DoH/DoT metrics, custom resolvers
- **tc-dns SKB linearization**: jumbo frame support via `bpf_skb_pull_data`
- **tc-ids `ctx.len()`**: use instead of linear buffer size for `bpf_skb_pull_data`
- **Kernel memory leak padding**: ESP/AH IPv6 parsing, IHL validation, ICMP conntrack
- **`take_map` consuming ProgramArray**: on repeated eBPF wiring
- **DNS compression pointer off-by-one**: hop limit boundary corrected
- **Firewall stale fast-path**: HashMaps flushed on rule reload
- **RwLock poison handling**: logged and handled instead of silently recovering
- **DLP uprobe memory leak**: `LruHashMap` for bounded memory, `saturating_sub` for safe arithmetic
- **Async alert pipeline**: `std::sync::Mutex` → `tokio::sync::Mutex` in async senders
- **Docker distroless**: `COPY` from builder stage instead of `RUN mkdir`
- **Docker kernel headers**: symlink Linux headers into musl include path for libpcap build
- **API latency test**: was measuring timeout duration instead of actual latency
- **OpenAPI spec**: added QoS endpoints, SecurityScheme, 401/403 responses on all protected paths
- **Unused `asm_experimental_arch`**: removed from eBPF programs that don't use inline assembly
- **Benchmark methodology**: 2-VM delta method with 3-run averaging, 5Gbps cap, 500Mbps volume baseline

### Security

#### Hardening
- **gRPC API key auth**: `x-api-key` header support; gRPC reflection now opt-in
- **Token revocation**: constant-time API key lookup with revocation list
- **SSRF protection**: webhook URLs, feed URLs, alert destinations validated against private/loopback/multicast with header injection prevention
- **Input validation**: BPF filter length limits, interface/namespace name validation, DLP regex validation at config time, JSON nesting depth and YAML size limits
- **TLS hardening**: default TLS 1.3 only (opt-in 1.2), minimum 2048-bit RSA for JWT, restricted key paths
- **API rate limiting**: auth-specific rate limits, metrics endpoint rate-limited regardless of auth config
- **CORS hardening**: exact host validation (fixes origin bypass), restricted to localhost or explicit origins
- **HTTP security headers**: standard headers on all responses
- **Salted API key hashes**: `/dev/urandom` for cryptographically secure salt generation
- **Startup hardening**: restrictive umask, privilege check, strict config file permissions (640), minimum kernel 6.6

#### Fixes
- **CORS origin bypass** (P0): prefix match replaced with exact host validation
- **Token revocation not enforced**: revocation list wired into authentication chain
- **Namespace access default-deny**: absent `namespaces` JWT claim now denies access
- **JWKS fetch logic**: composite auth provider no longer leaks internal error details
- **Bearer token parsing**: malformed tokens rejected early
- **SHA validation**: corrected binary integrity version check
- **LB ifindex path traversal**: interface name validated in load balancer resolver

## [2026.3.1] - 2026-03-15

### Added

- Full Rust eBPF network security agent with 12 kernel programs (XDP + TC + uprobe)
- Stateful firewall with L3/L4 filtering, conntrack, CIDR/GeoIP, IPv4/IPv6, VLAN, schedule rules, IP sets
- NAT: SNAT, DNAT, masquerade, port forwarding, 1:1 NAT, NPTv6 (RFC 6296), hairpin NAT
- IDS/IPS with pattern matching, auto IP blacklisting, /24 subnet blocking
- DLP: SSL/TLS content scanning for PCI, PII, credentials
- Rate limiting: 4 algorithms (token bucket, fixed/sliding window, leaky bucket) + SYN cookies + per-country tiers
- DDoS mitigation: SYN/UDP/ICMP/volumetric flood detection, automatic country CIDR blocking
- Threat intelligence: source-agnostic feed integration with bloom filter + LRU hash IOC correlation
- DNS intelligence: passive capture, domain blocklists, behavioral reputation scoring
- L7 firewall: HTTP, TLS/SNI, gRPC, SMTP, FTP, SMB with GeoIP matching
- Packet scrubbing: TTL, MSS clamping, DF clearing, IP ID randomization, TCP flag scrubbing
- Multi-WAN routing with health checks and failover
- L4 load balancer: TCP/UDP/TLS passthrough with 4 algorithms, up to 4096 services / 256 backends per service
- Traffic shaping / QoS: dummynet-inspired pipes, WF2Q+ queues, 5-tuple classifiers, FQ-CoDel
- REST API with OpenAPI 3.0 and Swagger UI (52 endpoints)
- gRPC streaming for real-time alert subscriptions
- Prometheus metrics with per-domain counters and eBPF kernel-side tracking
- Alert pipeline with circuit breaker, dedup, email/webhook/log routing
- CLI with 13 domain subcommands, table/JSON output
- JWT (RS256) + OIDC (JWKS) + API key authentication with RBAC
- TLS 1.3 for REST and gRPC
- Hot reload via file watcher, SIGHUP, or API
- Security zones with per-interface policies
- Interface groups for rule scoping
- Multi-level HashMap fast-path for firewall (O(1) 5-tuple + port lookup) and NAT rules
- Consolidated ratelimit bucket union (4 maps to 1, 75% memory reduction)
- Two-level LB HashMap architecture (services 64 to 4096, backends/svc 16 to 256)
- Map pinning for shared CT_TABLE and INTERFACE_GROUPS (~49MB memory savings)
- Tiered RingBuf events: L7 (192B/576B), DLP (280B/4120B) — 67-94% savings
- User RingBuf infrastructure for atomic config push (eBPF side ready, userspace pending aya API)
- 24 fuzz targets covering all domain engines and parsers
- Docker multi-arch image (distroless/static)
- 7 CI workflows (format, lint, test, audit, eBPF build, integration, security)

### Known Limitations

- QoS EDT (Earliest Departure Time) pacing: delay is tracked in metrics but not enforced in the eBPF datapath (awaiting aya-ebpf `bpf_skb_set_tstamp` API)
- User RingBuf config push: eBPF drain callback is wired, but userspace write requires mmap-based access not yet available in aya 0.13.1
- gRPC is alerts-only (streaming); all CRUD/management operations use REST API
</content>
</invoke>
