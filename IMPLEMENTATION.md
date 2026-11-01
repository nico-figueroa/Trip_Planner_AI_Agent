# Deployment and administration

## 1. Choose a deployment

| Environment | Application hosting | Persistent data | Semantic search |
|---|---|---|---|
| Local development/testing | Python + Streamlit | Local PostgreSQL | Local CPU model and in-process vectors |
| Streamlit Community Cloud | Managed Streamlit app | Supabase PostgreSQL through server-only REST | Prepare local model using administrator UI |
| Azure | Containerized Streamlit, e.g. Azure App Service | Supabase PostgreSQL through server-only REST | Model prepared in container image |

Anonymous planning, refinement, comparison, expenses, and PDF/JSON downloads
work without an account. Optional OIDC sign-in enables private saved-plan
loading/saving. POI votes require sign-in to prevent repeated anonymous votes.
Written itinerary feedback can be anonymous; proposed instruction changes
always need administrator approval.

Local JSON/JSONL files from previous releases are preserved, but the app no
longer automatically loads shared local itineraries into public sessions.
Cloud accounts use PostgreSQL JSONB; local cloud-host disks are not backups.

## 2. Local development and PostgreSQL setup

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\requirements.txt
```

Use the existing gitignored `trip-planner/.env`. Configure these settings
locally, never in chat or source control:

```dotenv
OPENAI_API_KEY=your-openai-key
GEOAPIFY_API_KEY=your-geoapify-key
POSTGRES_ADMIN_URL=postgresql://postgres:URL_ENCODED_PASSWORD@localhost:5432/postgres
DATABASE_URL=postgresql://postgres:URL_ENCODED_PASSWORD@localhost:5432/trip_planner
TEST_DATABASE_URL=postgresql://postgres:URL_ENCODED_PASSWORD@localhost:5432/trip_planner_test
```

Passwords containing punctuation must be URL-encoded in connection URIs.
Alternatively configure PostgreSQL's `pgpass` file and omit passwords from the
URIs. Restrict file permissions. Administrator credentials are allowed only for
local development, as explicitly chosen for this project.

Create the two dedicated databases and apply the common schema:

```powershell
python .\deploy\init_local_db.py
```

This script creates only `trip_planner` and `trip_planner_test` if absent,
applies [schema.sql](./deploy/schema.sql), and **does not create or alter roles**.
It does not drop databases, tables, or existing records. Run with an
administrator connection that has CREATE DATABASE permission. Existing schema
changes in future releases need explicit migration scripts; `IF NOT EXISTS`
does not upgrade arbitrary old table definitions.

The application chooses `DATABASE_URL` first. If absent, it uses
`SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY`. With neither configured,
anonymous planning still runs but persistent saves/feedback are disabled.
Do not put a development localhost DSN into a cloud deployment.

Prepare the public semantic model once:

```powershell
python .\deploy\prepare_model.py
streamlit run app.py
```

The default model directory is `models/all-MiniLM-L6-v2` at the repository root.
Set `RAG_MODEL_PATH` to override it. Inference uses CPU, local weights, and
`trust_remote_code=False`; preparation downloads the public
[all-MiniLM-L6-v2 model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
Observe its license and attribution. No OpenAI embedding calls are made.
Missing weights or retrieval failure produce an explicit optional-guide result,
not an unreported substitute lexical search.

### Optional local sign-in

Use [secrets.example.toml](./deploy/secrets.example.toml) as a template, not real
credentials. Native Streamlit OIDC requires an `[auth]` section containing
`redirect_uri`, `cookie_secret`, `client_id`, `client_secret`, and
`server_metadata_url`. Use a real OIDC provider such as Google, Microsoft
Entra ID, or Auth0; generic OAuth-only providers are not supported.

For a root launch, place real configuration in the gitignored root
`.streamlit/secrets.toml`. The existing project file is under
`trip-planner/.streamlit/secrets.toml`; it is found when launching from that
directory:

```powershell
Push-Location .\trip-planner
streamlit run app.py
Pop-Location
```

Register `http://localhost:8501/oauth2callback` with the identity provider for
local development. Use a long, random `cookie_secret`. Do not commit the real
TOML file. API and database settings remain `.env`/environment lookups; only
OIDC configuration is read directly through `st.secrets`.

Sign-in starts a new browser session. Sign in before generating a plan you
intend to save, or use **Export plan JSON**, sign in, **Import into this
session**, then **Save itinerary**. Keep exports private. The importer also
accepts the `active_itinerary` from a legacy `app_state.json`; it does not
assign a legacy shared account state to arbitrary users.

