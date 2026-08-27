# EXPRESS OS

A student life operating system: thirteen modules that read and write each
other's data, an assistant (**JOCasta**) that reasons across them, and a
proactive layer (**Spider Sense**) that notices problems before you do.

---

## Quick start

```bash
cp .env.example .env
openssl rand -hex 32          # paste into SECRET_KEY
docker compose up --build
```

| Surface | URL |
|---|---|
| Web app | http://localhost:4310 |
| API | http://localhost:4311 |
| API docs (development only) | http://localhost:4311/docs |
| PostgreSQL | `localhost:4312` |

Seeded demo login: **demo@express.os / expressdemo**

### Why these ports

EXPRESS uses a dedicated **4310–4312** block rather than 3000/8000/5432, so it
never fights another project on your machine for a port. All three are
configurable in `.env` (`EXPRESS_WEB_PORT`, `EXPRESS_API_PORT`,
`EXPRESS_DB_PORT`). If you change the web or API port, update `FRONTEND_ORIGIN`
and `NEXT_PUBLIC_API_URL` to match — the first is the CORS allow-list, the
second is what the browser calls.

---

## Stack

- **Frontend** — Next.js 14 (App Router), TypeScript, no UI framework
- **Backend** — FastAPI, SQLAlchemy 2.x, PostgreSQL 16
- **Auth** — JWT access token + httpOnly refresh cookie, bcrypt hashing
- **Migrations** — Alembic
- **AI** — JOCasta orchestrator over an authorized tool layer; optional Claude
  tool-calling, deterministic planner otherwise

---

## Modules

| Module | Path | Owns |
|---|---|---|
| Command Center | `/` | What matters now; **Fix My Day** |
| Planner | `/planner` | One timeline over every dated thing |
| Tasks | `/tasks` | The canonical queue every module writes into |
| College | `/college` | Semester, courses, timetable, attendance, coursework, exams |
| Learning | `/learning` | Topics, logged study sessions, skills |
| Projects | `/projects` | Projects, phases, project tasks |
| Career | `/career` | Internships and application stages |
| Goals | `/goals` | Goals whose progress is derived from linked work |
| Personal | `/personal` | Notes and habits |
| Finance | `/finance` | Entries and monthly budget caps |
| Memory | `/memory` | Everything JOCasta remembers |
| Progress | `/progress` | One cross-module report |
| Integrations | `/integrations` | OAuth connections |

### How they connect

Everything with a time on it becomes a **Task**, so Planner and Home need no
per-module special cases:

```
Assignment ──┐
ProjectTask ─┼──► Task ──► Planner / Home / Up Next
LearningTopic┤            └──► Spider Sense
Application ─┘
```

Derived values are computed, never stored twice:

| Value | Derived from |
|---|---|
| Goal progress | linked tasks, projects, topics, skills, habits |
| Project completion | phases ticked |
| Habit streaks | `habit_logs` rows, recomputed on every toggle |
| Budget state | this month's entries vs. the cap |
| Attendance | explicit present/absent marks |

Spider Sense consumes the same services the pages render, so a warning and the
screen it points at cannot disagree.

---

## JOCasta

```
User intent → retrieve context → reason → gate → execute → verify → explain
```

**Context** (`app/jocasta/context.py`) is targeted, bounded and user-scoped. A
finance question does not ship your habit history to a model; every slice caps
its rows; `GET /jocasta/context?q=...` shows exactly what JOCasta would see.

**Planning** (`app/jocasta/planning.py`) is a real allocator, not a prompt. It
reads deadlines and genuine free capacity, places work in the latest slot that
still precedes its deadline, and explains every placement. It runs **without an
API key**. It never moves an external deadline — coursework due dates are facts,
so it books work *before* them instead.

**Safety** (`app/jocasta/safety.py`) classifies all 41 tools:

| Risk | Count | Behaviour |
|---|---|---|
| read | 18 | runs immediately |
| write | 18 | routine capture, runs immediately |
| sensitive | 5 | asks first |

Three or more mutations at once also asks. An unclassified tool fails closed as
sensitive. Approval is a signed, user-bound, 10-minute token — it cannot be
forged, replayed by another user, or outlive its window.

```
"help me plan my week"        → allocator → shows the plan → asks
"studied trees for 45 mins"   → log_study
"delete that memory"          → asks first
"what's due?"                 → read-only, never writes
```

Set `ANTHROPIC_API_KEY` to add Claude tool-calling. Tool specs are generated
from the same pydantic schemas the executor validates against, so an advertised
tool can never drift from a real one. Without a key, the deterministic planner
handles everything above, fully offline.

---

## Spider Sense

Every signal carries a severity, an explanation and one suggested action —
anything that cannot justify itself is not raised.

Detectors: schedule conflicts · approaching and overdue deadlines · deadline
collisions · day overload · exams · attendance floor · budget caps · career
deadlines and live interview stages · stale revision topics · slipping projects
· lagging goals · repeatedly postponed tasks · streaks at risk.

