# Cloud Board deployment

Local `foreshadow board` stays on loopback. A public instance is a **deployment**, not a package constant.

This document describes one production layout:

```text
systemd timer  →  foreshadow run   →  production HOME SQLite
systemd board  →  127.0.0.1:8765
nginx HTTPS    →  https://foreshadow.plainlist.space/  →  127.0.0.1:8765
nginx HTTP     →  :666 alias (deprecated, no OAuth callback)
```

Production URL: `https://foreshadow.plainlist.space/`

Temporary HTTP alias: `http://175.24.134.228:666/` (anonymous read only; GitHub OAuth callback is HTTPS).

## Security

Anonymous visitors may **read** the daily board.

These require an **authorized GitHub operator** (`FORESHADOW_OPERATORS`):

- 进入 / mission create
- Gate 2 submit (requires `FORESHADOW_WRITE_TOKEN`; radar `GITHUB_TOKEN` stays GET-only)
- clone / local setup
- reviews
- mission events

Login is GitHub OAuth (identity only). The OAuth access token is discarded after `GET /user`. It is not a write grant.

`READY_FOR_HUMAN_SUBMIT` is a live contract, not an alias for
`WAITING_USER_APPROVAL`. The review endpoint enables the submit button only when
all four checks pass:

- the exact approved commit is available from the local repository or bundle;
- the dedicated write credential can perform the required operation;
- the approval snapshot still matches the package; and
- upstream still equals the validated base commit.

Any upstream movement is `NEEDS_REFRESH`, including docs-only or otherwise
non-overlapping movement. The operator must refresh, validate, and approve a new
snapshot before submission.

`/api/mission/remote` always returns blocked. Public registration is off (`FORESHADOW_BOARD_ALLOW_REGISTER=0`). Anonymous `/api/portfolio` is 401; the SPA must keep the public board visible anyway.

Put GitHub credentials only in a `0600` environment file. `GITHUB_TOKEN` is the
read-only radar token (classic PAT, **no scopes**). `FORESHADOW_WRITE_TOKEN` is a
separate server-side classic PAT with `public_repo`; it is used only after the
operator's Gate-2 click for fork (if missing), exact branch push, and PR creation.
It is never passed to the contribution sandbox. OAuth client secret is a
different env var.

The write token must be configured before the Board can display
`READY_FOR_HUMAN_SUBMIT`; the submit click does not ask for another credential.
For v0.6 this narrow classic PAT is the deployable path. A GitHub App is not a
drop-in replacement for arbitrary third-party forks because installation and
repository access must already cover the relevant source and destination.

## Files

Copy:

- `contrib/systemd/foreshadow-board.service`
- `contrib/systemd/foreshadow-daily.service`
- `contrib/systemd/foreshadow-daily.timer`
- `contrib/nginx/foreshadow-board.conf` (HTTP :666 alias)
- `contrib/nginx/foreshadow-https.conf` (`foreshadow.plainlist.space`)

GitHub OAuth App (Developer settings → OAuth Apps):

- Homepage: `https://foreshadow.plainlist.space/`
- Callback: `https://foreshadow.plainlist.space/api/auth/github/callback`
- Local extra callback: `http://127.0.0.1:8765/api/auth/github/callback`

DNSPod A record: `foreshadow.plainlist.space` → `175.24.134.228`. Then:

```bash
sudo certbot certonly --webroot -w /var/www/letsencrypt -d foreshadow.plainlist.space
```

Environment file `/etc/foreshadow/environment`:

```bash
FORESHADOW_HOME=/var/lib/foreshadow
FORESHADOW_BOARD_PUBLIC=1
FORESHADOW_BOARD_ALLOW_REGISTER=0
FORESHADOW_BOARD_URL=https://foreshadow.plainlist.space/
FORESHADOW_OPERATORS=rainhuang0220
FORESHADOW_GITHUB_OAUTH_CLIENT_ID=...
FORESHADOW_GITHUB_OAUTH_CLIENT_SECRET=...
GITHUB_TOKEN=ghp_...
# Required for READY_FOR_HUMAN_SUBMIT. Dedicated classic PAT with public_repo.
FORESHADOW_WRITE_TOKEN=ghp_...
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now foreshadow-board.service
sudo systemctl enable --now foreshadow-daily.timer
sudo nginx -t && sudo systemctl reload nginx
```

## Operate

```bash
sudo systemctl status foreshadow-board
sudo systemctl restart foreshadow-board
sudo journalctl -u foreshadow-board -f

sudo systemctl status foreshadow-daily.timer
sudo systemctl start foreshadow-daily.service
sudo journalctl -u foreshadow-daily -n 100
```

Daily identity remains **UTC** inside Foreshadow. Same-day Official skip still applies.

## Import a validated contribution (ripwire #74)

Copy the persistent store onto the server, then import against the operator account. This does not write to GitHub.

```bash
sudo mkdir -p /var/lib/foreshadow/contributions
sudo rsync -a --delete \
  "$HOME/Library/Application Support/foreshadow/contributions/redhat-et__ripwire__74/" \
  /var/lib/foreshadow/contributions/redhat-et__ripwire__74/
sudo -u foreshadow FORESHADOW_HOME=/var/lib/foreshadow \
  foreshadow import-contribution \
  --store /var/lib/foreshadow/contributions/redhat-et__ripwire__74 \
  --github-login rainhuang0220
```

Leave Gate 2 unclicked. Do not set `FORESHADOW_SUBMIT_FAKE=1` in production.
