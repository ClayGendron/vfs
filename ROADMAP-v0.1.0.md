# VFS v0.1.0 Roadmap

> Status: draft for review — 2026-05-18
> Owner: Clay (solo)
> Target: **v0.1.0 in ~2.5 months (~11 weeks)**, from current `0.0.22`

---

## 1. What v0.1.0 means

Two goals, decided together:

1. **First credible public/OSS release** — a developer outside this repo can install, run, read the docs, and trust the public API not to churn.
2. **YC / fundraising demo milestone** — there is a compelling, live, end-to-end story to show: real data mounted, queried, browsed, with auth and metrics visible.

These mostly align. Where they diverge, the **demo path wins on schedule** and the **OSS path wins on API/doc quality**.

## 2. The decisions that shaped this plan

| Question | Decision |
|---|---|
| Strategic purpose | Credible public/OSS release **+** YC/fundraising demo |
| Web app scope | **Full console with embedded dashboards** (browser + management + metrics + observability) |
| Enterprise must-haves | **AuthN/SSO (OIDC), RBAC, Audit logging** (deployment artifacts *not* marked must-have) |
| Backend scope | **Postgres + MSSQL co-equal**, Oracle deferred |
| Timeline | **~11 weeks, solo** |

## 3. The unstated prerequisite

VFS today is an **embedded Python library**. There is no server process. A web console, boundary-enforced RBAC, SSO, audit, and OpenTelemetry all require **a service layer**. So the spine of v0.1.0 is:

```
library  →  service (HTTP API + auth)  →  web console + dashboards
```

Everything else hangs off that spine. The service layer is the single highest-leverage piece of work and is on the critical path for five of your six areas.

## 4. Scope reality check (read this)

Full scope as specified — **Postgres+MSSQL parity + full console with dashboards + SSO + RBAC + audit + OTel + service layer + OSS-grade docs — is over budget for one person in 11 weeks** at production quality. This roadmap therefore splits work into:

- **Critical path** — must ship for the YC demo and a credible 0.1.0. Realistically ~9–10 of the 11 weeks solo. Already tight.
- **At-risk / first cuts** — slips to 0.1.x / 0.2.0 if the schedule slips. These are pre-decided so a slip doesn't trigger a scramble.

**Recommended primary cut (please confirm):** keep MSSQL a *supported, tested* backend, but run the **demo and dashboards on Postgres**, and treat full MSSQL parity (multi-hop traversal, trigram phase 4) as a 0.1.x follow-up rather than a 0.1.0 gate. "Co-equal" stays the *destination*; it is not worth blocking the release on solo.

**Recommended scope add (not originally marked must-have):** a minimal **Docker Compose quickstart** (VFS service + Postgres). "A developer outside the repo can run it" and "someone can run the demo" both effectively require this. Full Helm/Terraform stays parked.

## 5. The six areas → where they land

| Your area | State today | Lands in |
|---|---|---|
| 1. Public API on PG + MSSQL | PG/MSSQL backends built; API surface not frozen; multi-mount errors rough | Phase 0 |
| 2. CLI read + write | Query engine + composition built; no shell entrypoint shipped | Phase 1 |
| 3. Activity metrics | None | Phase 3 |
| 4. Observability (OTel) | None; constitution sibling `observability.md` missing | Phase 0 (doc) + Phase 3 |
| 5. Web console + dashboards | None | Phase 4 |
| 6. Enterprise (SSO/RBAC/audit) | `permissions.py` exists; no SSO, no audit, no boundary enforcement | Phase 2 |

## 6. Phased plan (11 weeks)

### Phase 0 — Foundation & API freeze · Weeks 1–2

The release-credibility gate. Nothing public should churn after this.

- **Freeze the public API.** Audit `src/vfs/client.py` surface; write a versioning + deprecation policy; document the supported surface in `docs/reference/api.md`.
- **Land in-flight de-risking work:** story 025 (modularize DB write impl) and story 026 (VFSResult-by-mount + error taxonomy). 026 is a hard prerequisite for clean multi-mount behavior and stable error contracts at the HTTP boundary.
- **Backend parity tracker.** Enumerate every PG-vs-MSSQL behavioral gap (incl. story 011 multi-hop, story 014 phase-4 trigram). Mark each gap `0.1.0-blocking` or `0.1.x`. Apply the §4 recommended cut.
- **Write `context/observability.md`** — the constitution's missing sibling. Defines the telemetry model (what's a span, what's a metric, what's an audited action, and how/whether they are addressable in the namespace).

*Exit:* public API documented and frozen; error taxonomy stable; observability model written; parity decisions recorded.

### Phase 1 — Service layer + shell entrypoint · Weeks 2–4 · KEYSTONE

