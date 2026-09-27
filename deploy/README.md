# Deploying for remote collection

One Linux host, behind HTTPS, running three things:

- **Caddy.** Public, on 80 and 443, with automatic certificates.
- **The capture server** (`tools/serve.mjs --ingest`). Localhost only; it
  serves the page code and proxies `/ingest/*`.
- **The ingest service** (`server/ingest.py`). Localhost only; it receives
  uploads.

Also a daily retention timer. The researcher app is never public; reach it
over SSH.

```
participant ──HTTPS──▶ Caddy :443 ──▶ serve.mjs 127.0.0.1:5173 ──/ingest──▶ ingest.py 127.0.0.1:5175
you ──SSH tunnel──▶ app.py 127.0.0.1:5174
```

**Status: written 2026-09-27, not yet run on a server.** The development
machine had no Linux, Caddy or systemd. Two parts were rehearsed for real
against local servers:

- `npm run deploy:check`, which runs from outside;
- the capture → proxy → ingest chain.

On the host, validate the rest first:

- `caddy validate --config /etc/caddy/Caddyfile`
- `systemd-analyze verify deploy/systemd/*.service deploy/systemd/*.timer`

## Before you start

- **Where the host is.** The route is UK/EU. Choose a provider region in the
  UK or EEA and record it: it is the "transfers outside the UK/EEA" line of the
  record of processing (`npm run ropa -- <study>`) and of the DPIA.
- **A study approved for participants.** Its file needs
  `"audience": "participants"` and the ethics fields (`studies/README.md`).
  Without one, the deploy check warns that every study is a self-test.
- **A domain name** pointing at the host (an A/AAAA record).

## Steps

1. **System packages.** Install Node 24, Python 3.14, git, ffmpeg, and Caddy
   (from Caddy's own repository).
2. **A service user and the code:**
   ```
   sudo useradd --system --home /opt/myimotions --shell /usr/sbin/nologin myimotions
   sudo git clone https://github.com/timohubbard/myimotions /opt/myimotions
   cd /opt/myimotions
   sudo -u myimotions python3.14 -m venv .venv
   sudo -u myimotions node tools/py.mjs -m pip install -r requirements.txt
   sudo -u myimotions npm run models
   sudo -u myimotions mkdir -p tempdata/inbox out
   sudo chmod 700 tempdata out
   ```
3. **Secrets.** Copy `deploy/env.example` to `/etc/myimotions/env`
   (`chmod 600`, owned by root). Set `MYIMOTIONS_DOMAIN`, and set
   `INGEST_TOKEN` from `openssl rand -hex 32`.
4. **Services:**
   ```
   sudo cp deploy/systemd/* /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now myimotions-ingest myimotions-capture myimotions-retention.timer
   ```
5. **Caddy.** Copy `deploy/Caddyfile` to `/etc/caddy/Caddyfile`, and give
   Caddy the domain (`MYIMOTIONS_DOMAIN` in its environment, e.g.
   `systemctl edit caddy` → `Environment=MYIMOTIONS_DOMAIN=…`).
   `sudo systemctl reload caddy`.
6. **Firewall.** Allow 22, 80 and 443 only. 5173, 5174 and 5175 must not be
   reachable.
7. **Check from your own machine:**
   ```
   npm run deploy:check -- https://<domain>
   npm run smoke:capture -- --study <study> --base https://<domain> --upload --inbox <local copy of the host's tempdata/inbox, or skip --upload>
   ```
   `deploy:check` confirms, and fails loudly on anything else:
   - HTTPS, with the plain-HTTP redirect;
   - the `?study=` redirect keeps the query;
   - cross-origin isolation (the clock precision);
   - nothing but page code is served;
   - uploads work through the proxy;
   - 5173, 5174 and 5175 are closed.
8. **Reaching the researcher app:**
   `ssh -L 5174:127.0.0.1:5174 <host>`, then on the host
   `sudo -u myimotions npm run app -- --media tempdata/inbox`. Open
   `http://localhost:5174` on your machine.

## Processing uploads

Uploaded sessions land in `tempdata/inbox/<session_id>/`. Process each one on
the host:

```
sudo -u myimotions npm run process -- tempdata/inbox/<session_id> --out out [--aus]
```

It refuses an upload that was never sealed, and a withdrawn or expired session.
Panel IDs are pseudonymised on the way in; the key and the link table live in
`out/_keys/`. Cohort analysis and export follow: `npm run cohort` and
`npm run export`.

## What this deployment deliberately does not do

- **No participant authentication.** Anyone with a study link can upload a
  bundle, as with any public study link. The ingest service limits what
  arrives: `session.json` first, fixed file names, size caps, one seal per
  session, and refusals for withdrawn or expired sessions.
- **No rate limiting.** Caddy has none built in. Add a plugin or a
  provider-level limit if a study link is posted publicly rather than through
  a panel.
- **Logs keep no panel IDs.** The Caddyfile deletes `PROLIFIC_PID`,
  `STUDY_ID`, `SESSION_ID` and `pid` from logged URLs, drops the Referer, and
  masks client addresses. A default access log would have copied every
  participant's raw Prolific ID into a file the pseudonymisation never sees.
- **Backups.** Not configured here. If you add them, the backups must expire
  too. A backup kept past the retention period breaks the promise the sweep
  keeps, and a withdrawn participant's data survives in it.
