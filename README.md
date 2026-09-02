# 🕸️ EXPRESS OS

A personal life operating system for students that brings timetable, attendance, coursework, study, projects and goals into one place — with an AI assistant (JOCasta) that can read and change any of it in plain language, and a proactive signal layer (Spider Sense) that warns you before things go wrong.

## Features

- Daily planner combining classes, study sessions, project work, coursework and personal items on one timeline
- College workspace — courses, attendance counting, modules, concepts, weekly timetable and Drive links
- JOCasta AI assistant with text chat, voice input and PDF/attachment understanding
- Natural-language control of the whole system ("add DBMS class Monday at 9 AM", "set my attendance to 42 out of 50")
- Confirmation gate before anything destructive — nothing is deleted or overwritten without asking
- Spider Sense alerts for attendance falling below the floor, deadlines with no free time, and timetable clashes
- Learning topics, projects, goals and memory, with progress derived from real work rather than typed in
- Installable PWA — works on MacBook and iPhone from one URL
- No dummy data: every number traces back to something you entered or the system counted

## Tech Stack

**Frontend**
- Next.js 14 (App Router)
- TypeScript
- CSS (no UI framework)

**Backend**
- Python
- FastAPI
- SQLAlchemy 2.x
- Alembic

**Database**
- PostgreSQL 16

**AI**
- Google Gemini (`google-genai`)
- Deterministic rule-based planner as fallback

**Infrastructure**
- Docker + Docker Compose
- Railway (hosting + managed PostgreSQL)

## Project Structure

```
backend/
  app/
    api/routes/      REST endpoints per module
    jocasta/         AI assistant: intent, planner, safety, tools, orchestrator
    services/        Spider Sense, attendance, planner, time utilities
    models/          Database tables
    tests/           481 tests
  alembic/           Database migrations
frontend/
  app/               Pages (planner, college, jocasta, learning, projects, goals)
  components/        Shell, UI primitives, icons
  lib/               API client, types, auth, voice
docker-compose.yml
```

## Installation

Clone the repository:

```bash
git clone https://github.com/POOJIKASRI-V-29/EXPRESS.git
cd EXPRESS
```

Set up environment variables:

```bash
cp .env.example .env
```

Edit `.env` and set `SECRET_KEY` (generate with `openssl rand -hex 32`) and `POSTGRES_PASSWORD`.
Optionally add a `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey) — the app works without it and falls back to the rule-based assistant.

Run everything:

```bash
docker compose up -d
```

- Frontend: http://localhost:4310
- Backend API: http://localhost:4311
- PostgreSQL: localhost:4312

Run the tests:

```bash
docker compose exec backend python -m pytest -q
```

## Live Demo

Frontend: https://frontend-production-33d8.up.railway.app

Backend: https://backend-production-d130d.up.railway.app

## How JOCasta Works

```
your message
   ↓  intent          instruction, question, or conversation?
   ↓  context         a bounded brief read from your real data
   ↓  planner         Gemini function-calling, or deterministic rules
   ↓  validation      every argument checked against a schema
   ↓  safety          destructive? ask first
   ↓  executor        scoped to your account only
PostgreSQL
```

The AI model never touches the database directly. It proposes; the application validates, asks, and executes.

## Screenshots

<!-- Drag screenshots into this section on GitHub to embed them -->

## Notes

- Gemini's free tier allows 20 requests per day. Once used, JOCasta falls back to the rule-based assistant — planner and college commands are unaffected.
- Voice input uses the browser's speech recognition. It works on desktop Chrome, Edge and Safari; on iPhone it is unverified and the UI says so rather than showing a mic that does nothing.
- Integrations store OAuth tokens but do not sync calendars or mailboxes yet.

## Author

Poojikasri V
