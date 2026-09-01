# EXPRESS OS

A personal operating system for a student's life — timetable, coursework,
study, projects and goals in one place, with an assistant (**JOCasta**) that can
read and change any of it in plain language, and a proactive signal layer
(**Spider Sense**) that notices what is about to go wrong.

Built for one real user, with one real database. There is no demo mode and no
seeded fiction: every number on screen traces back to something the user
entered or something the system counted.

**Live:** https://frontend-production-33d8.up.railway.app

---

## What it does

| Module | Path | Owns |
|---|---|---|
| Command Center | `/` | What matters right now, and **Fix My Day** |
| Planner | `/planner` | The day itself: classes, study, project work, coursework, personal items |
| College | `/college` | Courses, attendance, modules, concepts, weekly timetable, Drive links |
| Learning | `/learning` | Topics and skills outside coursework, with study time |
| Projects | `/projects` | Projects, phases and their tasks |
| Goals | `/goals` | Goals, with progress derived from the work linked to them |
| JOCasta | `/jocasta` | Chat, voice, attachments — the assistant over everything above |
| Memory | `/memory` | What the user asked to be remembered |
| Progress | `/progress` | Cross-module summary |
| Career · Finance · Personal · Integrations | | Applications, spending, habits, OAuth connections |

`/tasks` redirects to `/planner`. There is no separate task list — a task is a
planner item like any other.

### Two rules the whole system follows

**Derived, not stored.** Goal progress comes from linked work; project
completion from phases; habit streaks from logs; course progress from concepts;
attendance from attended/held counts. Nothing that can be computed is stored and
allowed to drift.

**Counted, not typed.** Attendance is a pair of integers you increment, not a
percentage you type. A course with no classes held shows `—`, never `0%` — no
data is not the same as a failing record, and the two must never look alike.

---

## JOCasta

JOCasta is a pipeline, not a prompt. The model writes language and proposes
tools; it never touches the database.

```
message
  ↓  intent            is this an instruction, a question, or conversation?
  ↓  context           a bounded brief read from the user's real rows
  ↓  planner           Gemini function-calling, else deterministic rules
  ↓  validation        every argument against a pydantic schema
  ↓  safety            destructive? → confirmation token, and stop
  ↓  executor          scoped to the authenticated user
  ↓  verification      re-read what was written
PostgreSQL
```

- **The model never receives a database session**, a user row, or an id it was
  not handed as text in this turn. The SDK's automatic function calling is
  switched off, so proposing a call and running one stay separate steps.
- **A tool name the model invents is dropped** before the executor sees it.
- **Intent gates writes.** A message that was not an instruction to change
  something cannot reach a mutating tool, whatever the planner proposed. This is
  what stops "how are you" becoming a task.
- **Unlisted tools fail closed** — a new tool is treated as destructive until
  someone classifies it.

53 tools across every module. Deletes, reschedules, attendance overwrites and
course edits all require an explicit confirmation.

### The LLM is optional

Google Gemini (`google-genai`, model set by `GEMINI_MODEL`). Without a key —
or when the key is rate-limited, out of quota, or failing — JOCasta falls back
to deterministic rules and templates. Conversation gets less natural. Nothing
breaks.

The College and timetable commands are handled by the **rules** planner on
purpose, not the model: the Gemini free tier allows 20 requests a day, and the
core workflow cannot depend on a quota that runs out mid-morning.

`GET /ready` reports `configured`, `working` and `answering_with` separately and
**makes no API call**. A key being present is not evidence that it works;
conflating the two turns a billing problem into an apparent wiring problem.

### Attachments

PDFs are read for their text layer (`pypdf`, no OCR) and interpreted together
with whatever the user said about them. A timetable, a syllabus, or a question
about the file all take the same path. **Nothing is written without a preview
and a confirmation.**

### Voice

Browser `SpeechRecognition` and `SpeechSynthesis`, feature-detected at runtime.
No audio is ever recorded, buffered or uploaded — the API returns text. Where
recognition is unavailable the UI says so instead of showing a mic that does
nothing. Voice produces a transcript and sends it down the same pipeline as
typed text; there is no second path.

---

## Spider Sense

Thirteen detectors that read real rows and emit signals with a severity, an
explanation and an action — attendance falling toward the floor, a deadline
with no free capacity before it, a habit streak about to break, a conflict in
the timetable. Signals are idempotent via a dedupe key, so a scan on every
mutation does not produce noise.

