# Server setup — from bare metal to a running Antiquary

Hand this file to a fresh Claude Code session running **on the Ubuntu Server machine
itself** (after cloning the repo — see step 5) and it has everything needed to finish
setup with no other context. It also works as a plain step-by-step guide for a human.

This assumes: the target PC already has Ubuntu Server installed (or you're about to
install it, per step 1), and you're doing all of this **locally on that machine**, not
from the sandboxed dev environment the rest of this project was built in.

Read `CLAUDE.md` and `docs/ARCHITECTURE.md` first if you haven't — they explain what
Antiquary is and how it's built. `docs/DEPLOYMENT.md` is the short-form version of this
same guide; this file is the detailed walkthrough.

---

## 1. Install Ubuntu Server

Use **Ubuntu Server 24.04 LTS or newer** (26.04 LTS is fine) — Server edition, not
Desktop. `amd64` is correct for a normal PC.

During the installer:
- **Storage**: default guided partitioning (use entire disk, with LVM) is fine unless
  you have a specific layout in mind.
- **Profile setup**: pick a username/password you'll remember — this becomes the
  account you SSH in as and run Docker under.
- **SSH setup**: tick **"Install OpenSSH server"**. This matters — without it you can
  only manage the box from a physically-attached keyboard/monitor.
- **Featured snaps**: skip all of them (Docker, etc.) — install Docker manually in step
  2 to get the official version, not the snap.
- Let it install, reboot, remove the USB.

Log in once at the console to confirm it boots, then do everything else over SSH from
your main computer:
```bash
ssh <your-username>@<server-local-ip>
```
(Find the server's local IP from the console login screen, or your router's device
list.)

## 2. Basic OS hardening and updates

```bash
sudo apt update && sudo apt upgrade -y

# Firewall: only allow SSH, HTTP, HTTPS
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Optional but recommended: disable SSH password auth once you've copied an SSH key over
(`ssh-copy-id <user>@<server-ip>` from your main machine first), then in
`/etc/ssh/sshd_config` set `PasswordAuthentication no` and
`sudo systemctl restart ssh`. Skip this if you're fine with password login for now.

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```
**Log out and back in** (or `newgrp docker`) for the group change to take effect, then
confirm:
```bash
docker run hello-world
docker compose version
```

## 4. Install the `gh` CLI (needed for the private repo)

```bash
type -p curl >/dev/null || sudo apt install curl -y
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh -y
gh auth login
```
Follow the prompts (browser-based device auth is easiest). This account needs access to
the `sarthax10/antiquary` repo.

## 5. Clone the repo

```bash
cd ~
gh repo clone sarthax10/antiquary
cd antiquary
```

From here on, a Claude Code session started in `~/antiquary` will have `CLAUDE.md`
loaded automatically.

## 6. Get a free domain (DuckDNS)

Caddy needs a real hostname to get a free HTTPS certificate — a bare IP can't get one.

1. Go to https://www.duckdns.org, sign in with GitHub/Google.
2. Claim a subdomain, e.g. `antiquary-yourname.duckdns.org`.
3. Point it at your **public IP** (check it at https://whatismyip.com from the server's
   network). DuckDNS's dashboard has a box for this.
