# Authentication contract

This document specifies the API-only authentication increment. User, session,
and reset-token storage, password validation/hashing, and local operator
provisioning, login, current-session status, logout, and API request protection
are implemented. Rate limits and password recovery are planned next.
The test configuration and file-backed fixtures described in
[development.md](development.md) are available.

## Scope and boundaries

One locally provisioned operator accesses one shared clinical workspace.
Provisioning confirms the recovery mailbox and reads a password interactively
without echo. There is no public registration, additional production account,
role management, or patient ownership. Tests may use distinct fictional users
to prove current-user and recovery isolation.

| Boundary | Responsibility |
| --- | --- |
| Password verification | Check the supplied password against a salted Argon2id hash. Passwords are never decrypted. |
| Session lookup | Digest the opaque cookie token and resolve a live database session and its user. |
| Authentication | Establish the current user on the backend, in Flask `g`. |
| Authorization | Decide whether that user may perform this operation on its target. The current operator may access the shared workspace. |
| CSRF protection | Require a trusted Origin for unsafe requests and a session-bound token for protected mutations. This does not grant permissions or protect stolen credentials. |
| Recovery | Authorize a password change only for the user bound to a valid one-time reset token. |

Flask's signed client-side session cookie is not the authentication authority.
Session tokens and reset tokens each contain 32 cryptographically random bytes;
only their SHA-256 digests are stored. Passwords use slow salted Argon2id hashing,
not a fast token digest. Each session also has an independent random CSRF secret.

## Input limits and validation

Email/password validation is available to provisioning and login. HTTP auth
requests reject missing/unknown fields, wrong types, non-object JSON,
malformed Unicode, and oversized input without echoing submitted values.

| Input | Rule |
| --- | --- |
| Auth POST body | At most 8 KiB; `application/json` only. Apply this locally to auth endpoints, allowing a separate limit for future multipart uploads. |
| Email | At most 1,024 UTF-8 bytes before trimming/validation, and 254 UTF-8 bytes after normalization. Validate syntax with a maintained library without DNS requests. |
| Email identity | Trim surrounding whitespace, normalize with the library, apply the same documented case-insensitive policy everywhere, and revalidate bounds. Never rewrite provider-specific dots or plus suffixes. |
| Password | 15–128 Unicode characters, including spaces; no composition rule, trimming, normalization, or truncation. Reject invalid Unicode. |
| Password blocklist | Apply a documented local common/compromised-password list to provisioning and reset. Login checks the exact supplied password without applying a new blocklist restriction. Never transmit candidate passwords to another service. |
| Session/reset/CSRF token | 43 URL-safe base64 characters encoding 32 random bytes without padding; reject malformed or oversized input before expensive processing. |

Email normalization uses `email-validator==2.3.0` with strict syntax checks,
DNS checks disabled, and SMTPUTF8 mailbox names disabled. ASCII mailbox names
are lowercased and internationalized domains use their lowercase IDNA ASCII
representation. The local part is limited to 64 characters. This application
deliberately treats the whole address as case-insensitive. The same helper must
be used by login, recovery, and account rate-limit keys. Provisioning confirms
mailbox ownership by operator assertion; it does not send a verification email.

Password hashing uses `argon2-cffi==25.1.0` with explicit Argon2id parameters:
64 MiB memory, 3 iterations, parallelism 4, 16-byte random salt, and 32-byte hash.
The encoded hash includes the salt and parameters. A five-hash local measurement
on the development machine had a median of approximately 23 ms; remeasure before
changing hardware or cost. A random dummy hash is computed once per app instance
for unknown-account verification, not once per login attempt.

The packaged local blocklist is Django 5.2's 19,640-entry snapshot, with source,
checksum, attribution, and license in
[the data directory](../src/neodermo/auth/data/README.md). Screening compares a
lowercase copy only; hashing and verification preserve the exact input. This
finite list does not detect every compromised password. No candidate is sent
over the network, and Django is not a runtime dependency.

## Local operator provisioning

Install the pinned dependencies and upgrade the configured database first:

```sh
.venv/bin/python -m pip install -e ".[dev]"
make db-upgrade
.venv/bin/flask --app neodermo:create_app auth bootstrap
```

Run bootstrap in an interactive terminal. Enter the recovery email twice,
confirm control of that mailbox, then enter and confirm the password without
echo. There is no password argument, environment variable, or credential file.
The command refuses to fall back to echoed input when no suitable terminal is
available. A 120-second wall-clock deadline covers the entire command, including
all prompts; on expiry it exits with an error and releases its timer and database
resources. The local CLI requires macOS or Linux for this deadline. Validation
errors do not repeat submitted values.

Bootstrap refuses a second account. After validation/hashing, a SQLite
`BEGIN IMMEDIATE` transaction serializes the final empty-users check and insert.
No lock is held while prompting or hashing. Concurrent bootstrap attempts have
one winner; failures roll back the insert. Lock contention is bounded by the
SQLite driver's connection timeout and produces a generic operational error.
Do not manually remove the operator to reset a password; recovery is a later
milestone of this increment.

The additive auth migration follows the existing domain migration. Users have
unique normalized emails. Sessions/reset records reference users, store unique
SHA-256 token digests, enforce UTC timestamps and expiry after creation, and
index user/expiry columns. Deleting a user cascades their credential rows; no
user-deletion command is exposed. Multiple fictional users are allowed in tests;
the single-operator restriction belongs to the provisioning operation.

