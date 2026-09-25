# Development

These conventions come with the initial Flask foundation. The installable package, factory, migrations, and pytest suite are part of that same ongoing work. Commands below are the target interface; they are not runnable until that package exists. Coding style, docstrings, and environment rules are in [guidelines.md](guidelines.md).

## Layout

```
AGENTS.md
README.md
pyproject.toml
.gitignore
.env.example
src/neodermo/__init__.py
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

## Target commands

Use Python 3.12+ and a virtualenv at `.venv`. macOS system Python is 3.9 and is not enough. Run Flask on port 5000 once the application factory exists.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# set SECRET_KEY and DATABASE_URL in .env
export FLASK_APP=neodermo:create_app
flask db upgrade
flask run --port 5000
pytest
```

`pip install -e ".[dev]"` is runnable now and makes `import neodermo` work. The migrate, run, and pytest commands land with the factory, health route, and tests.

`GET /api/health` is the first HTTP contract. It must report database connectivity and must not return secrets or paths.

## Adding work later

- New HTTP: add a blueprint module under `src/neodermo/api/` and register it from `create_app()`.
- New tables: add models under `src/neodermo/models/` and generate a new Alembic revision. Do not rewrite merged migrations.
- New checks: add focused pytest modules that build the app through `create_app` and an isolated test database.
