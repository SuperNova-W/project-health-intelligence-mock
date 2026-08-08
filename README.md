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

## MongoDB and Authentik

Set `PHI_MONGO_URI` and `PHI_MONGO_DATABASE` to use Beanie/Motor. Production deployments must leave `PHI_DEV_AUTH` disabled and configure `PHI_AUTHENTIK_OIDC_ISSUER_URL` (plus the optional JWKS URL and audience). Authentik roles map to `admin`, `portfolio_leader`, and `project_lead`; project leads are restricted by their `project_ids` claim server-side.

Useful settings include `PHI_AGGREGATION_FLOOR` (default 5), `PHI_RULE_SET_VERSION`, `PHI_GITEA_URL`, `PHI_GITEA_API_TOKEN`, and `PHI_AUTHENTIK_URL`.

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