- **HTTP service** (FastAPI) exposing the frozen public API. `VFSResult`/`Candidate` JSON transport; streaming for large reads; auth/session hook points stubbed (filled in Phase 2).
- **`vfs` shell entrypoint** — console script for read **and** write and full pipelines (`vfs 'grep "login" /workspace | pagerank | top 15'`). Satisfies area 2. `--json`, exit codes.
- Constitutional check: the service exposes the canonical namespace only — no side-channel URL grammar (Article 1).

*Exit:* the library is reachable over HTTP and from a terminal; everything downstream can build on it.

### Phase 2 — Identity & access · Weeks 4–6

- **SSO / OIDC** at the service boundary (Authlib or equivalent). One working IdP path (e.g. Google/Okta) for the demo.
- **RBAC** — extend `permissions.py` to roles/groups; enforce at the service boundary *and* in the CLI, not just in-library.
- **Audit logging** — append-only `actor / action / path / result / timestamp`. Per the constitution's "everything is a file" principle, prefer making the audit trail addressable in the namespace (e.g. under a `/.vfs/...` sidecar) rather than an opaque side store; finalize in `observability.md`.

*Exit:* every API/CLI/console action is authenticated, authorized, and audited.

### Phase 3 — Observability + activity metrics · Weeks 6–7 (overlaps Phase 4)

- **OpenTelemetry** instrumentation: traces (query-pipeline spans, per-backend timings), metrics (op counts, latency histograms, backend latency), structured logs. OTLP export.
- **Activity metrics** — product-level usage (top paths, query volume, active users) derived from the audit stream + OTel. Aggregates queryable for the dashboard.

*Exit:* traces/metrics/logs exported; activity aggregates available to the console.

### Phase 4 — Web console + dashboards · Weeks 5–10 (parallel; uses `frontend-design` skill)

Built in slices so the demo-critical slice ships first and independently.

- **Slice A — Browser (read-only), demo-critical:** namespace tree browser, file viewer, query runner (the four verbs + pipelines), graph visualization. This is the YC demo centerpiece — schedule it to be demoable by ~week 8.
- **Slice B — Management:** mount add/remove, users/roles/permissions, write/edit through the UI.
- **Slice C — Dashboards:** embedded activity-metrics and observability panels (Phase 3 data).

*Exit:* Slice A polished and demoable; B/C as schedule allows.

### Phase 5 — Release engineering · Weeks 9–11

- **Diátaxis docs:** populate `docs/reference/` (API, query DSL, metadata paths), one complete `docs/tutorials/` getting-started, key `docs/how-to/` pages. OSS-credibility gate.
- **Docker Compose quickstart** (service + Postgres) — see §4.
- Versioning/deprecation policy finalized; `CHANGELOG.md`; migration notes from 0.0.x.
- **YC demo script + seed dataset** — a scripted, reliable 5-minute path.
- Cut **v0.1.0**.

## 7. Critical path vs. at-risk

**Critical path (must ship):** Phase 0 (lean) → Phase 1 → Phase 2 (one IdP, RBAC, basic audit) → Phase 3 (traces + key metrics) → Phase 4 Slice A → Docker Compose quickstart → demo script + core reference docs.

**At-risk — pre-agreed cuts to 0.1.x / 0.2.0 if schedule slips, in cut order:**

1. MSSQL full parity (stories 011, 014 phase 4) — keep MSSQL supported/tested, demo on Postgres.
2. Web console Slice C depth (rich dashboards) — ship minimal panels, defer depth.
3. Web console Slice B depth (full management UI) — CLI/API remain the management path.
4. Activity-metrics richness — ship counts/top-N, defer trends/segmentation.
5. MCP single-tool interface — defer (not in the six areas; flag if agent-framework demo is wanted).
6. Story 027 embedded code execution — explicitly post-0.1.0.

## 8. Open decisions for you

1. **Confirm the §4 primary cut**: PG-first for demo/dashboards, MSSQL parity → 0.1.x? (Strongly recommended given solo + 11 weeks.)
2. **Confirm Docker Compose quickstart is in scope** for 0.1.0 (recommended).
3. **Which IdP** should the SSO demo target (Google / Okta / Auth0 / Microsoft Entra)? Pick one for the demo; generalize later.
4. Is an **agent-framework integration (MCP)** needed in the YC demo narrative? If yes, it moves up from the cut list.
5. Should activity metrics + audit be **addressable in the namespace** (constitutionally consistent) or a separate store? Resolved in `context/observability.md`, but your instinct sets direction.

## 9. Next step

On your go, I'll generate the implementing story specs under `context/stories/` (next free number is **028**): service layer, shell entrypoint, OIDC, RBAC, audit, OTel, activity metrics, and the web-console slices — sequenced per this roadmap.