## 3. Create or migrate Supabase storage

1. Create/select a Supabase project in the administrator dashboard.
2. In its SQL editor, run [schema.sql](./deploy/schema.sql).
3. Then run [supabase.sql](./deploy/supabase.sql) to apply role grants.
4. Obtain the project HTTPS URL and server-side **service-role** API key.
   A browser publishable/anon key is intentionally insufficient.
5. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the hosting
   environment/secrets. Do not expose the service key in widgets, logs,
   JavaScript, or exported plans.

These steps apply the same initial schema used locally. Alternatively run the
two files as ordered SQL migrations through your existing Supabase CLI workflow.
No project is provisioned and no remote migration is run automatically by this
repository.

Tables:

- `planner_accounts`: owner hash and JSONB state with saved plans/expenses.
- `planner_feedback`: explicit ratings/comments, deduplicated by
  actor + plan + POI.
- `planner_guidance`: review proposals and pending/approved/rejected decisions.

RLS is enabled, with no public browser policies. `anon` and `authenticated`
roles have no direct table/RPC access. The trusted Streamlit backend uses the
service role and filters private state by a SHA-256 hash of the **verified OIDC
issuer and subject**, never by an email or account ID supplied in a widget.
This is a server-side authorization architecture, not Supabase browser auth.
The service role bypasses RLS, so keep the backend and its credentials trusted.

For migration of personal legacy plans, use the private JSON import workflow
after sign-in. Do not bulk-assign the old shared JSON file to all accounts.
Configure Supabase backups according to your service plan, retention needs,
and budget; test restoration before depending on durable storage.

## 4. Streamlit Community Cloud

1. Push application changes, **not** `.env`, real `secrets.toml`, data, exports,
   or model weights. The root [requirements.txt](./requirements.txt) delegates
   to the implementation's dependencies.
2. Create a Community Cloud app for this repository with entry point `app.py`.
3. Select the tested Python runtime, 3.14, if offered. The local validation
   runtime is Python 3.14.6. If Cloud does not offer a compatible runtime, first
   validate the dependencies on an offered version or use Azure's pinned
   container; do not assume a lower version passes.
4. In Advanced settings / Secrets, use the contents of your **gitignored**
   `secrets.toml`, based on the deployment template. Top-level scalar settings
   become environment variables in Streamlit. This is the administrator-approved
   cloud provisioning path; application API key resolution still reads `.env`
   and the environment, not API key entries through `st.secrets`.
5. Include OpenAI/Geoapify keys, Supabase URL/service-role key, and
   `ADMIN_PRINCIPALS` as top-level values. **Omit** `DATABASE_URL`,
   `TEST_DATABASE_URL`, and `POSTGRES_ADMIN_URL` from cloud secrets. Local
   PostgreSQL is not reachable as localhost from Cloud.
6. Add `[auth]` and register the actual app HTTPS URL plus `/oauth2callback`
   with your identity provider. Configure the same redirect URI in both places.
7. Deploy, sign in as a configured administrator, and select
   **Administrator: local semantic model → Prepare local semantic model**.
   This downloads weights once into the running app's filesystem. Repeat
   preparation after a rebuild if local weights were removed.
8. Verify the acceptance checks below.

Local semantic inference adds substantial PyTorch dependencies, memory use,
model preparation time, and cold starts. Monitor the hosting tier's current
limits. If it cannot fit the model, use Azure with adequate memory; optional
RAG failure must not be mistaken for functioning vector retrieval.

## 5. Azure container deployment

The included [Dockerfile](./Dockerfile) packages the app and prepares semantic
weights during build. [.dockerignore](./.dockerignore) excludes credentials
and runtime/user data. Docker Desktop/Engine must be running for local builds.

```powershell
docker build -t trip-planner:latest .
docker run --rm -p 8000:8000 --env-file .\trip-planner\.env trip-planner:latest
```

For a local container, localhost in `DATABASE_URL` refers to the container, not
the Windows host. Use `host.docker.internal` with suitable PostgreSQL access
controls, or omit `DATABASE_URL` and use Supabase. Do not expose a development
administrator database connection outside the machine.

For Azure App Service using a Linux custom container:

1. Choose the subscription/resource group, region, container registry, and
   hosting plan as administrator. These services may incur costs.
2. Build/push the image to the selected registry; create the web app from it.
3. Configure container port `8000` (`WEBSITES_PORT=8000` where required by the
   selected App Service container mode). The image also supports `PORT`.
