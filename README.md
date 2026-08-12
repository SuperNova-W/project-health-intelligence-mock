# App Dev Horizon

App Dev Horizon is a FastAPI backend plus the existing product-vision frontend. The backend serves immutable weekly snapshots, evidence-linked warnings, versioned project boundaries, review feedback, audit history, signal-rule definitions, and pull-only source sync jobs.

## Local development

The local mode uses an in-memory repository with seven aggregate-only demo projects, so MongoDB and upstream services are not required for a first run.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
PHI_ENVIRONMENT=local PHI_DEV_AUTH=true .venv/bin/uvicorn backend.main:app --reload --port 8000
```

In another terminal, serve the frontend:

```bash
npm run dev
```

Open <http://localhost:4173>. The mock defaults to `http://127.0.0.1:8000` for API calls; set `window.PHI_API_BASE` before `app.js` if your API runs elsewhere.

## Frontend authentication

The API reads no cookies; it authenticates with an Authentik OIDC bearer token. With `PHI_DEV_AUTH=true` the server bypasses this, so local development needs no token. Every other deployment must supply one through `window.PHI_API_TOKEN`, set before `app.js` loads:

```html
<script>
  // A string, or a (possibly async) function called per request so an
  // expiring token can be refreshed by the host page's OIDC client.
  window.PHI_API_TOKEN = () => myOidcClient.getAccessToken();
</script>
```

The frontend sends it as `Authorization: Bearer <token>` and leaves the header off entirely when no token is configured. Obtaining and refreshing the token is the host page's responsibility — this mock deliberately implements no OIDC redirect flow of its own.

## Live data

Point the service at a real Gitea organization and People Portal backend, then drive
the pipeline with `scripts/run_jobs.py`. The service starts no scheduler of its
own, so these commands are the supported entrypoints for cron, a systemd timer,
or a Kubernetes CronJob.

```bash
export PHI_MONGO_URI='mongodb://…' PHI_MONGO_DATABASE=project_health_intelligence
export PHI_GITEA_URL='https://gitea.example.org' PHI_GITEA_API_TOKEN='…' PHI_GITEA_ORG='appdev'
export PHI_PEOPLE_PORTAL_URL='https://people.example.org' PHI_PEOPLE_PORTAL_API_TOKEN='…'

scripts/run_jobs.py backfill --weeks 10   # once, to seed baselines
scripts/run_jobs.py nightly               # nightly
scripts/run_jobs.py weekly                # weekly, after the last nightly run
```

Each command prints a JSON run report and refuses to start when the upstream
configuration is incomplete; `--allow-incomplete` overrides that check.

Three things are required before any warning can appear:

- **A boundary record per project.** `POST /boundaries` declares the project's
  root Authentik team and its repositories. Repositories outside every boundary
  are never attributed to a project, so a portfolio with no boundaries renders
  entirely as `insufficient_data`.
- **A backfill before the first snapshot.** Signals compare against a trailing
  8-week baseline and need at least four *prior* weekly observations, so a fresh
  database produces no warnings until roughly five weeks of history exist.
  `backfill` replays Gitea one week at a time to create them; a single wide-range
  replay produces one observation and never opens the gate.
- **Team sizes from People Portal.** Contributor counts are retained only when the
  owning team meets `PHI_AGGREGATION_FLOOR`, and the size comes from the team
  hierarchy pull. Without it, contributor signals stay suppressed by design.

Raw pulls land in append-only staging collections (`repo_activity_staging`,
`repo_activity_evidence`, `authentik_teams`, `gitea_repos`) and are folded into
the modelled `repo_activity` collection the rules read. Staging is the archive;
`repo_activity` is a projection, so the in-progress week is refreshed in place
rather than duplicated. Ingestion writes through a blocking pymongo client
because the adapters are synchronous and run as batch jobs; the API continues to
read through Motor/Beanie.

## Docker-backed People Portal and intelligence live stack

`compose.live-test.yaml` provides a Dockerized `PeoplePortalServer` on
<http://localhost:3100>, the Project Health Intelligence API on
<http://localhost:8000>, a static dashboard on <http://localhost:4173>,
persistent local Gitea on <http://localhost:10000>, and MongoDB on
`localhost:27018`. People Portal local-mock mode seeds 13 teams and 7
project/boundary records into MongoDB. The intelligence service connects to
the internal People Portal endpoints `/api/project-health/teams` and
`/api/project-health/projects`, then pulls repository activity from Gitea.
The Gitea seed uses
snapshots of `../PeoplePortalUI`, `../PeoplePortalServer`, and
`../AppDev-CorpWiki`, creates the other portfolio repositories, and writes ten
weeks of synthetic activity (hundreds of commits) so the baseline rules open.

```bash
docker compose -f compose.live-test.yaml up -d mongodb gitea people-portal-server --build --wait
docker compose -f compose.live-test.yaml exec -T --user git gitea \
  gitea admin user create --username phi-admin \
  --password phi-local-admin-password --email phi-admin@example.invalid \
  --admin --must-change-password=false
.venv/bin/python scripts/seed_live_gitea.py
.venv/bin/python scripts/run_live_stack_test.py

# Start the Dockerized intelligence API and dashboard after the Gitea seed.
docker compose -f compose.live-test.yaml up -d project-health-api project-health-dashboard --build --wait
```

The Gitea administrator command is needed only for a new volume. The seed is
otherwise repeatable: it recreates a read-only API token in the ignored
`.live-test-token` file and force-refreshes the fixture repositories.

Then open <http://localhost:4173>. Stop the stack with
`docker compose -f compose.live-test.yaml down`; add `--volumes` only when an
intentional full reset of the local fixture data is wanted.

## MongoDB and Authentik

Set `PHI_MONGO_URI` and `PHI_MONGO_DATABASE` to use Beanie/Motor. Production deployments must leave `PHI_DEV_AUTH` disabled and configure `PHI_AUTHENTIK_OIDC_ISSUER_URL` (plus the optional JWKS URL and audience). Authentik roles map to `admin`, `portfolio_leader`, and `project_lead`; project leads are restricted by their `project_ids` claim server-side.

Useful settings include `PHI_AGGREGATION_FLOOR` (default 5), `PHI_RULE_SET_VERSION`, `PHI_GITEA_URL`, `PHI_GITEA_API_TOKEN`, `PHI_GITEA_ORG`, `PHI_PEOPLE_PORTAL_URL`, and `PHI_PEOPLE_PORTAL_API_TOKEN`. Direct Authentik team ingestion remains a fallback when People Portal is not configured.

## API surface

- `GET /snapshots/latest` — accessible current queue and project projections.
- `GET /projects/{id}/snapshots` — immutable project snapshot history.
- `GET /projects/{id}/boundary` — point-in-time boundary record.
- `POST /feedback` — review feedback plus an audit entry.
- `GET /audit` — scoped review/audit log.
- `GET /rules` — active rule definitions and version.
- `GET /boundaries` and `POST /boundaries` — admin boundary listing/version creation.
- `GET /health` — service and notification-mode status.

Warnings must include inspectable raw evidence references. Contributor counts and related series are omitted entirely when the configured aggregation floor is not met. Planned pauses short-circuit rule evaluation and are never emitted as risk warnings. No email, Slack, paging, or other outbound notification integration exists.

## Tests

```bash
PHI_ENVIRONMENT=local PHI_DEV_AUTH=true .venv/bin/pytest -q
```

The pure rule tests cover baselines, minimum-data guards, evidence, pause suppression, immutability of inputs, and the aggregation floor. See [STATUS.md](STATUS.md) for the frontend-to-endpoint map, assumptions, and remaining stubs.
