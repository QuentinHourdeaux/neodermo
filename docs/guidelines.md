# Code guidelines

How to write Python and Flask in this repository. Layout and commands live in
[development.md](development.md). Product rules live in
[v0.1-spec.md](v0.1-spec.md).

These docs are public. Do not put private-tracker names, IDs, or personal names
in the repository.

## Style

- Use Python 3.12 or newer. The macOS system `python3` is 3.9 and is not
  supported.
- Follow PEP 8: `snake_case` modules, functions, and variables; `PascalCase`
  classes; 4-space indent.
- Prefer type hints on public functions and anything with a non-obvious
  signature.
- Pin every dependency in `pyproject.toml`. If you install it, record it. New
  libraries need a one-line why in the change that adds them.
- Do not add Flask-RESTful, marshmallow, pydantic, a repository layer, or a
  shared client framework unless a later change truly needs them.
- Keep the Flask code idiomatic and small. Extract a function when a second call
  site exists, not because it might be useful later.
- No formatter or lint gate is required in this first slice. Write as if
  Black-compatible PEP 8 is the default.

## Comments and docstrings

Python's equivalent of JSDoc is a **docstring** (PEP 257) plus **type hints**.
Use Google-style docstrings. Put types in the signature; do not repeat them in
the docstring.

Write a docstring on public or non-obvious functions: the application factory,
config loaders, and anything with a lifecycle, safety, or privacy rule. Skip a
long `Args` block when the name and hints already tell the story.

Comments explain _why_ and invariants. Do not narrate ordinary assignments or
control flow.

```python
def create_app(config_name: str | None = None) -> Flask:
    """Build and return a configured Flask app.

    A new app is created each call so tests and the migration CLI
    do not share one global instance.
    """
```

Routes stay thin. Rule functions own the why:

```python
@bp.get("/health")
def health() -> tuple[dict[str, str], int]:
    """Return database connectivity without exposing configuration."""
    return check_database(), 200


def check_database() -> dict[str, str]:
    """Run a trivial connectivity query.

    Returns a generic payload. Never include paths, env values,
    or exception text that could leak configuration.
    """
```

## Flask and Python

- Build the app with `create_app()`. Keep `db = SQLAlchemy()` in `extensions.py`
  and call `init_app`. Tests and the migration CLI must be able to construct a
  fresh app.
- Register blueprints from the factory. Routes parse HTTP and return responses.
  Application functions own validation and lifecycle rules. SQLAlchemy models
  own persistence.
- Use `current_app` and `g` inside a request. Do not store request-specific data
  on the app object.
- Use SQLAlchemy 2 style when models exist (`select()`, not `Model.query`).
- Alembic owns schema changes. Do not use `db.create_all()` as the schema path.
  Do not rewrite a migration that has already landed on `main`.
- Flask 3 does not use `FLASK_ENV`. Select an explicit config and use
  `FLASK_DEBUG` only for local reload.
- Known failures return a small JSON body and a precise status code. Do not
  return stack traces, filesystem paths, or secrets.
- Log what happened, not narratives, room or bed values, credentials, or tokens.
- Store timestamps timezone-aware in UTC. Convert to local time only when
  displaying.
- When write APIs exist, reject unknown fields. JSON field names stay stable
  once documented.

## Environments

A second person should be able to clone, create `.venv`, copy `.env.example` to
`.env`, fill the required values, migrate, and run. If that still needs
unwritten knowledge, these docs are incomplete.

| Mode                        | How it is selected                          | Database            | Debug | Secrets                            |
| --------------------------- | ------------------------------------------- | ------------------- | ----- | ---------------------------------- |
| Local                       | `.env` on the developer machine             | SQLite under `var/` | on    | generated locally, never committed |
| Test                        | pytest / testing config                     | isolated temp URI   | off   | dummy values in fixtures           |
| Packaged / later production | process environment, not a file in an image | `DATABASE_URL`      | off   | injected by the host               |

- Commit `.env.example` with every supported variable, a short comment, and fake
  values.
- Never commit `.env`, `.venv/`, `var/`, a real `SECRET_KEY`, or later password
  hashes.
- Required now: `SECRET_KEY`, `DATABASE_URL` (or a documented SQLite path that
  becomes that URL).
- Optional: `FLASK_DEBUG`. Later work may add an upload directory and auth/mail
  settings. Add supported settings to `.env.example` in the change that implements
  them. Operator provisioning will store a password hash in the database, not
  a credential file or environment variable; see [authentication.md](authentication.md).
- Tests must pass with no `.env` present, and must still pass if `.env` points
  at the runtime database. pytest must not create or modify that runtime file.
- Do not add a second unofficial config channel (`config.local.py`,
  machine-specific shell exports) unless it replaces `.env` on purpose.

Commands for creating the venv and starting the app are in
[development.md](development.md).

## Tests

- Build the app through `create_app` and an isolated database. The Flask test
  client is enough until a live-server check is required.
- Name tests after the behavior (`test_health_fails_when_database_unavailable`),
  not after the implementation.
- If a test's intent is not obvious, comment the contract it locks, not the
  lines of setup.
