# ADR: HTTPS via foreshadow.plainlist.space

**Status:** Accepted (2026-09-02)

## Context

Foreshadow Board is public HTTP on `175.24.134.228:666`. GitHub OAuth callbacks for non-loopback hosts need HTTPS. `Secure` cookies are meaningless on that URL.

The same VM already serves `https://plainlist.space/` with Let's Encrypt (`/etc/letsencrypt/live/plainlist.space/`, valid until 2026-11-29). DNS is DNSPod. nginx is Baota (`/www/server/panel/vhost/nginx/`). Foreshadow’s vhost is `foreshadow-666.conf` (HTTP 666 only).

## Decision

Production origin:

```text
https://foreshadow.plainlist.space/
```

- DNS A: `foreshadow.plainlist.space` → `175.24.134.228`
- certbot for that hostname (HTTP-01 on port 80)
- nginx 80 → 443 redirect; 443 proxy_pass `http://127.0.0.1:8765` with `X-Forwarded-Proto https`
- `FORESHADOW_BOARD_URL=https://foreshadow.plainlist.space/`
- Keep `:666` HTTP as a **deprecated alias** (anonymous read). Do not register it as an OAuth callback.

## Rejected

- Cloudflare Tunnel: useful if we lacked a domain; we have one on this host. Tunnel still needs a zone on Cloudflare.
- Path on `plainlist.space` (`/foreshadow`): collides with existing `/api/` and `/oauth/` on that site.
- Self-signed on :667: browsers and GitHub OAuth will reject it.

## Operator step that this agent cannot finish alone

Create the DNSPod A record (and the GitHub OAuth App callback `https://foreshadow.plainlist.space/api/auth/github/callback`). Code, nginx snippet, and certbot command ship in `contrib/` and `docs/deploy.md`.
