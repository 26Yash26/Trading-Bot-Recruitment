# Runbook

Two audiences: running the site on your laptop, and standing it up on the VM.

---

## Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed_demo      # optional: 18 fake participants
python -m server                 # http://localhost:8000
```

That serves the API *and* the static site on one port — same routes as
production, minus nginx. Nothing else to start.

`seed_demo` prints an admin session cookie. To open `/admin` locally:

```bash
QG_ADMIN_EMAILS=demo.admin@smail.iitm.ac.in python -m server
```

then paste the printed `qg_session=...` into a cookie for `localhost`. (With
real Google OAuth configured you just sign in instead.)

To see a leaderboard immediately, open `/admin`, set **rounds per game** to 300
and **repeats** to 1, and press **Run a showdown now** — that takes a few
seconds instead of a few minutes.

### Editing the frontend

```bash
./scripts/build_css.sh --watch   # rebuild web/css/app.css on change
```

It downloads Tailwind's standalone binary into `~/.cache/quantguild` on first
run. No node, no npm, no `node_modules`. **Commit `web/css/app.css`** — the VM
does not build anything.

### Tests

```bash
pytest                # 86 tests
pytest tests/test_sandbox.py -v   # the ones that matter
```

---

## VM setup (once)

Assumes the existing setup from `GCP-VM-GitHub-Actions-CICD-Guide.md`:
`/var/www/html` is already a git clone that Actions hard-resets on every push.

### 1. Install bubblewrap

**Do this before real submissions arrive.** Without it the sandbox falls back to
a weaker tier, and the admin page will say so in red.

```bash
sudo apt update && sudo apt install -y bubblewrap python3-venv
```

### 2. Service account and directories

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin quantguild
sudo mkdir -p /var/lib/quantguild /opt/quantguild/bin
sudo chown -R quantguild:quantguild /var/lib/quantguild /opt/quantguild
sudo chmod 700 /var/lib/quantguild
```

The web root stays owned by the deploy user; only `/var/lib/quantguild` is
writable by the service.

### 3. Virtualenv (outside the web root)

```bash
sudo -u quantguild python3 -m venv /opt/quantguild/venv
sudo -u quantguild /opt/quantguild/venv/bin/pip install -r /var/www/html/requirements.txt
```

### 4. Secrets

```bash
sudo cp /var/www/html/deploy/quantguild.env.example /etc/quantguild.env
sudo nano /etc/quantguild.env          # fill in the OAuth client and admin emails
sudo chown root:quantguild /etc/quantguild.env
sudo chmod 640 /etc/quantguild.env
```

### 5. Google OAuth

console.cloud.google.com → APIs & Services → Credentials → OAuth client ID
(Web application).

- Authorised JavaScript origin: `https://quantguildiitm.in`
- Authorised redirect URI: `https://quantguildiitm.in/api/auth/callback`

It must match `QG_OAUTH_REDIRECT_URI` exactly — no trailing slash.

### 6. systemd

```bash
sudo cp /var/www/html/deploy/systemd/*.service /var/www/html/deploy/systemd/*.path /etc/systemd/system/
sudo cp /var/www/html/deploy/apply-deploy.sh /opt/quantguild/bin/
sudo chmod +x /opt/quantguild/bin/apply-deploy.sh

sudo systemctl daemon-reload
sudo systemctl enable --now quantguild.service
sudo systemctl enable --now quantguild-deploy.path
sudo systemctl status quantguild.service
```

`quantguild-deploy.path` watches `/var/www/html/.git/FETCH_HEAD` and restarts
the API whenever Actions deploys — the workflow itself restarts nothing, and
`.github/` is not to be edited.

### 7. nginx

```bash
sudo cp /var/www/html/deploy/nginx.conf /etc/nginx/sites-available/quantguild
sudo ln -sf /etc/nginx/sites-available/quantguild /etc/nginx/sites-enabled/quantguild
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Then confirm the document root is not exposed:

```bash
curl -s https://quantguildiitm.in/secret/config.py | head -1   # must be <!DOCTYPE html>
curl -s https://quantguildiitm.in/server/store.py  | head -1   # must be <!DOCTYPE html>
curl -s https://quantguildiitm.in/.git/config      | head -1   # must be <!DOCTYPE html>
```

If any of those returns Python or git config, **stop and fix nginx before
announcing the site**.

### 8. HTTPS

```bash
sudo certbot --nginx -d quantguildiitm.in -d www.quantguildiitm.in
```

Then set `QG_PUBLIC_ORIGIN=https://quantguildiitm.in` in `/etc/quantguild.env`
and `sudo systemctl restart quantguild` — session cookies only get the `Secure`
flag when the origin is HTTPS.

### 9. First run

Open `/admin` (signed in with an email from `QG_ADMIN_EMAILS`):

1. **Sandbox & secrets** → confirm the isolation tier says **Bubblewrap** or
   **Docker**, in green.
2. **Sandbox & secrets** → set the four hidden `(min, max)` distribution bounds
   and the master seed. These are never sent to a browser.
3. **Showdown** → set the interval, rounds, repeats and starting capitals.
   Watch the estimated cost — it warns if a showdown would take more than 70% of
   the interval.
4. Press **Run a showdown now** to prove the pipeline end to end.

---

## Operations

| Task | How |
|---|---|
| Watch the API | `sudo journalctl -u quantguild -f` |
| Restart | `sudo systemctl restart quantguild` |
| Pause showdowns | Admin → **Run showdowns automatically** off |
| Close submissions | Admin → **Accept new submissions** off |
| Ban a roll number | Admin → Submissions → **Ban** |
| Back up everything | `sudo tar czf ~/qg-$(date +%F).tar.gz /var/lib/quantguild` |
| Inspect the database | `sudo -u quantguild sqlite3 /var/lib/quantguild/quantguild.db` |
| Roll back a deploy | `git revert <sha> && git push` — the path unit restarts the API |

### Before the mock auction (20 Sep)

Back up `/var/lib/quantguild` first — it holds every submission.

### Sizing

One 2000-round game with 20 sandboxed bots takes about 15 s. With `n`
participants the cost per showdown is roughly

```
variations × repeats × ceil(n / 20) × len(starting_capitals) × 15 s ÷ workers
```

100 participants, 3 variations, 3 repeats, 1 capital, 4 workers ≈ 11 minutes —
comfortable inside a 2-hour interval. The admin page computes this for you.
