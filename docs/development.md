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
src/neodermo/models/__init__.py   # empty until the first schema
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
- Schema changes use Flask-Migrate / Alembic. Do not use `db.create_all()` as the schema story. The first domain migration lands with the Patient / Wound / Assessment schema. Session authentication later uses this `SECRET_KEY` and factory.

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

`GET http://127.0.0.1:5000/api/health` should return `{"status":"ok","database":"ok"}`. There is no domain migration yet; `db upgrade` opens SQLite and applies nothing. Do not run `flask db init` again; `migrations/` already exists.

In another terminal (activate the venv first):

```sh
pytest
```

Without activating:

```sh
.venv/bin/pytest
.venv/bin/flask --app neodermo:create_app run --port 5000
```

`GET /api/health` is the only HTTP contract so far. It reports database connectivity and must not return secrets or paths.

## Adding work later

- New HTTP: add a blueprint module under `src/neodermo/api/` and register it from `create_app()`.
- New tables: add models under `src/neodermo/models/` and generate a new Alembic revision. Do not rewrite merged migrations.
- New checks: add focused pytest modules that build the app through `create_app` and an isolated test database.
