# Authentication contract

This document specifies the planned API-only authentication increment. The
current application still exposes only `/api/health`; authentication endpoints,
storage, and enforcement are not implemented yet. The test configuration and
file-backed fixtures described in [development.md](development.md) are available.

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

These bounds are part of the planned contract; enforcement arrives with the
auth endpoints. Reject missing/unknown fields, wrong types, non-object JSON,
malformed Unicode, and oversized input without echoing submitted values.

| Input | Rule |
| --- | --- |
| Auth POST body | At most 8 KiB; `application/json` only. Apply this locally to auth endpoints, allowing a separate limit for future multipart uploads. |
| Email | At most 1,024 UTF-8 bytes before trimming/validation, and 254 UTF-8 bytes after normalization. Validate syntax with a maintained library without DNS requests. |
| Email identity | Trim surrounding whitespace, normalize with the library, apply the same documented case-insensitive policy everywhere, and revalidate bounds. Never rewrite provider-specific dots or plus suffixes. |
| Password | 15–128 Unicode characters, including spaces; no composition rule, trimming, normalization, or truncation. Reject invalid Unicode. |
| Password blocklist | Apply a documented local common/compromised-password list to provisioning and reset. Login checks the exact supplied password without applying a new blocklist restriction. Never transmit candidate passwords to another service. |
| Session/reset/CSRF token | 43 URL-safe base64 characters encoding 32 random bytes without padding; reject malformed or oversized input before expensive processing. |

Email normalization must be identical for provisioning, login, recovery, and
account rate-limit keys. The final library configuration, normalization details,
Argon2 cost, and blocklist source/version belong in the implementation change.

## Session and request policy

Default absolute session lifetime is 43,200 seconds (12 hours), configurable
through the planned `SESSION_LIFETIME_SECONDS` setting. There is no sliding
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
are `GET /api/health`, `GET /api/auth/session`, and the login, forgot-password, and
reset-password POSTs below. Current-user status exposes only the session's user;
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
| `POST /api/auth/forgot-password` | `email` | 202 with `{"message":"If the account exists, recovery instructions will be sent."}` for known and unknown valid addresses. |
| `POST /api/auth/reset-password` | `token`, `new_password` | 204 after an atomic password change and revocation of all that user's sessions/reset tokens; no automatic login. |

Errors use `{"error":{"code":"..."}}` without submitted values. Health retains
its existing response shape. Error codes are:

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Malformed/oversized body, invalid fields or values, or unsupported auth request content type. |
| 400 | `invalid_reset_token` | Unknown, expired, or consumed reset token; use one response for all three. |
| 401 | `invalid_credentials` | Unknown email or wrong password; perform dummy-hash verification for unknown users. |
| 401 | `unauthenticated` | Protected operation has no valid session. |
| 403 | `invalid_origin` | Unsafe request has no trusted Origin. |
| 403 | `invalid_csrf` | Protected mutation has no matching session CSRF token. |
| 403 | `forbidden` | Authenticated user lacks permission for the operation. |
| 429 | `rate_limited` | Temporary request limit exceeded; include `Retry-After`. |

Login, recovery requests, and reset attempts will have address limits and
account/token limits using maintained tooling. Apply equivalent rules to known
and unknown accounts without permanent lockouts. Document the concrete limits,
storage, and single-process assumption when implemented; forwarded headers are
not trusted for the direct local deployment.

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