Scans are idempotent (`dedupe_key`), self-clearing when a condition no longer
holds, capped at 25 active signals, and one failing detector cannot blind the
others.

---

## Configuration

All configuration is environment-based; nothing is hardcoded. See
`.env.example` for the full annotated list.

`ENV` selects the profile:

| | development | staging / production |
|---|---|---|
| API docs | exposed at `/docs` | disabled |
| Error detail | returned to client | generic message + request id |
| Refresh cookie | `Secure` off | `Secure` on |
| Weak `SECRET_KEY` | allowed | **refuses to boot** |
| Default demo password | allowed | **refuses to boot** |

---

## Database & migrations

Alembic is the source of truth.

```bash
docker compose exec backend alembic upgrade head     # apply
docker compose exec backend alembic revision --autogenerate -m "..."
docker compose exec backend alembic downgrade -1     # roll back one
```

`prestart` handles three cases automatically: an empty database is built from
scratch; a database created by the original pre-Alembic bootstrap is **stamped**
at the baseline (no re-creation, no data loss) and then upgraded; anything
already under Alembic is upgraded normally.

In **development only**, an additive column sync runs afterwards as a safety
net. It only ever ADDs columns and logs loudly when it fires — if you see that
warning, a migration is missing.

Back up before migrating:
```bash
docker compose exec -T db pg_dump -U express -d express > backups/express.sql
```

---

## Security

- Every user-owned query filters by the authenticated user; ownership is
  covered by tests, including cross-user mutation attempts.
- JOCasta has **no database authority**. It proposes tool calls; a server-side
  executor validates arguments against pydantic schemas and runs them scoped to
  the authenticated user. Tools that resolve a human name search only that
  user's rows, and an unmatched name fails loudly rather than guessing.
- OAuth tokens are Fernet-encrypted at rest with a key derived from
  `SECRET_KEY`. No endpoint returns a token; no response model contains one.
- `POST /auth/logout` clears the httpOnly refresh cookie server-side — the
  client cannot do this itself.
- Logs redact anything credential-shaped before it can be written.

---

## Observability

Structured logs (JSON in non-development), each carrying a `request_id` that is
also returned as the `X-Request-ID` header, so one user action traces across
router, service and tool execution.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness. Deliberately does not touch the database. |
| `GET /ready` | Readiness. Reports each dependency; 503 if not serving. |

---

## Testing

```bash
docker compose exec backend pytest -q
# or against the host checkout:
docker run --rm -v "$PWD/backend:/app" -w /app -e SECRET_KEY=testkey express-os2-backend pytest -q
```

**123 tests**, on in-memory SQLite (a portable UUID type and a UTC-normalising
datetime type keep the models backend-agnostic), so no PostgreSQL is needed.

Coverage: authentication and token handling · ownership and cross-user
isolation · every module's CRUD and derived state · the cross-module flows
above · JOCasta context, safety, confirmation and planning · every Spider Sense
detector · OAuth mechanics and token containment.

---

## Status: what is real

**Implemented and verified end to end**
All thirteen modules with real persistence · cross-module flows · JOCasta
context, planning, confirmation and 41 tools · Spider Sense with 13 detectors ·
auth and multi-user isolation · migrations · structured logging · health and
readiness · phone layout.

**Implemented, requires credentials to exercise**
- *OAuth for Google Calendar, Gmail, Drive and GitHub.* The flow is complete —
  authorize URL with PKCE and signed state, callback, code exchange, encrypted
  token storage, refresh, disconnect. It has been tested for its security
  properties but **never run against a live provider**, because that needs real
  client credentials. Set `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` or
  `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` and register the redirect URI shown
  on the Integrations page.
- *Claude tool-calling.* Wired and type-checked against the installed SDK, but
  never executed — no `ANTHROPIC_API_KEY` has been present. The deterministic
  planner is what has actually been exercised.

**Not built**
- Actual *syncing* once a provider is connected. Connecting stores a token;
  nothing reads a calendar or mailbox yet. `last_sync_at` stays null and the UI
  says "no sync has run yet" rather than implying otherwise.
- Notion integration.
- Frontend test suite (no runner is configured; UI behaviour was verified
  manually and through the API).
- Rate limiting, and refresh-token rotation/revocation.

---

## Layout

```
backend/app/models        # 29 tables
backend/app/services      # spider_sense, home, materialize, progress, goals, finance, habits
backend/app/jocasta       # context, planning, safety, tools, planners, orchestrator
backend/app/integrations  # providers, oauth, crypto
backend/app/api/routes    # 16 route modules
backend/alembic/versions  # migrations
frontend/app              # login + 13 module pages
frontend/components       # shell, icons, shared UI primitives
frontend/lib              # api client, auth, types, formatting
```
# EXPRESS
