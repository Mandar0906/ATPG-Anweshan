# Running APTG

Three pieces: a Postgres database, a FastAPI backend (the CSED+DPGR engine + a thin HTTP
layer over it), and a Next.js frontend. Two ways to run it — pick one.

## Option A: Docker (recommended — one command, works the same on Windows/Mac/Linux)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and
running. From the repo root:

```
docker compose up --build
```

First run takes a few minutes (installing dependencies, building images). When it's ready:

- Frontend: **http://localhost:3000**
- Backend API: **http://localhost:8000** (try http://localhost:8000/students)

The `db` container auto-creates the `aptg` database, `backend` applies the schema and seeds
the three example students on first boot (safe to restart — it detects existing data and
skips re-seeding), and `frontend` is built against the backend's URL. To stop everything:
`docker compose down` (add `-v` to also wipe the database volume and start fresh next time).

If `docker compose up --build` fails partway through, paste me the error output — Docker
build behavior varies slightly by host and this is the one path I could not execute myself
in this environment to pre-verify end-to-end (see note at the bottom of this file).

## Option B: Run everything natively (no Docker)

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+

### 1. Install PostgreSQL and get it running

**Windows**: install from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/).
The installer starts the service automatically and has you set a password for the
`postgres` superuser during setup — remember that password, you'll need it below. (The
`sudo -u postgres ...` commands from Linux/macOS docs don't apply on Windows — there's no
`sudo` there in that sense; the installer's Stack Builder / pgAdmin, or the plain `psql`
client it installs, is how you interact with it.)

Open **SQL Shell (psql)** from the Start menu (installed alongside Postgres), press Enter
through the prompts to accept defaults, enter the password you set, then run:
```sql
CREATE DATABASE aptg;
```

**macOS**: `brew install postgresql@16 && brew services start postgresql@16`, then
`createdb aptg`.

**Linux**: `sudo systemctl start postgresql` (or `sudo service postgresql start`), then
```
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
sudo -u postgres createdb aptg
```

### 2. Point the scripts at your Postgres credentials

The scripts default to `localhost:5432`, database `aptg`, user `postgres`, password
`postgres`. If yours differ (very likely on Windows, where you chose your own password),
set environment variables before running anything below instead of editing code:

**Windows (PowerShell)**:
```powershell
$env:APTG_DB_PASSWORD = "your-actual-password"
```
**Windows (cmd.exe)**:
```
set APTG_DB_PASSWORD=your-actual-password
```
**macOS/Linux**:
```
export APTG_DB_PASSWORD=your-actual-password
```
(Also set `APTG_DB_HOST`, `APTG_DB_PORT`, `APTG_DB_NAME`, `APTG_DB_USER` the same way if
any of those differ too.)

### 3. Install Python dependencies

```
pip install -r backend/requirements.txt
```
(Use a virtualenv if you prefer: `python -m venv venv`, then activate it first.)

### 4. Load the schema and seed data

```
python db/apply_schema.py
python db/seed.py
```
`apply_schema.py` is safe to re-run (skips if already applied); `seed.py` is safe to re-run
too (skips if the `department` table already has rows). To wipe and reseed from scratch:
```
psql -h localhost -U postgres -d aptg -c "TRUNCATE department, course, career_interest_area RESTART IDENTITY CASCADE;"
python db/seed.py
```

You should see: `Seed complete. student ids -> ME(Example1)=1  AE(Example2)=2  MSE(Example3)=3`

### 5. Verify the engine against the PS's three examples

```
cd backend
python tests/run_examples.py
```
Expect `RESULT: 16/16 checks passed`.

### 6. Start the backend API

Still inside `backend/`:
```
uvicorn app.main:app --reload --port 8000
```
Check it: open http://localhost:8000/students in a browser — you should see the three
seeded students as JSON.

### 7. Start the frontend

In a **new** terminal, from the repo root:
```
cd frontend
npm install
copy .env.local.example .env.local        (Windows)
cp .env.local.example .env.local           (macOS/Linux)
npm run dev
```
Open **http://localhost:3000**. Pick a student, click "Generate Roadmap".

## Trying the interesting cases

- **Example1_LateMinorAspirant** (ME): generates a 9-semester plan with the Data Science
  minor and a "Feasible with Adjustment · Degree Extension" badge, plus an alternative
  8-semester no-minor pathway.
- **Example2_CareerFocused** (AE): a plain "Feasible" 8-semester plan front-loading
  robotics-relevant electives.
- **Example3_PrereqBottleneck** (MSE): type `MSEADVELEC` into "Forced elective code" and
  `5` into "Requested semester", then Generate — you'll see the engine refuse semester 5
  (the prerequisite MSE201 isn't cleared yet) and place it in semester 7 instead, with a
  "Feasible with Adjustment · Semester Shift" badge and the reasoning in the explainability
  log below.

## A note on how this was verified

This snapshot was built and tested by running the backend (`uvicorn`) and frontend
(`npm run build` / `npm run start`) natively against a real Postgres instance, and
confirming the API and page both serve real data end-to-end — that's the same code every
Docker container above runs, just not inside Docker itself. The Docker daemon was not
available in the sandbox this was built in, so `docker compose up --build` itself (the
image builds and container networking specifically) could not be executed here, though
`docker compose config` was used to validate the compose file resolves without errors. If
something in the Docker path doesn't work on your machine, Option B will definitely work
and tells you exactly which piece to look at.
