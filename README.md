# Neodermo

A mobile-first wound-care journal, built as a hands-on project to learn Python and Flask.

Neodermo will help nurses record wound assessments and follow their evolution across visits. The first version will focus on a simple flow: select a patient, choose a wound, review the previous assessment, and record today's observations.

## What's coming

- Patients with separate histories for each wound.
- Dated assessments with measurements, reported pain, dressing used, and notes.
- A timeline to compare observations and measurement trends across visits.
- A responsive web interface, followed by Android home-screen installation as a progressive web app (PWA).

Photo documentation may follow once the core workflow works. Offline recording and synchronization are outside the initial scope.

## Planned stack

| Layer | Technology |
| --- | --- |
| Frontend | JavaScript and React |
| Backend | Python and Flask |
| Data access | SQLAlchemy |
| Database | SQLite initially, PostgreSQL later |
| Backend tests | pytest |
| Mobile access | Responsive web app, then an installable PWA |

## The name

Neodermo is inspired by the Greek roots *neo-* (new) and *derma* (skin), evoking the journey from a wound toward healed skin.

## Project status

Planning stage: this repository currently contains only this README.

This is a learning prototype, not a clinical system. Demos will use fictional cases only. Real patient records, wound photographs, credentials, and secrets must never be committed to this public repository. Clinical use would require a separate privacy, security, and workplace approval process.
