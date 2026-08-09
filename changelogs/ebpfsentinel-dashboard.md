# Changelog — ebpfsentinel-dashboard

All notable changes to the web console and control plane are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versioning follows **CalVer**: `YYYY.M.RELEASE` (year, month without leading zero, release index within that month).

Within each release, entries are grouped **Added → Changed → Fixed → Security**.

## [Unreleased]

First public release of the dashboard. Entries describe the product as shipped; the front end was rebuilt on Angular during development and only the final surface is listed.

### Added

#### Control plane

- **Axum server** with a typed configuration, validation, and hot reload over `notify` + `ArcSwap` + `SIGHUP`
- **In-process rustls TLS** with certificate hot reload
- **Unified route surface**: health, static assets, metrics, CORS and CSP
- **Nonce-based CSP middleware** and security headers, with `connect-src` scoped to self plus the OIDC issuer
- **Bearer auth required on `/metrics`**
- **Helm chart** with security hardening, and a distroless image
- **Tauri 2 desktop console** build

#### Identity and access

- **OIDC authorization-code flow with PKCE**, end to end on the server
- **JWKS rotation** and a per-tenant agent JWT minter
- **`TenantScoped<T>` extractor** with a route audit, so a handler cannot forget the tenant boundary
- **Per-tenant whoami identity** driving the front-end session
- **Time-boxed auditor view tokens** with issue, redeem and revoke
- **Tenant admin self-service UI** with role guards and quota gauges, side-sheet detail, warning banners and auto-disable at the limit

#### Agent connectivity

- **Licence-gated agent pool** with TLS pinning and per-tenant fan-out under a scope ACL
- **Agent licence attestation cryptographically verified** rather than trusted from a self-report
- **Agent admission gated on the signed binary-measurement manifest**
- **SSE upstream subscription** with broadcast, an ingest actor and client endpoints, events wrapped in an `agent_id` envelope
- **gRPC alert fan-in** alongside SSE
- **Per-tenant broadcast capacity** with queue metrics, malformed-event counter, and no raw payload echo
- **Reverse proxy and SSE handlers** with a typed generated client

#### History and search

- **`HistoryStore` trait with a ClickHouse implementation**: batched insert and retention purge
- **ClickHouse-optional mode as a first-class deployment**, not a degraded path
- **Retro-IOC search** over ClickHouse with a rate limiter

#### Console

- **Angular 22 SPA** with an app shell, i18n (EN/FR/DE), RBAC and the full route table
- **Overview wallboard**: stat tiles with delta chips, severity donut, MITRE rows, top regions, compliance cards and a 24h incidents chart
- **Alert queue and detail**: filters, virtual table, grouping, bulk actions, severity badges, `j`/`k` navigation, forensic timeline, block-IP action, live SSE
- **Fleet inventory** with an agent detail sheet and configuration push dry-run
- **Network topology** on the agent flow graph, with a selection pane
- **Flow analytics** on the per-record flow query with cross-filtering, directional asymmetry from connection tracking, and metric drift from cached trend reports
- **Feature screens on the agents' real endpoints**: firewall, DDoS, QoS, load balancer, policy routing, NAT, rate limit, IDS, IPS, DLP, L7 deep inspection, DNS intelligence, TLS intelligence, post-quantum TLS, JA4 fingerprints, threat intel, connection tracking, security zones, GeoIP, container awareness, ML detection, automated response, packet capture, forensics, SIEM export, compliance, analytics, aliases, interface groups and VLANs
- **Every dashboard split from its editor**, and each configuration screen linked back to the dashboard it configures
- **Spec-driven configuration forms** bound to a YAML document, with reorderable list editors, named list rows, map-valued settings through key=value fields, and provenance ("where this document came from") with a remove action
- **Rule editors**: IDS regex, L7 patterns, DLP signatures, per-rule MITRE mapping with typeahead, IPS threshold tuning with replay preview
- **Rule lifecycle**: version history, diff and rollback, staged rules with an approve/promote flow, replay against the last 24h with ClickHouse and agent fallback
- **GeoIP world map** with a country drill sheet, and a **MITRE ATT&CK heatmap** with SVG export and a drill sheet
- **Compliance UI** with a framework matrix, per-framework standings, score deltas, findings panel, and server-side PDF generation Ed25519-signed with an iframe preview
- **Audit log and licence screens** with CSV/JSON export
- **SOAR webhook CRUD** with licence gating
- **Notification pipeline** for licence, quota and fleet events, with a bell, inbox, toasts and SMTP email
- **Custom dashboard widget builder**: five widget types on a grid layout
- **Multi-cluster aggregation backend** with a cluster picker
- **Command palette** that runs actions as well as navigating, plus a search palette over every screen
- **White-label multi-brand theming per tenant**, rendered from the assets the server serves
- **Charter design tokens** with density modes, a three-tier sidebar and a contextual topbar
- **Charts** on ApexCharts, with value scales, time axes, mean lines and a mark on the latest sample
- **Accessibility**: WCAG 2.2 AA pass, focus trap, spoken state on status chips
- **Responsive below 1000px** with a nav drawer and folding tables
- **Loading and empty states** given their own treatment rather than a grey sentence
- **Per-route error boundaries** with a client panic uplink

#### Tooling

- **Dual code generation**: `xtask emit-server-openapi` plus progenitor clients for the agent and the server, with `utoipa` annotations across the route surface
- **Docker development loop** with hot reload
- **Synthetic overview data** behind `EBPFSENTINEL_DEMO_DATA`

### Changed

- Agent configuration is served by section and its editors are read-only, so the operator-managed document stays authoritative
- The invented branding write path was dropped in favour of rendering what the server serves

### Security

- CSP `connect-src` scoped to self plus the OIDC issuer
- `/metrics` requires bearer authentication
- SSE malformed events are counted, never echoed back with their payload
