# Engineering Decisions & Trade-offs

## 1. Data Model & History: Append-only Activity Log in the same transaction
**Context:** The brief requires that history can never disagree with the item state.
**Options:** Database triggers, a separate history microservice, or writing to the database in the same application transaction.
**Choice:** I write an `ActivityEvent` row in the exact same SQLAlchemy transaction as the item mutation. If the item update fails, the log rolls back too.
**Trade-off:** Requires the application layer to remember to log, but it avoids the complexity of triggers and guarantees strong consistency.

## 2. Concurrency: Optimistic Locking for Edits, Atomic UPDATE for Claims
**Context:** Two users claiming the same item or editing stale data.
**Options:** Pessimistic locking (`SELECT FOR UPDATE`), or optimistic locking.
**Choice:** For claiming, I used a conditional `UPDATE ... WHERE assignee_id IS NULL RETURNING`. The database serializes the row lock, so exactly one request wins, and the other gets a 409. For edits, I used an optimistic version column.
**Trade-off:** The client must handle 409 Conflict responses by refetching the latest data, but we avoid holding database locks open during slow HTTP requests.

## 3. Authorization: Single Matrix, Server-Enforced
**Context:** Permissions must be strictly scoped per team and per resource.
**Options:** Scatter `if role == ...` checks across routers, or use a centralized matrix.
**Choice:** I created `app/permissions.py` with a single `ACTION_MATRIX` and a `can()` function. Every service method checks this before executing. 
**Trade-off:** It makes the service methods slightly repetitive, but it means we can update permissions in one file. It also made it trivial to ensure the frontend is completely bypassed for security.

## 4. Async Processing: Transactional Outbox Pattern
**Context:** Notifying users shouldn't block the HTTP request, but fire-and-forget tasks can be lost if the server crashes.
**Options:** Celery/Redis, or a Postgres-backed outbox.
**Choice:** A `Job` row is inserted into the `jobs` table in the same transaction as the item mutation. A separate background worker polls `jobs` using `FOR UPDATE SKIP LOCKED`, processes them, and applies exponential backoff on failure.
**Trade-off:** Higher latency (2s poll interval) compared to Redis, but it avoids needing to manage a separate message broker and guarantees no jobs are lost.

## 5. Pagination: Keyset Cursor instead of OFFSET
**Context:** The dashboard needs to handle tens of thousands of items.
**Options:** `LIMIT/OFFSET` or keyset pagination.
**Choice:** Keyset pagination using `(created_at, id)`. The SQL uses `WHERE (created_at, id) < (cursor_ts, cursor_id)`.
**Trade-off:** The frontend has to pass an opaque cursor string instead of a simple page number, but it guarantees consistent O(log n) performance even at deep pages. `OFFSET` would scan thousands of rows and slow down over time.

## Known Limitations
- No sign-up flow (seeded users only, as per the brief).
- Notifications are logged to the console rather than emailed.
- Single worker instance in the Docker Compose setup (though `SKIP LOCKED` allows scaling to N workers).
- Search uses simple `ILIKE` matching. At 10x scale, this would move to Postgres `tsvector`.