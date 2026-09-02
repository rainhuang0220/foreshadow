# Cloud Board deployment

Local `foreshadow board` stays on loopback. A public instance is a **deployment**, not a package constant.

This document describes one production layout:

```text
systemd timer  →  foreshadow run   →  production HOME SQLite
systemd board  →  127.0.0.1:8765
nginx          →  0.0.0.0:666  →  127.0.0.1:8765
```

Example public URL for the operator’s current host: `http://175.24.134.228:666/`

## Security

Anonymous visitors may **read** the daily board.

These require a logged-in Board user:

- 开始进入 / mission create
- clone / local setup
- reviews
- mission events

`/api/mission/remote` always returns blocked. Public registration is off (`FORESHADOW_BOARD_ALLOW_REGISTER=0`).

Put the GitHub token only in a `0600` environment file. Classic PAT, **no scopes**.

## Files

Copy:

- `contrib/systemd/foreshadow-board.service`
- `contrib/systemd/foreshadow-daily.service`
- `contrib/systemd/foreshadow-daily.timer`
- `contrib/nginx/foreshadow-board.conf`

Environment file `/etc/foreshadow/environment`:

```bash
FORESHADOW_HOME=/var/lib/foreshadow
FORESHADOW_BOARD_PUBLIC=1
FORESHADOW_BOARD_ALLOW_REGISTER=0
FORESHADOW_BOARD_URL=http://175.24.134.228:666/
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
