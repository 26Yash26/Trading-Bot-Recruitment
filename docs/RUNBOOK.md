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

That serves the API *and* the static site on one port, same routes as
production, minus nginx. Nothing else to start.

`seed_demo` prints an admin session cookie. To open `/admin` locally:

```bash
QG_ADMIN_EMAILS=demo.admin@smail.iitm.ac.in python -m server
```

then paste the printed `qg_session=...` into a cookie for `localhost`. (With
real Google OAuth configured you just sign in instead.)

To see a leaderboard immediately, open `/admin`, set **rounds per game** to 300,
cut the iteration list down to one row, and press **Run a showdown now**. That
takes a few seconds instead of a few minutes.

### Editing the frontend

```bash
./scripts/build_css.sh --watch   # rebuild web/css/app.css on change
```

It downloads Tailwind's standalone binary into `~/.cache/quantguild` on first
run. No node, no npm, no `node_modules`. **Commit `web/css/app.css`**, the VM
does not build anything.

### Tests

```bash
pytest                # 284 tests
pytest tests/test_sandbox.py -v   # the ones that matter
```

Run this on Linux/macOS/WSL, the sandbox is POSIX-only, so on native Windows the
bot-spawning tests skip (you'll see ~10 skips, 0 failures; the AST-policy tests
still run). No CI runs `pytest` yet, so run it yourself before merging.

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

It must match `QG_OAUTH_REDIRECT_URI` exactly, no trailing slash.

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
the API whenever Actions deploys, the workflow itself restarts nothing, and
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
and `sudo systemctl restart quantguild`, session cookies only get the `Secure`
flag when the origin is HTTPS.

### 9. First run

Open `/admin` (signed in with an email from `QG_ADMIN_EMAILS`):

1. **Sandbox & secrets** → confirm the isolation tier says **Bubblewrap** or
   **Docker**, in green.
2. **Sandbox & secrets** → set the four hidden `(min, max)` distribution bounds
   and the master seed. These are never sent to a browser.
3. **Showdown** → set the interval and the rounds, and **Game & tournament** →
   the iteration list. Watch the estimated cost: it warns if a showdown would
   take more than 70% of the interval.
4. Press **Run a showdown now** to prove the pipeline end to end.

---

## One-time: adopt the self-syncing deploy script

**Run this once, before the orientation session.** Until it is done, changes to
`deploy/nginx-app.conf` and `deploy/apply-deploy.sh` are committed to the repo
and never reach production.

The systemd unit runs `/opt/quantguild/bin/apply-deploy.sh` and nginx reads
`/etc/nginx/snippets/quantguild-app.conf`, both are *copies* installed by
`setup_vm.sh`, which is run by hand. So the repo can say one thing while the VM
does another, with nothing to indicate it. `apply-deploy.sh` now syncs the nginx
snippet on every deploy, but that change cannot install itself.

```bash
cd /var/www/html
git log -1 --format='%h %s'          # confirm the deploy landed first

# The caching fix, static assets must revalidate, or a deploy strands anyone
# with the site open on a half-stale ES module graph (blank page, no error).
sudo install -m 644 deploy/nginx-app.conf /etc/nginx/snippets/quantguild-app.conf
sudo nginx -t && sudo systemctl reload nginx

# The script that will keep the above in sync from now on.
sudo install -m 755 deploy/apply-deploy.sh /opt/quantguild/bin/apply-deploy.sh
```

Verify from anywhere:

```bash
curl -sI https://quantguildiitm.in/web/js/main.js | grep -i cache-control
# want exactly:  Cache-Control: no-cache
# not:           Cache-Control: public, max-age=3600
```

After this, a normal `git push` carries nginx changes too.

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
| Roll back a deploy | `git revert <sha> && git push`, the path unit restarts the API |

### Mock auction 1, and releasing variations 3 and 4

Back up `/var/lib/quantguild` first, it holds every submission.

Mock auction 1 runs on variations 1 and 2 only. Releasing 3 and 4 is the same
moment, and it is **irreversible**: once the kit has been downloaded it cannot
be un-downloaded, so do the run first and the release second.

1. **Back up.** `sudo tar czf ~/qg-$(date +%F).tar.gz /var/lib/quantguild`
2. **Run the mock.** Admin → Showdown → **Mock auction** (not *Practice*, the
   stamp decides whether the board is archived and what the next mock seeds on).
   Let it finish, check the board, send participants their per-block numbers.
   The board stays reachable from the leaderboard's *Boards* picker afterwards,
   so the practice clock replacing the live one does not lose it.
