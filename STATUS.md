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

## Live ingestion path

The pull-only pipeline is wired end to end and covered by `tests/test_live_pipeline.py`,
which drives the real adapters against an in-process fake Gitea and asserts that a
week-segmented backfill yields an evidence-backed warning.

| Stage | Entrypoint | Notes |
| --- | --- | --- |
| Team hierarchy pull | `run_nightly_sync` | Runs first; stages the team sizes the floor gate reads. |
| Repo activity pull | `run_nightly_sync`, `run_weekly_backfill` | ISO-week-aligned windows; boundary and team-size resolvers injected from `backend/resolvers.py`. |
| Fold to modelled rows | `fold_staging_activity` | One row per project, repo, and week; the in-progress week is refreshed in place. |
| Scoring | `generate_weekly_snapshots` | History is truncated at the week being generated, so replayed weeks are scored against only their own past. |
| Operator CLI | `scripts/run_jobs.py` | `backfill`, `nightly`, `weekly`; JSON run reports, preflight configuration check. |

The repository also includes a Docker-backed live test (`compose.live-test.yaml`
and `scripts/run_live_stack_test.py`). It exercises the actual People Portal
server and its seeded Mongo data, real Gitea HTTP APIs, persistent dashboard
Mongo writes, the catalog/activity folds,
snapshot scoring, warning evidence, and the frontend-facing API. Its Gitea seed
hosts snapshots of the adjacent People Portal UI/server and Corp Wiki codebases
alongside synthetic portfolio repositories.

Four defects found while connecting this path were fixed rather than worked around:

1. `backfill()` replayed the whole range as one window, producing a single weekly
   observation. The rules require at least four prior weeks, so no warning could ever
   fire. Replay is now segmented per week (`run_weekly_backfill`).
2. The adapters write synchronously while `BeanieStore` exposes async Motor
   collections, so every staged write was a discarded coroutine and nothing persisted.
   Ingestion now writes through a blocking pymongo handle (`backend/staging.py`).
3. Raw adapter rows and `RepoActivityDocument` had incompatible shapes for the same
   `repo_activity` collection, so the snapshot job could not read what ingestion wrote.
   Raw rows now land in `repo_activity_staging` and are folded into the modelled shape.
4. Review latency and contributor counts accumulated over every pull request the
   repository had ever had, making them lifetime averages that were identical in every
   window and therefore incapable of forming a trend. Both are now windowed.

## Explicit stubs and assumptions

- Local development uses an in-memory repository and deterministic demo fixtures. Beanie/Motor initialization, document indexes, and a repository facade for the API/jobs are present for Mongo deployments; the local path is the verified path in this repository.
- Authentik OIDC JWT validation is implemented for configured production settings; local mode requires the explicit `PHI_DEV_AUTH=true` switch.
- Authentik/ Gitea sync adapters are pull-only and injectable. Upstream API URLs, organization details, and the hosting scheduler are deployment configuration, not hard-coded defaults. The Gitea organization is now read from `PHI_GITEA_ORG` through `Settings` rather than a bare environment lookup inside the job.
- The current job entrypoints are scheduler-ready, but no process-wide scheduler is started by default; deployment must select and supervise the scheduler runtime. `scripts/run_jobs.py` is the supported command surface for that runtime.
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
