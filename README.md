# MessMate — Smart Mess Management System

MessMate is a real Flask application for shared student or bachelor messes. It tracks meals, bazar expenses, payments, member balances, monthly meal rates, manager rotation, and auditable month-end statements.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export COOKIE_SECURE=false
export DEMO_MODE=1
python run.py
```

Open `http://127.0.0.1:3000`. Demo mode creates development-only accounts:

| Role | Mess ID | Password |
| --- | --- | --- |
| Admin | `admin` | `DemoAdmin!2026` |
| Manager | `manager` | `DemoManager!2026` |
| Member | `member` | `DemoMember!2026` |

Never enable `DEMO_MODE=1` in production. Demo credentials are intentionally documented only for local testing.

## Database and Supabase

Set `DATABASE_URL` to the Supabase connection string. MessMate uses SQLAlchemy and PostgreSQL `NUMERIC` fields for money and meal quantities. The same code also accepts the managed MySQL-compatible `DATABASE_URL` supplied by a Webdev environment and uses SQLite only when no URL exists, for local development/test convenience. Production persistence must use Supabase or another durable PostgreSQL/MySQL database, never the Render filesystem.

The app creates missing tables safely at startup for this initial release. For a larger deployment, convert the model metadata into reviewed Alembic migrations before applying destructive schema changes. Startup never drops tables or resets existing records.

## Render deployment

1. Push this repository to GitHub.
2. Create a Render Web Service from the repository, using the included `Dockerfile` or `render.yaml`.
3. Add `DATABASE_URL` from Supabase, a long random `SECRET_KEY`, and a one-time `ADMIN_BOOTSTRAP_SECRET` in Render environment variables.
4. Keep `COOKIE_SECURE=true` in production. Render's health check is `/health`.
5. After the service is live, run the bootstrap command from a secure shell or one-off job:

```bash
ADMIN_BOOTSTRAP_SECRET='the-secret-from-render' \
python bootstrap_admin.py --mess-id admin01 --name 'Your Name' \
  --email you@example.com --password 'a-long-unique-password' \
  --secret 'the-secret-from-render'
```

The command refuses to run when an admin already exists and never prints the password. Remove or rotate the bootstrap secret after the first admin is created.

## First-month workflow

1. Sign in as admin and create member accounts in **Members**.
2. Appoint the current member in **Manager assignment**. Assignment dates are bounded to the accounting period and manager actions are period-scoped.
3. The manager records daily meals and bazar expenses. Expenses are pending until an admin approves them; only approved meal-related categories feed the rate.
4. Members submit deposits with unique references. An admin verifies them; pending payments never affect official balances.
5. Review the closing queue and lock the month in **Monthly closing**. Statements and the historical meal-rate snapshot are preserved.
6. Appoint the next month's manager before the next period begins, retaining historical attribution.

## Security notes

- Passwords are Werkzeug hashes, not plaintext.
- Auth uses a database-backed random session token in `webdev_app_session`; the cookie is HttpOnly, SameSite=None, and Secure in public Preview/production.
- State-changing requests require CSRF validation, and login attempts are rate-limited.
- Financial and role changes write to `audit_logs`.
- Duplicate payment references are rejected by validation and a database uniqueness constraint.
- Receipt/object-storage integration is optional and must be configured before accepting files; the core expense workflow remains functional without it.

## Available routes

`/health`, `/manus-routes.json`, `/dashboard`, `/member/statement`, `/member/meals`, `/member/bazar`, `/member/payments`, `/notifications`, `/manager/meals`, `/manager/bazar`, `/manager/cashbook`, `/manager/handover`, `/admin/members`, `/admin/manager`, `/admin/closing`, `/admin/audit`, and `/reports/export.csv`.

## Tests

Run `pytest -q`. The test suite uses an isolated SQLite database and verifies login/logout, authorization, manager assignment behavior, rate/balance calculations, duplicate payment prevention, and monthly locking.

## Honest limitations in this release

Payment gateways, email/Telegram notifications, full receipt uploads to object storage, CSV member import, and month creation/reopening UI are configuration-ready follow-up work rather than falsely simulated integrations. The implemented core workflow does not claim that an external payment was received automatically.