3. **Build the released kit**, locally, on a branch:

   ```bash
   python build_kit.py --release-v3-v4
   python -m pytest tests/test_embargo.py tests/test_late_kit.py -q
   ```

   That pulls `late-kit/` into `public/starter-kit.zip`: `Template_3.py`,
   `Template_4.py`, `README_v3_v4.md`, and the four-variation `local_test.py`
   replacing the two-variation one. It also rewrites the embargo notice at the
   top of the kit README. Commit the rebuilt zip, the VM has no build step.

   Note that `test_committed_zip_is_what_a_fresh_build_produces` compares the
   committed zip against a **pre-release** build, so it fails by design from
   here on. Flip it, or drop it, in the same commit, do not leave a red suite
   over an event weekend.

4. **Push.** The deploy is the release: `/public/` is served `no-cache`, so the
   kit URL changes meaning without anyone re-bookmarking anything.
5. **Open the variations.** Admin → variations → tick 3 and 4. This is what
   makes `/api/variations/late.js` return 200 instead of 404, pushes the new
   rules to every open browser over the leaderboard SSE stream, and makes the
   submit endpoint accept `_3.py` and `_4.py`. Nothing about V3 or V4 is on the
   wire until this switch is flipped, verify with
   `curl -sI https://quantguildiitm.in/api/variations/late.js`.
6. **Announce**, with the banner in Admin → announcement.

Steps 4 and 5 are independent: the kit can go out before the switch, or after.
Doing 5 first with an un-rebuilt kit is the bad ordering, the site would
describe two variations the download says nothing about.

### Mock auction 2 (all four variations)

Same as above minus the release. Set Admin → variations to all four before the
run; a bot submitted for a variation that is not enabled is not collected by
`Scheduler.collect_field`, so an unticked variation silently plays nobody.

### Run kinds

Every showdown is stamped `practice`, `mock` or `final`. It is not cosmetic:

| | `practice` | `mock` | `final` |
|---|---|---|---|
| Started by | the clock, and the Practice button | the Mock button | the Final button |
| Board | rewritten by the next tick | archived, listed on the site | archived, listed |
| Seeds a balanced/finals run from | the last practice run | the last mock | the last final |

The clock only ever produces `practice` runs, and a kind chosen in the console
applies to **one** run and then falls back, a forgotten switch cannot mislabel
the 2am tick. `POST /api/admin/run-now {"kind": ...}` is audited.

### What a showdown is

A showdown is the whole tournament: five iterations, the first two on random
groups, the third strength balanced, the last two a finals between the leading
`finals_size` bots. That is the shipped default, so an ordinary Run now already
plays it.

Admin → Game & tournament → **Iterations in a showdown** is the control. It is
one list: each row is an iteration and its grouping, `+ add an iteration` and
the `x` on a row change the count, and every button saves immediately.
`iterations` follows the length of the list, so the two cannot disagree. The
**standard showdown** preset rewrites the list to the five above.

There used to be a separate "Iterations per variation" number field. It saved
only on the Save button while the grouping buttons saved immediately, so typing
5 and then clicking a grouping repainted the page and threw the 5 away, and the
extra iterations could never be given a mode. The number field is gone.

### Running one variation at a time

The variation chips above the Run buttons say what **this run** covers. They are
not the release switch. Turn some off to replay a single variation.

That is safe because the live board takes each variation from the newest run
that scored it, so the others keep whatever they had. A run refuses a variation
that is not released, rather than quietly playing nobody.

### The scoring PDF

`docs/scoring.tex` builds two PDFs, both committed:

```bash
./scripts/build_docs.sh
```

`scoring-public.pdf` (variations 1 and 2) and `scoring.pdf` (all four).
`/api/docs/scoring.pdf` serves whichever the released variations allow, so the
switch that opens V3 and V4 swaps the document too, no separate step. The
script refuses to finish if the public build mentions an unreleased variation,
and `tests/test_embargo.py` checks the committed PDFs the same way.

Rebuild and commit both whenever `scoring.tex` changes; the VM has no TeX.

### Sizing

One 2000-round game with 20 sandboxed bots takes about 15 s. With `n`
participants the cost per showdown is roughly

```
variations × repeats × ceil(n / 20) × len(starting_capitals) × 15 s ÷ workers
```

100 participants, 3 variations, 3 repeats, 1 capital, 4 workers ≈ 11 minutes,
comfortable inside a 2-hour interval. The admin page computes this for you.
