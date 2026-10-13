# MessMate implementation plan

## Scope and delivery approach

MessMate will be implemented as a real Flask application with server-rendered Jinja templates, progressively enhanced vanilla JavaScript, a normalized SQLAlchemy data model, and a responsive CSS design system. The app will use `DATABASE_URL` at runtime so Render can connect to Supabase PostgreSQL; a SQLite fallback is allowed only for local development and test runs. No financial records will be stored in browser localStorage or in the production filesystem.

The first delivered build will be a coherent end-to-end product slice rather than a set of disconnected screens:

1. Secure login/logout and backend-enforced roles for admin, manager, and member.
2. Seed-safe bootstrap workflow with no hardcoded production credentials.
3. Admin overview, member management, manager assignment, settings, audit log, and monthly closing controls.
4. Manager daily meal entry, bazar entry/approval, cashbook, and handover views.
5. Member dashboard, statement, meal/bazar/payment history, monthly reports, notifications, and correction requests.
6. Decimal-safe monthly calculation engine for meal rates, common-expense allocation, balances, deposits, refunds, dues, and locked historical statements.
7. REST-style JSON endpoints for state-changing actions with validation, CSRF checks, permission checks, audit events, and duplicate-payment protection.
8. Deployment files, migration/bootstrap CLI, automated tests, health endpoint, route manifest, and beginner-friendly Supabase/Render documentation.

Optional integrations such as email, Telegram, and actual payment gateways will remain configuration-ready but will not be falsely represented as active. Receipt uploads will validate type and size and store a durable object reference when platform storage credentials are available; otherwise the expense record remains functional without a receipt.

## Architecture

- `app.py`: Flask application factory, middleware, route registration, health endpoint, error handling, security headers compatible with embedded Preview, and session configuration.
- `config.py`: environment-driven settings, database URL normalization, BDT/timezone defaults, upload limits, and cookie policy (`webdev_app_session`, HTTPS Preview-compatible `SameSite=None; Secure`).
- `models.py`: SQLAlchemy models, relationships, constraints, indexes, and enums for users, role assignments, periods, managers, meals, corrections, categories, expenses, payments, deposits, refunds, statements, closings, cashbook, announcements, notifications, and audit logs.
- `security.py`: password hashing, login rate limiting, CSRF token generation/validation, session lifecycle, role decorators, and manager-period checks.
- `services/accounting.py`: Decimal-based approved-expense totals, meal-rate calculation, common-expense allocation, member balances, statement snapshots, close/reopen rules, and carry-forward logic.
- `services/audit.py`: immutable audit entries for financial edits, approvals, reversals, role changes, manager assignments, and closing/reopening.
- `services/storage.py`: safe receipt validation and optional platform-storage integration; database stores the file key and stable URL, not local permanent files.
- `routes/auth.py`, `routes/member.py`, `routes/manager.py`, `routes/admin.py`, `routes/api.py`: focused page and JSON routes with backend authorization.
- `templates/`: shared shell, login, dashboards, tables, forms, print statement, 403/404/500 pages.
- `static/css/app.css`: navy/charcoal, soft-white, teal/emerald design system with mobile-first breakpoints.
- `static/js/app.js`: navigation, modal/form helpers, flash messages, table filtering, notification state, and progressive enhancement.
- `migrations/`: additive schema initialization/versioning and seed-safe bootstrap metadata.
- `tests/`: pytest coverage for auth, roles, manager rotation, calculations, payments, closing, history, and error handling.

## Design direction

### Design movement
A restrained **editorial fintech dashboard**: information-dense but calm, with strong typographic hierarchy and a premium operations-console feel instead of a generic admin template.

### Core principles
- **Trust before decoration:** balances, approvals, dates, and ownership are always explicit.
- **Calm density:** compact data tables are paired with generous section spacing and strong grouping.
- **Progressive disclosure:** quick actions first; correction reasons, audit trails, and breakdowns remain one click away.
- **Operational clarity:** states use consistent badges, warnings are actionable, and locked periods look visibly immutable.

