# Development

Layout, layering, and the commands that work on a fresh clone. Coding style, docstrings, and environment rules are in [guidelines.md](guidelines.md).

## Layout

```
AGENTS.md
README.md
pyproject.toml
.gitignore
.env.example
docs/v0.1-spec.md
docs/development.md
docs/guidelines.md
src/neodermo/__init__.py          # create_app
src/neodermo/config.py
src/neodermo/extensions.py        # db = SQLAlchemy()
src/neodermo/models/               # establishment, patient, stay, wound, assessment
src/neodermo/api/health.py
migrations/                       # Flask-Migrate / Alembic
tests/conftest.py
tests/test_health.py
var/                              # gitignored runtime SQLite and later uploads
```

Keep the application as one Python package named `neodermo` under `src/`. Do not add a frontend, Docker, or extra frameworks in this first slice.

## Layering

- Routes translate HTTP. They parse requests and return responses.
- Application functions own rules. Validation and lifecycle checks live here once they exist.
- SQLAlchemy models own persistence.

Python modules use `snake_case`. Document JSON fields and HTTP paths when they are added. Do not add a repository layer or a shared client framework for a future Android app. Keep the Flask code idiomatic and small.

Branch names use a purpose prefix: `feat/`, `doc/`, `fix/`, and similar.

## Configuration and data

- Read `SECRET_KEY` and `DATABASE_URL` from the environment. Commit `.env.example`, never a real `.env`.
- Runtime SQLite and later private uploads live under `var/`. Do not put care data in `static/` or Git.
- Tests must use a separate database path. `pytest` must never create or modify the configured runtime database.
- Schema changes use Flask-Migrate / Alembic. Do not use `db.create_all()` as the schema story. The first domain migration adds Establishment, Patient, PatientStay, Wound, and Assessment. Planned authentication uses email/password login, opaque database sessions, recovery, and backend authorization; see [authentication.md](authentication.md). The current `SECRET_KEY` requirement does not determine the session design.
- SQLite foreign keys are enabled on every connection. A stay has one patient and one establishment. `start_date` is required; `end_date = NULL` marks an ongoing stay. A partial unique index permits at most one ongoing stay per patient, and a check rejects an end date before its start date.
- Patient `name` is one required text field. Surrounding whitespace is trimmed, and blank names are rejected.
- Room, bed, and service are optional free-text context on PatientStay, not separate records or unique assignments. Several patients may have the same establishment, room, and bed. Blank location input is stored as `NULL`.
- Changing room, bed, or service updates PatientStay without changing Patient or its wound history. A transfer ends one stay and starts another at the new establishment; the old stay remains. The later API must make that change atomically.
- A wound is open when `closed_at` is `NULL`. The later write APIs must set a server UTC timestamp when closing, clear it when reopening, reject new assessments while closed, and preserve earlier history. This schema PR adds no care-data routes.
- Optional clinical fields are `NULL` when not recorded, except patient allergies: the non-null `allergies` text is empty when there are no allergies. `infection = false` means an explicit no, not missing data. Exudate, wound colour, and odour are single enum values.
- Wound edges, wound tissue, and periwound skin are lists of enum values stored as JSON arrays on Assessment. SQLite has no native enum-array column, so `FindingList` validates allowed values and duplicates in Python whenever an assessment is inserted or updated through SQLAlchemy; `MutableList` tracks in-place changes. Raw SQL bypasses that validation. When Neodermo moves to PostgreSQL, migrate these fields to native enum-array columns. No extra findings table is needed.
- Timestamp columns use fixed-width UTC text through `UTCDateTime`, with database checks for the canonical format. The model accepts aware Python datetimes and returns aware UTC datetimes; observation time has no default. Measurements use nonnegative decimal centimetres with at most two decimal places, checked before and during storage.

## Local commands

Use Python 3.12 or newer. The macOS system `python3` is 3.9 and will not work. On this machine: `brew install python@3.12`.

