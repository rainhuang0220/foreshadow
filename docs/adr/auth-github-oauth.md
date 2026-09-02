# ADR: GitHub identity login + durable Foreshadow session

**Status:** Accepted (2026-09-02)
**Product:** Foreshadow v0.3

## Context

Public Board at `http://175.24.134.228:666/` allows anonymous read. Mutations require a Foreshadow username/password. Registration is disabled. Sessions last 14 days, cookie is `HttpOnly; SameSite=Lax` without `Secure`. Refresh/close-browser dropping login is a product failure for a daily personal tool. A public HTTP cookie cannot be made “Secure”.

Foreshadow is a GitHub-centered operator tool. The operator already is `rainhuang0220` on GitHub.

## Decision

1. **Login identity** = GitHub OAuth web application flow (authorization code). Scopes: none, or `read:user` only. After `GET /user`, discard the access token.
2. **Authorization** = `FORESHADOW_OPERATORS` allowlist of GitHub logins (env, comma-separated). Source never hardcodes a username.
3. **Session** = existing SQLite `sessions` table (hashed token), lifetime **30 days**, rotate on each successful login, revoke on logout. Cookie: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` iff the request is HTTPS.
4. **Password login** remains for localhost/dev and the existing `rain` row. Public Board presents **Login with GitHub** first.
5. **Write permissions** are not granted at login. A future GitHub App installation (Contents, Pull Requests, Issues, Metadata) is the mutation credential. Classic `repo`-scoped PAT is not the write path.
6. **HTTPS** target: `https://foreshadow.plainlist.space/` on the existing Baota host (Let's Encrypt already works for `plainlist.space`). `:666` HTTP remains a temporary alias and must not host the OAuth callback.

## Rejected

| Option | Why not |
|---|---|
| oauth2-proxy | Extra process; default-protects all routes; anonymous Board needs exceptions; identity headers must be spoof-proofed |
| Cloudflare Access | Forces login for viewers |
| Starlette SessionMiddleware only | Signed cookie is not server-revocable without a denylist we would have to build anyway |
| Browser password managers / extensions | Fixes a broken app instead of sessions |
| Storing GitHub OAuth token as the session | Couples identity to write power; long-lived OAuth App tokens are the wrong shape |

## Consequences

- OAuth callback requires a public HTTPS origin (GitHub loopback exception is only for `127.0.0.1` / `localhost`).
- Deploy needs `FORESHADOW_GITHUB_OAUTH_CLIENT_ID` / `CLIENT_SECRET` and an allowlist.
- `/api/me` grows `github_login`, `operator`, `auth_method`.
- Tests mock the GitHub token endpoint with respx. No live OAuth in CI.