Provisioning itself issues no session or reset credential. An operator signs in
through the login endpoint after provisioning.

## Session and request policy

Default absolute session lifetime is 43,200 seconds (12 hours), configurable
through `SESSION_LIFETIME_SECONDS`. There is no sliding
renewal. Password reset tokens expire after 1,800 seconds (30 minutes).

The cookie is named `neodermo_session`: HttpOnly, SameSite=Lax, Path=/, no Domain,
and Secure for HTTPS. Disabling Secure is allowed only for documented loopback
HTTP development. Cookie expiry matches server-side expiry. Raw session tokens
appear only in the cookie, never response JSON or logs.

Every successful login creates a fresh session and CSRF token. It invalidates a
valid session presented by that browser while preserving other devices'
sessions. Logout deletes the current session and clears the cookie with matching
scope; replay must fail immediately. Database sessions survive app restarts.

Require authentication by default for `/api` routes. The exact public exceptions
are `GET /api/health`, `GET /api/auth/session`, and `POST /api/auth/login`.
Forgot-password and reset-password will be added as public exceptions with
their endpoints. Current-user status exposes only the session's user;
request fields cannot select a different identity.

Every unsafe API request requires an exact match against configured trusted
frontend origins. Reject absent, `null`, and untrusted Origin values. Configure
the loopback app origin explicitly (for example `http://127.0.0.1:5000`); do not
derive trust from the Host header. Different schemes, hosts, and ports are
different origins. Cross-origin CORS remains disabled in this API-only increment.

Protected POST/PUT/PATCH/DELETE also require `X-CSRF-Token`, compared in constant
time with the server-side session secret. Public auth POSTs use the JSON and
Origin protections, including when a browser already has a session. GET never
changes account or clinical data. Preflight handling must not execute protected
operations. All API responses, including errors, receive `Cache-Control: no-store`.

## HTTP contract

| Endpoint | Input | Success |
| --- | --- | --- |
| `GET /api/health` | None | Preserve the existing 200 connectivity response and generic 503 failure response. |
| `POST /api/auth/login` | `email`, `password` | 200 with `authenticated: true` and `csrf_token`, plus a new session cookie. |
| `GET /api/auth/session` | No account selector | 200 with `authenticated: true`, `user: {id, email}`, and `csrf_token`; otherwise `authenticated: false` without creating a session. A stale cookie may be cleared. |
| `POST /api/auth/logout` | Valid session, Origin and CSRF headers; no account selector | 204 after revocation. |

Planned recovery endpoints: `POST /api/auth/forgot-password` will accept
`email` and return the same 202 response for known and unknown valid addresses.
`POST /api/auth/reset-password` will accept `token` and `new_password` and
return 204 after revoking that user's sessions and reset tokens.

Errors use `{"error":{"code":"..."}}` without submitted values. Health retains
its existing response shape. Error codes are:

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Malformed/oversized body, invalid fields or values, or unsupported auth request content type. |
| 401 | `invalid_credentials` | Unknown email or wrong password; perform dummy-hash verification for unknown users. |
| 401 | `unauthenticated` | Protected operation has no valid session. |
| 403 | `invalid_origin` | Unsafe request has no trusted Origin. |
| 403 | `invalid_csrf` | Protected mutation has no matching session CSRF token. |
| 403 | `forbidden` | Authenticated user lacks permission for the operation. |
| 429 | `rate_limited` | Login limit exceeded; includes `Retry-After` in seconds. |

The planned recovery endpoint will use `invalid_reset_token` for unknown,
expired, and consumed tokens.

Login has two independent fixed-window limits: 30 requests per minute from the
connection's remote address and 5 per minute for a normalized email, whether
that account exists or not. The email bucket key is a digest of the normalized
address. Malformed requests still consume the address bucket; requests without
a valid normalized email do not consume an email bucket. The check runs before
password verification. A 429 response includes `Retry-After`; there are no
permanent account locks. Forwarded headers are not trusted for this direct
local deployment.

[Flask-Limiter](https://flask-limiter.readthedocs.io/en/stable/) uses an
in-memory store here. Counters reset when the app restarts and do not coordinate
between workers; run this local deployment as one process. When recovery routes
are implemented, add their planned independent limits: forgot password 10/hour
per address and 3/hour per normalized email; reset password 20/minute per
address and 5/minute per submitted token digest. Do not accept an email in a
reset request to select its rate-limit bucket.

Recovery requests must avoid an obvious account-existence timing shortcut.
Deliver reset credentials only to the provisioned mailbox through a loopback
SMTP capture inbox, with a separate test outbox. Never return or log the token.
Requesting recovery does not change the password or revoke sessions. Concurrent
reset attempts must have only one winner, and a login racing a reset must not
create a session based on the old password. Send a confirmation after reset.

Before this increment is complete, document and verify the actual local inbox,
HTTP examples with explicit Origin/CSRF headers, token expiry cleanup, and
credential-free logs. Authentication must be in place before clinical endpoints
ship. Recovery UI, external mail services, JWT/OAuth, MFA, and multi-user clinical
authorization are later work.