`flask` and `pytest` are installed **inside** `.venv`, not globally. A new terminal does not remember `source .venv/bin/activate`. Either activate again, or call `.venv/bin/flask` and `.venv/bin/pytest`.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# replace SECRET_KEY in .env with a local random string
```

Then, with the venv still active:

```sh
flask --app neodermo:create_app db upgrade
flask --app neodermo:create_app run --port 5000
```

`GET http://127.0.0.1:5000/api/health` should return `{"status":"ok","database":"ok"}`. `db upgrade` now applies the first domain migration without dropping existing tables or data. Repeating it does nothing. Do not run `flask db init` again; `migrations/` already exists.

In another terminal (activate the venv first):

```sh
pytest
```

Without activating:

```sh
.venv/bin/pytest
.venv/bin/flask --app neodermo:create_app run --port 5000
```

From the repository root, the Makefile offers shortcuts that use the project `.venv`:

```sh
make test
make migration msg="describe schema change"  # generate and review the migration file
make db-upgrade                    # apply migrations to the configured local database
```

`GET /api/health` is the only HTTP contract so far. It reports database connectivity and must not return secrets or paths.

Local operator provisioning is available after installing dependencies and
applying the additive auth migration. Run
`.venv/bin/flask --app neodermo:create_app auth bootstrap` in a terminal; see
[the provisioning guide](authentication.md#local-operator-provisioning).
It prompts for the mailbox and hidden password and refuses a second account.
Login, session handling, and recovery endpoints are not implemented yet.

## Database migrations

Changing a SQLAlchemy model does not change the database by itself. From the
repository root, start with the configured database upgraded to the current
revision, then use this sequence for a new or changed field:

1. Edit the model in `src/neodermo/models/` and make sure it is imported in
   `src/neodermo/models/__init__.py`.
2. Run `make migration msg="describe schema change"`. This compares the models
   with the configured database and creates a file under `migrations/versions/`.
   It does **not** apply the change. If it reports no schema changes, no file is
   created.
3. Review the generated `upgrade()` and `downgrade()` before using them. Check
   constraints, defaults, existing-row handling, and whether a renamed field
   was mistaken for a drop and add. Edit the migration when the generated
   operations do not express the intended change.
4. Run `make db-upgrade` to apply pending revisions to the database selected by
   `DATABASE_URL` (normally set in `.env`). It creates the SQLite database when
   missing; repeating it at the latest revision is a no-op. Keep existing data
   rather than deleting the database to apply a later migration.
5. Run `make test`, then `.venv/bin/flask --app neodermo:create_app db check` to
   check for model/schema drift. Tests use an isolated database and do not
   upgrade the configured runtime database.

`make migration` gives each new revision a UTC timestamp ID in
`YYYYMMDDTHHMMSSffffffZ` form (the last six digits are microseconds, to avoid
same-second collisions). Alembic follows each revision's `down_revision` link
for actual upgrade order. Running `flask db migrate` directly without
`--rev-id` uses Alembic's default generated ID.

## Adding work later

### Isolated test applications

`create_app("testing", test_config={...})` applies explicit test configuration
before SQLAlchemy and Flask-Migrate initialize. It does not load `.env` or use
runtime `DATABASE_URL`/`SECRET_KEY` values. Overrides are accepted only with the
testing configuration; they are not a second runtime configuration channel.

The existing `app`/`client` fixtures use in-memory SQLite for lightweight checks.
`file_app_factory` builds separate app instances sharing one `tmp_path` SQLite
file within a test. Call it again for restart or separate-connection checks;
migrations are explicit. `migrated_file_app` provides that app already upgraded
through the real Alembic migrations. Both file fixtures release database sessions
and dispose engines at teardown. Never point test overrides at the runtime file.

### Extending the application

- New HTTP: add a blueprint module under `src/neodermo/api/` and register it from `create_app()`.
- New tables: add models under `src/neodermo/models/` and generate a new Alembic revision. Do not rewrite merged migrations.
- New checks: add focused pytest modules that build the app through `create_app` and an isolated test database.