4. If your ISP gives you a dynamic (changing) public IP, set up their auto-update cron
   job (DuckDNS's "install" tab has the exact one-liner for Linux) so the record stays
   current.

## 7. Port forwarding on your router

Log into your router's admin page (usually `192.168.0.1` or `192.168.1.1`) and forward:
- **Port 80 (TCP)** → server's local IP, port 80
- **Port 443 (TCP)** → server's local IP, port 443

Caddy needs 80 for the Let's Encrypt challenge (and to redirect HTTP→HTTPS) and 443 for
the actual site. Every router's UI is different — look for "Port Forwarding" or
"Virtual Server" in the admin panel.

Give the server a **static local IP** (either a DHCP reservation in the router, or a
static netplan config on Ubuntu) so this forwarding rule doesn't break after a reboot.

## 8. Set up `.env`

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # use this for SECRET_KEY
nano .env   # or vim/whatever
```

Fill in every value. Key ones for production:
- `SECRET_KEY` — the random hex string generated above (never reuse a dev value here).
- `FORCE_HTTPS=1` — this is real production behind Caddy TLS.
- `DATABASE_URL=postgresql://antiquary:<pick-a-real-password>@postgres:5432/antiquary`
  (note: `postgres` as hostname, not `localhost` — inside Docker Compose's network the
  service name is the hostname).
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — must match what's in
  `DATABASE_URL`.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — your real admin login; change the password via the
  app after first login if you want, but don't ship the example value.
- `S3_ENDPOINT_URL=http://minio:9000`, `S3_ACCESS_KEY` / `S3_SECRET_KEY` — pick real
  values (these become MinIO's root credentials), `S3_BUCKET=antiquary-videos`,
  `S3_REGION=us-east-1`.
- `DOMAIN=antiquary-yourname.duckdns.org` (or your real domain) — Caddy reads this to
  request the certificate.
- `OLLAMA_MODEL=llama3.2:3b` (or whatever model you want; leave `OLLAMA_FACTCHECK_MODEL`
  blank to fall back to the same model).
- `PEXELS_API_KEY` — free key from https://www.pexels.com/api/ for stock visuals.
- Telegram/YouTube/Instagram vars can stay blank — nothing uses them yet (see
  `CLAUDE.md`'s "known gaps").

## 9. First manual bring-up (before trusting CI)

```bash
docker compose build
docker compose up -d
docker compose logs -f app
```
Watch for: `ollama-init` pulling the model → `alembic upgrade head` → `seed-admin` →
gunicorn starting. Then from any browser:
- `https://<your-domain>/api/health` → `{"status": "ok"}`
- `https://<your-domain>/` → the Antiquary login page, log in with `ADMIN_EMAIL` /
  `ADMIN_PASSWORD`.

If the cert doesn't issue, double check DNS has actually propagated
(`dig +short <your-domain>` should return your public IP) and that ports 80/443 are
really reaching the box (test with `curl -I http://<your-domain>` from outside your
network, e.g. your phone on mobile data).

## 10. Install the GitHub Actions self-hosted runner

This is what makes `git push` to `main` auto-deploy here.

On GitHub: repo → **Settings → Actions → Runners → New self-hosted runner** → Linux,
x64. It generates a one-time token — copy the exact commands it shows you (they look
like this, but the token is unique per run):
```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf actions-runner.tar.gz
./config.sh --url https://github.com/sarthax10/antiquary --token <TOKEN_FROM_GITHUB_UI>
sudo ./svc.sh install
sudo ./svc.sh start
```
This runner polls GitHub outward — no additional inbound port-forwarding needed for
deploys (separate concern from step 7, which is for serving the site itself).

Then add the `DOMAIN` repository **variable** (not secret — it's not sensitive):
**Settings → Secrets and variables → Actions → Variables → New repository variable**,
name `DOMAIN`, value matching your `.env`'s `DOMAIN`. The CI health check uses this to
know what URL to curl after deploying.

## 11. Verify the full loop

Make a trivial change locally (or just re-push), push to `main`, and watch
**Actions** tab on GitHub — it should pick up the job on your self-hosted runner,
rebuild, restart, and pass the health check.

## Ongoing operation

- **Data survives deploys.** `postgres_data` and `minio_data` are named Docker volumes
  — a normal `docker compose build && up -d` (what CI runs) never touches them. Only
  `docker compose down -v` or manually deleting a volume destroys data — never run that
  in normal operation.
- **Schema migrations** run automatically (`alembic upgrade head` on every app start,
  no-op if nothing changed) — never hand-edit the Postgres schema.
- **Back up regularly** — nothing backs itself up:
  ```bash
  docker run --rm -v postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data.tgz /data
  docker run --rm -v minio_data:/data -v $(pwd):/backup alpine tar czf /backup/minio_data.tgz /data
  ```
- **Changing the Ollama model**: edit `OLLAMA_MODEL` in `.env`, `docker compose up -d`
  — the `ollama-init` one-shot container pulls the new model before `app` restarts.
- **Logs**: `docker compose logs -f <service>` (`app`, `caddy`, `postgres`, `minio`,
  `ollama`).

## If something's broken

- `docker compose ps` — is everything `Up`/`healthy`?
- `docker compose logs app` — most application errors surface here.
- `docker compose logs caddy` — TLS/certificate issues surface here.
- Check `docs/ARCHITECTURE.md` for how the pieces fit together before changing code.
