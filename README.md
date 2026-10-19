# Newtonite Ops — Roll 23131010259

An internal web app to create, assign, track, and resolve operational work items across teams. Built for the Newtonite "Operations Under Pressure" challenge.

- **Live URL:** https://newtonite-ops-23131010259-production.up.railway.app
- **Repo:** https://github.com/AKASHRAUT108/Newtonite-ops-23131010259

## What it does
- Work items with server-enforced workflows (Open → In Progress → Awaiting Approval → Resolved → Closed).
- Team-scoped RBAC (Viewer, Member, Lead, Admin).
- Concurrency handling: atomic claims (409 Conflict) and optimistic locking (409 Stale Update).
- Idempotent POST requests via `Idempotency-Key`.
- Append-only activity log written in the same transaction as the item change.
- Transactional outbox + worker process for reliable background notifications (with retries and exponential backoff).

## Prerequisites
- Docker Desktop (with Compose v2)

## Run it Locally

1. Copy the environment file:
   ```bash
   cp .env.example .env
   # Edit .env and set JWT_SECRET to a random 32+ char string

2. Start the containers and build the image:

bash
docker compose up --build -d
3. Apply database migrations and seed the data:

bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed
4. Verify it is running:

bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}


Demo Credentials
The seed script creates 10 users across 3 teams with the password password123.

Role	Email
Admin	admin@newtonite.test
Lead (Platform)	lead.platform@newtonite.test
Member (Platform)	member.platform@newtonite.test
Viewer (Platform)	viewer.platform@newtonite.test
Member (Payments)	member.payments@newtonite.test
Running Tests
Run the automated test suite inside the container:

bash
docker compose exec api pytest -q
Expected output: 14 passed. The suite covers concurrent claims, stale updates, idempotency, workflow rules, role-based authorization, and the transactional outbox.

Documentation
Engineering Decisions

API Walkthrough & Architecture

text

### Step 3: Ensure `docs/api-walkthrough.md` exists

Check if you have a `docs` folder with `api-walkthrough.md`. If you don't, create it and paste a brief overview of the curl commands (login, list, claim). The link in the README points here.

### Step 4: Push it all to GitHub

```powershell
git add README.md ENGINEERING_DECISIONS.md
git commit -m "docs: finalize README, add ENGINEERING_DECISIONS"
git push
Step 5: Fresh Clone Test (The Reviewer's Test)
To ensure the reviewer can actually run this, open a new terminal window (not inside your current folder) and run:

powershell
cd C:\
mkdir test-clone
cd test-clone
git clone https://github.com/AKASHRAUT108/Newtonite-ops-23131010259.git
cd Newtonite-ops-23131010259
cp .env.example .env
# (Manually open .env in notepad and set JWT_SECRET=test)
docker compose up --build -d