4. Configure OpenAI/Geoapify keys and Supabase settings as App Service
   environment settings, preferably Azure Key Vault references using managed
   identity. Do not bake secrets into the image or its build arguments.
5. Put the native `[auth]` TOML content in the secret environment setting
   `STREAMLIT_AUTH_TOML`. [start_cloud.py](./deploy/start_cloud.py) writes it to
   `.streamlit/secrets.toml` with restricted permissions before launching
   Streamlit. Include the Azure HTTPS callback URL, matching the IdP registration.
   Alternatively mount a protected native TOML file.
6. Enable HTTPS-only access and WebSocket support as appropriate for the
   chosen hosting configuration. Keep Streamlit's XSRF/CORS protection enabled.
7. Configure health probing at `/_stcore/health`, logging, restart policy,
   memory limits, and scale settings.
8. Start with a single instance and monitor memory/latency. PostgreSQL keeps
   private state durable; local vectors are per-process caches.

Azure Container Apps can host the same image: expose port 8000 with HTTPS
ingress and configure the same environment/secret settings. Verify WebSockets,
health probes, memory, and cold-start behavior for the selected tier.

## 6. Administrator feedback workflow

Configure `ADMIN_PRINCIPALS` as a JSON string containing exact
`[issuer, subject]` pairs from verified OIDC identities, e.g.:

```toml
ADMIN_PRINCIPALS = '[["https://your-issuer", "administrator-subject"]]'
```

Do not use emails or allow UI users to set their own roles.

Written feedback triggers one bounded model review. Actionable proposals
remain **pending**; empty/vague/manipulative feedback may be rejected.
Negative tone alone does not establish falsity. Review cannot prove every
factual complaint true or false; uncertain claims should prompt verification,
not become assumed facts.

Administrators inspect proposals and approve/reject them in the UI. Review
personal details, factual support, and effects on current-user constraints
before approval. Only the latest eight approved advisory instructions (at most
300 characters each) are incorporated into future planning/retrieval requests.
Core system instructions, date constraints, credentials, and tool safety are
not rewritten. Changing feedback resets its proposal for fresh review.

POI boosts are applied to fresh rankings **outside** cached retrieval:
`base score + 0.25 × upvotes − 0.35 × downvotes`. One latest vote per signed-in
actor/POI is counted across plans; repeated votes cannot stack. Base scores
preserve Geoapify candidate order on a 0–1 scale. This changes the order of
retrieved candidates, not the provider's coverage or routing accuracy.

## 7. Validation and operations

Offline regression suite:

```powershell
Push-Location .\trip-planner
python -m pytest -q -W error
Pop-Location
```

Database integration after creating/configuring `trip_planner_test`:

```powershell
Push-Location .\trip-planner
python -m pytest -q tests\test_postgres_integration.py
Pop-Location
```

Without `TEST_DATABASE_URL`, the database integration test is explicitly
skipped. It rejects any database name other than `trip_planner_test` and
cleans up only its generated rows, never existing user data or tables.

Before production acceptance verify:

- Anonymous generation succeeds; accounts are optional.
- OIDC callbacks, logout, and two-user isolation work with real provider setup.
- Saved plans/expenses survive an app restart on the selected database.
- Wikivoyage trace returns semantic passages and source URLs, not just a fallback.
- Date range overrides duration inclusively and displays the adjustment.
- Single-day regeneration keeps other days unchanged, including legacy plans.
- Day/output/map-style filters preserve the underlying itinerary.
- Beach stops have verified coordinates; unresolved names are reported.
- Path lines follow visit order; they are **not** calculated driving directions.
- Expenses/remaining totals are separate from model estimates, which are not quotes.
- Alternatives run only on explicit request with sidebar enabling and incur extra API calls.
- Feedback counts/votes persist; only administrators can approve guidance.
- Image contents/logs/exports do not contain credentials.

The application bounds provider timeouts and tool budgets but does not provide
an availability or latency SLA. Anonymous planning exposes paid server-side
API actions; set provider quotas and deployment-level rate/access controls
appropriate to your intended audience. Monitor both model spending and hosting
costs.

### Validation limitations at implementation time

Offline tests, the local semantic model, and live Wikivoyage vector retrieval
were exercised. Local PostgreSQL administrator authentication was unavailable;
database creation was deferred pending credentials, with no role changes.
Supabase migrations and real OIDC callbacks require administrator-provided
configuration. Docker is installed, but its daemon was not running, so no
container build or Azure/Community Cloud deployment is claimed as verified.