### Color philosophy
Deep ink navy provides authority and readability; warm off-white surfaces prevent the interface from feeling cold; a distinctive teal-green acts as the brand signal for confirmed money movement and healthy operations. Amber is reserved for review states and red for destructive or overdue states.

### Layout paradigm
A command-center shell: collapsible left rail for modules, a slim top context bar for accounting month and user state, and content sections that use asymmetric summary bands followed by full-width operational tables. On mobile the rail becomes a bottom action strip and tables collapse into stacked record cards.

### Signature elements
1. A small **meal-ring motif**: circular progress/rate visuals used for month health and meal coverage.
2. **Ledger rails**: subtle vertical accent rules that distinguish credits, debits, and review items in statements.
3. **Period lock markers**: compact lock/date chips that make finalized months feel safely immutable.

### Interaction and animation
Every mutation provides immediate inline validation, a visible pending state, and a success or failure message. Transitions are short (150–220ms), using opacity/translate rather than expensive layout animation. Focus rings remain visible. No animation is required to understand a financial result.

### Typography system
Use a high-legibility sans family stack with `Inter`/system fallback for UI and `IBM Plex Mono`/system monospace for IDs, references, and ledger numerals. Headings are semibold with tight tracking; body copy is regular and compact; currency values use tabular numerals.

### Brand essence
**MessMate is the transparent month-end command center for shared messes—built for members who want every meal and taka to add up.** Personality: precise, grounded, reassuring.

### Brand voice
Headlines are direct and operational; CTAs state the next action and its effect. Examples: “This month, every taka accounted for.” and “Review the 14 items waiting for approval.”

### Wordmark and logo
A compact “M” mark formed from two joined ledger rails and a small meal dot, paired with the MessMate wordmark. It should work as a one-color favicon and as a teal-on-navy brand mark.

### Signature brand color
**MessMate Teal — `#14B8A6`**, used sparingly for confirmed states, active navigation, and the logo mark.

## Data and security decisions

- Monetary and quantity fields use SQL `NUMERIC`/Python `Decimal`; rounding is centralized for BDT.
- Only approved expenses and verified payments enter official statements.
- Locked periods use application checks plus database constraints where practical; authorized reopening creates an audit event.
- No public registration. Admin bootstrap requires `ADMIN_BOOTSTRAP_SECRET` and creates the first admin only when no admin exists.
- Passwords use Werkzeug `scrypt`/PBKDF2-compatible hashing; sessions are server-side signed and use the reserved Preview-compatible cookie name `webdev_app_session`.
- All state-changing forms and JSON requests require CSRF validation; all sensitive routes use role decorators and object ownership checks.
- Login attempts are rate-limited in a bounded server-side store; the durable audit log records successful and sensitive actions without storing passwords or secrets.
- Receipt upload paths are randomized and validated; application records retain ownership metadata and can be soft-hidden.

## Build workflow

1. Create the Flask package, templates, CSS/JS, route manifest, environment example, README, Dockerfile, Gunicorn entrypoint, and test configuration.
2. Implement schema and safe initialization/migration flow, then auth and role enforcement.
3. Implement accounting services and test calculations with Decimal before wiring dashboards.
4. Add admin, manager, and member routes/forms using the shared shell and responsive design system.
5. Add history, reports, CSV export, notifications, audit views, monthly closing/reopening, and print stylesheet.
6. Run pytest, compile checks, database initialization checks, Gunicorn startup, `/health`, and `/manus-routes.json` verification.
7. Configure Webdev deployment declaration with `Dockerfile` and `/health`, create a checkpoint, and provide the Preview URL unless publication is separately requested.

## Assumptions recorded

- English is the default UI language; labels are centralized so Bangla can be added later.
- The app ships with a development-only demo dataset behind an explicit `DEMO_MODE=1` guard; production never seeds fake financial transactions.
- Supabase credentials are supplied later as protected deployment environment variables, never committed to the repository.
- Because a native PowerPoint deliverable is irrelevant to this web build, no presentation artifact is created.
