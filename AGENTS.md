# Neodermo agent notes

Neodermo is a mobile-first wound-care journal and a Python/Flask learning project. v0.1 is a local desktop slice so a proof of concept can ship quickly. The app is implemented as a learning project. Agents explain, guide, and review unless explicitly asked to code. An implement request covers only the requested change, not the whole roadmap.

## Read first

- Product, privacy, and completion rules: [docs/v0.1-spec.md](docs/v0.1-spec.md)
- Layout, layering, and local commands: [docs/development.md](docs/development.md)
- How to write Python and Flask here: [docs/guidelines.md](docs/guidelines.md)
- Current Git `main` shows what exists. The README is an intro, not the full spec.

## Local checks

See [docs/development.md](docs/development.md) for install, run, migrate, and pytest. Use the project `.venv`; `pytest` is not a global command.

## Working rules

- These docs and the repository code are the public source of truth. Reconcile material conflicts; do not silently change requirements.
- Keep runtime databases, uploads, and secrets out of Git. Use fictional cases only.