Red, amber and green belong to Spider Sense. Planner categories use a separate
muted palette (slate, violet, teal, rose, taupe, indigo) so *what a thing is* is
never confused with *how urgent it is*.

---

## Stack

- **Frontend** — Next.js 14 (App Router), TypeScript, no UI framework, no CSS framework
- **Backend** — FastAPI, SQLAlchemy 2.x, PostgreSQL 16
- **Auth** — JWT access token + httpOnly refresh cookie, bcrypt
- **Migrations** — Alembic (`0001` … `0006`)
- **AI** — Google Gemini, with a deterministic planner as the floor
- **Hosting** — Railway: two services plus managed Postgres on private networking

---

## Running it locally

```bash
cp .env.example .env
```

Set `SECRET_KEY` (`openssl rand -hex 32`) and `POSTGRES_PASSWORD`. Optionally add
`GEMINI_API_KEY` from https://aistudio.google.com/apikey — everything works
without it.

```bash
docker compose up -d
```

- Web http://localhost:4310
- API http://localhost:4311 (docs at `/docs` in development only)
- Postgres localhost:4312

Ports avoid the 3000/8000 range on purpose — those are usually already taken.

First boot creates the schema and seeds a demo account (`demo@express.os` /
`expressdemo`) **only when the database has no users**. With real data present
it migrates and leaves everything alone. Both values are development defaults;
production refuses to start with them.

```bash
docker compose exec backend python -m pytest -q      # 481 tests
docker compose exec backend alembic current
```

---

## Tests

**481 backend tests**, no network access required — the Gemini SDK is patched at
`genai.Client`, so the real provider code runs against a fake transport.

Coverage worth knowing about: intent classification and the write guard; the
confirmation layer; ownership isolation between accounts; attendance arithmetic
including the zero-held case; timetable → planner propagation; course delete
scope; attachment parsing against a genuine PDF built in-memory; and every
provider failure mode (missing key, network error, refusal, empty reply, rate
limit) landing on the deterministic path.

```bash
cd frontend && npx tsc --noEmit && npm run build
```

---

## Layout

```
backend/app/
  api/routes/     one module per feature area
  jocasta/        intent · context · planner_rules · planner_llm · llm · brain
                  · safety · tools · orchestrator · attachment
  services/       derived values, Spider Sense, materialisation, time
  models/         SQLAlchemy tables
  tests/          19 test modules
frontend/
  app/            one directory per destination
  components/     shell, ui primitives, icons, states
  lib/            api client, types, auth, voice
```

`app/jocasta/llm.py` is the only place the application talks to a language
model. Swapping providers means changing that file and nothing else — which is
how this codebase moved from Anthropic to Gemini.

---

## Deployment

Railway, from this repository's production Dockerfiles:

```bash
railway up --service backend
railway up --service frontend
```

Topology lives in `.railway/railway.ts` (services, root directories, Dockerfile
paths, healthcheck). The dev `Dockerfile`s next to the `.prod` ones are what
docker-compose builds locally and are unchanged.

`NEXT_PUBLIC_API_URL` must be present at **build** time — Next.js inlines
`NEXT_PUBLIC_*` into the client bundle during `next build`, so supplying it only
to the running container leaves the browser calling localhost.

Migrations run in `prestart` before the server accepts traffic, so a deploy
cannot serve against an un-migrated schema.

---

## Honest limitations

- **Gemini free tier: 20 requests/day.** Once spent, JOCasta's conversation
  falls back to templates. Planner and College commands are unaffected.
- **iPhone voice is unverified.** The UI feature-detects and degrades honestly,
  but nobody has confirmed transcription on a physical iPhone — especially in
  standalone PWA mode, where it is historically unreliable.
- **Integrations connect but do not sync.** OAuth stores a token; nothing reads
  a calendar or mailbox yet. `last_sync_at` stays null and the UI says so.
- **Touch targets are 36–40px** against Apple's 44pt guideline. Usable, not
  ideal.
- Attachment parsing needs a **text layer**. A scanned photo of a timetable
  reports that it found nothing rather than guessing.

---

## Security notes

- `.env` is gitignored and never committed. `.env.example` is a template with
  every secret blank.
- The API key is server-side only; no provider credential reaches the browser.
- OAuth tokens are never exposed to the frontend.
- Passwords, tokens and API keys are never logged.
- Production refuses to boot with a placeholder `SECRET_KEY` or the shipped
  `DEMO_PASSWORD`.
