# App Dev Horizon implementation status

## Frontend surface map

| Frontend surface | API source | Status |
| --- | --- | --- |
| Overview and attention queue | `GET /snapshots/latest` | Connected; queue contains only evidence-backed warnings. |
| Project inventory | `GET /snapshots/latest` | Connected; status, coverage, and last-sync metadata are rendered. |
| Insights | `GET /snapshots/latest` | Connected; aggregate metrics only. |
| Project profile and evidence | `GET /projects/{id}/snapshots`, `GET /projects/{id}/boundary` | Connected; immutable snapshot metadata and raw-evidence references are shown. |
| Feedback modal | `POST /feedback` | Connected; warning/snapshot/project linkage and audit write are enforced server-side. |
| Review log | `GET /audit` | Connected; role-scoped. |
| Project boundaries | `GET /projects/{id}/boundary` | Connected for reads; admin version creation is available through `POST /boundaries`. |
| Signal rules | `GET /rules` | Connected read-only view. |
| Data coverage card | Snapshot `data_completeness_pct` and `last_sync_at` | Connected. |

## Explicit stubs and assumptions

- Local development uses an in-memory repository and deterministic demo fixtures. Beanie/Motor initialization, document indexes, and a repository facade for the API/jobs are present for Mongo deployments; the local path is the verified path in this repository.
- Authentik OIDC JWT validation is implemented for configured production settings; local mode requires the explicit `PHI_DEV_AUTH=true` switch.
- Authentik/ Gitea sync adapters are pull-only and injectable. Upstream API URLs, organization details, and the hosting scheduler are deployment configuration, not hard-coded defaults.
- The current job entrypoints are scheduler-ready, but no process-wide scheduler is started by default; deployment must select and supervise the scheduler runtime.
- Staffing/role data is not used for signals; the implementation assumes Authentik team membership is the only available team-size source.
- The identity-map seed command performs ephemeral matching and writes only aggregate run metadata. It does not persist usernames, user ids, emails, or ambiguous matches.
- The frontend keeps the existing visual structure but does not invent historical portfolio pulse data when the API does not return it.
- No Phase 5 / ML work was started.

## Open questions from IMPLEMENTATION_PLAN.md §7

1. Named executive sponsor: still unresolved; this build proceeds ahead of the Phase 0 gate as requested.
2. Authoritative staffing/role source: assumed to be Authentik team hierarchy for aggregation eligibility; People Portal staffing signals remain deferred.
3. Gitea rate limits/webhooks: assumed polling is sufficient for the adapter contract; webhook deployment remains open.
4. Weekly job runtime: assumed an external scheduler invokes the provided job entrypoints; no notification channel is added.
5. Aggregation floor: defaulted to 5 in code and configuration; product/legal should confirm the final value.
