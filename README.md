# Neodermo

A mobile-first wound-care journal, built as a hands-on project to learn Python and Flask.

Neodermo helps a nurse record wound assessments and follow their evolution across visits. The product is meant for a phone. v0.1 is a local desktop browser slice of that workflow so a working proof of concept can ship quickly: select a patient, choose a wound, review the previous expectation, and record this visit. Photos are optional.

This is a learning prototype, not a clinical system. Use fictional cases only. Real patient records, wound photographs, credentials, and secrets must never be committed to this public repository.

## Spec and conventions

- Product, privacy, and completion rules: [docs/v0.1-spec.md](docs/v0.1-spec.md)
- How the codebase is laid out: [docs/development.md](docs/development.md)
- How to write Python and Flask here: [docs/guidelines.md](docs/guidelines.md)
- Agent working notes: [AGENTS.md](AGENTS.md)

## Planned stack

| Layer | Technology |
| --- | --- |
| Frontend | JavaScript and React (after the Flask APIs exist) |
| Backend | Python and Flask |
| Data access | SQLAlchemy |
| Database | SQLite for v0.1, PostgreSQL later |
| Backend tests | pytest |

v0.1 runs locally in a desktop browser. That is a time-box, not a product change: Android access stays the next milestone and should keep using the same backend.

## Local commands

Install, migrate, run, and test commands are in [docs/development.md](docs/development.md). They become runnable once the Flask package exists.
