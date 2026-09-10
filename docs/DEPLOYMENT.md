# Deployment

Everything in this repo (code, Docker configs, CI workflow) is ready to deploy. The
steps below are the ones that need your physical machine or your accounts — nothing
here can be done from inside a coding assistant's sandbox, so do these yourself.

## 1. Install Ubuntu Server

Install Ubuntu Server (22.04 LTS or newer) on the PC that will host this. Standard
install — a normal user account with `sudo`, OpenSSH enabled so you can manage it
remotely, is all this needs beyond the defaults.

Then install Docker + Docker Compose:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # log out/in after this
```

## 2. Get a domain (free option: DuckDNS)

Caddy needs a real domain to issue a free Let's Encrypt certificate — a bare IP address
can't get one. If you don't want to buy a domain:

1. Go to https://www.duckdns.org, sign in (GitHub/Google/etc.), and claim a subdomain,
   e.g. `yourname.duckdns.org`.
2. Point it at your server's public IP (DuckDNS's dashboard does this, and can
   auto-update if your ISP gives you a dynamic IP — see their "install" tab for a small
   cron script that keeps it current).

## 3. Port forwarding

On your router, forward **ports 80 and 443** (TCP) to the Ubuntu server's local IP.
Caddy needs both — 80 for the Let's Encrypt HTTP challenge (and to redirect to https),
443 for the actual site.

## 4. Create the GitHub repo and push

```bash
cd history-shorts
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```
Use a **private** repo — this now handles real user credentials, even though secrets
live in `.env` (git-ignored) rather than in the repo itself.

## 5. Install the self-hosted GitHub Actions runner

On the Ubuntu server, in the repo's GitHub page: **Settings → Actions → Runners → New
self-hosted runner**, follow GitHub's generated commands (they look like this, but copy
the exact token from your repo — it's one-time-use):
```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf actions-runner.tar.gz
./config.sh --url https://github.com/<you>/<repo> --token <TOKEN_FROM_GITHUB>
sudo ./svc.sh install
sudo ./svc.sh start
```
This runner polls GitHub outward — no inbound access needed for the deploy mechanism
itself (separate from the port-forwarding in step 3, which is for the site itself).

Add the `DOMAIN` repository variable (**Settings → Secrets and variables → Actions →
Variables**) matching what's in your server's `.env`, so the workflow's health check
knows what URL to hit.

## 6. First-time server setup

Clone the repo onto the server (or let the first CI run do it), then in the repo root:
```bash
cp .env.example .env
```
Fill in every value in `.env` — see the comments in `.env.example` for what each one
does. Generate `SECRET_KEY` with:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Set `FORCE_HTTPS=1` (this is production, behind real Caddy TLS). Pick a real
`ADMIN_PASSWORD` — change it via the app after first login if you want, but don't leave
the example value in place.

Then bring the stack up once manually to confirm it works before relying on CI:
```bash
docker compose build
docker compose up -d
docker compose logs -f app   # watch for "alembic upgrade head" then gunicorn starting
```

From then on, every `git push` to `main` triggers the GitHub Actions workflow, which
rebuilds and restarts the stack on this same server automatically.

## Ongoing operation

- **Your data is safe across deploys.** `postgres_data` and `minio_data` are named
  Docker volumes, not part of any container's disposable filesystem — `docker compose
  build && docker compose up -d` (what CI runs) never touches them. The only way to lose
  this data is running `docker compose down -v` (that `-v` removes volumes) or manually
  deleting them — never do either of those in normal operation.
- **Schema changes** are applied automatically and incrementally via Alembic
  (`alembic upgrade head` runs on every app start, and is a no-op if nothing's new) —
  never hand-edit the database schema directly.
- **Backups**: back up the `postgres_data` and `minio_data` volumes (e.g.
  `docker run --rm -v postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data.tgz /data`)
  on whatever schedule matters to you — nothing in this stack backs itself up.
- **Ollama model updates**: if you change `OLLAMA_MODEL` in `.env`, re-run
  `docker compose up -d` — the `ollama-init` one-shot container will pull the new model
  before `app` starts.
