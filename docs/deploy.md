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

- 开始进入 / mission create
- clone / local setup
- reviews
- mission events

Login is GitHub OAuth (identity only). The OAuth access token is discarded after `GET /user`. It is not a write grant.

`/api/mission/remote` always returns blocked. Public registration is off (`FORESHADOW_BOARD_ALLOW_REGISTER=0`). Anonymous `/api/portfolio` is 401; the SPA must keep the public board visible anyway.

Put the GitHub **read** token only in a `0600` environment file. Classic PAT, **no scopes**. OAuth client secret is a different env var.

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
