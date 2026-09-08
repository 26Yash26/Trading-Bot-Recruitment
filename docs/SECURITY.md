# Security model

We run arbitrary Python written by a few hundred undergraduates, on a VM that
also serves a public website, and we publish a leaderboard people care about.
This is what stops that from going wrong.

---

## 1. The thing that makes this deployment unusual

`.github/workflows/deploy.yml` SSHes into the VM and runs, inside
`/var/www/html`:

```
git fetch origin main
git reset --hard origin/main
```

So **`/var/www/html` is a checkout of this entire private repo**, and nginx's
document root points at it. Private on GitHub does not mean private over HTTP.
A default nginx config would happily serve `/secret/config.py`, `/server/store.py`
and `/.git/config` to anyone who guessed the path.

The fix is that **no request path is ever turned into a file path**, except
under an explicit allowlist:

| Path | Served |
|---|---|
| `/api/...` | proxied to the API on `127.0.0.1:8000` |
| `/web/...` | static assets (`try_files $uri =404`) |
| `/public/...` | downloads: the starter kit (`try_files $uri =404`) |
| everything else | `index.html`, with no `$uri` in the `try_files` |

Because the catch-all never consults `$uri`, traversal has nothing to traverse:
`/secret/config.py`, `/../secret/config.py` and `/%2e%2e/secret/config.py` all
render the single-page app. `deploy/nginx.conf` also has a redundant `return 404`
block for the sensitive directories, so that a future edit that reintroduces
`try_files $uri` fails loudly instead of silently exposing the repo.

`tests/test_server.py::test_no_request_path_becomes_a_file_path` asserts this
against the same route table the app serves locally.

**Secrets are not in the repo at all.** The OAuth client secret, admin list and
public origin live in `/etc/quantguild.env` (mode 640, outside the web root).
The database and every uploaded bot file live in `/var/lib/quantguild`.

---

## 2. Running participant code

Three layers. Each one assumes the others may fail.

### Layer 1 — static policy (`sandbox/policy.py`)

Runs at upload time, before the file is ever executed. It parses the submission
to an AST and applies an **allowlist**:

- imports must resolve to a known-good root module (`math`, `random`,
  `itertools`, `numpy`, `pandas`, `scipy`, `sklearn`, …),
- `eval`, `exec`, `compile`, `open`, `__import__`, `getattr`, `setattr`,
  `globals`, `locals`, `vars` and friends are rejected,
- **any** dunder attribute access is rejected — `__class__`, `__globals__`,
  `__subclasses__`, `__mro__`, `__code__`,
- the file must define a top-level `class Bot` with `get_bid`.

> Last year's site used a list of banned *substrings* (`"import os"`,
> `"__class__"`). That loses to `getattr(obj, "__cla" + "ss__")` and to
> `__im` `port__`. Parsing to an AST and allowing only what we recognise closes
> that whole family of bypasses — which is why `getattr` is banned outright even
> though it is a perfectly reasonable function.

This layer is a fast, friendly rejection with a line number, not the real
boundary. Assume a determined participant gets past it.

### Layer 2 — the process (`sandbox/child.py`)

Every bot runs in its own process. Before a single line of participant code is
imported, that process:

- **takes stdout away from the bot.** The protocol is newline-delimited JSON on
  the pipe; the child dups the real stdout to a private fd and points fd 1 at
  `/dev/null`. A bot that prints `{"ok": true, "bid": 999999}` cannot forge a
  bid. (`test_bot_stdout_cannot_forge_a_bid`)
- applies `setrlimit`: `RLIMIT_AS` (address space), `RLIMIT_CPU` (total CPU for
  the game), **`RLIMIT_FSIZE = 0`** so it cannot write a single byte anywhere,
  `RLIMIT_NPROC = 0` so it cannot fork, `RLIMIT_NOFILE = 64`, `RLIMIT_CORE = 0`.
- neuters `socket` — belt and braces for the plain-subprocess fallback, where
  there is no network namespace to rely on.

### Layer 3 — isolation (`sandbox/runner.py`)

`detect_isolation()` picks the strongest tier available on the host:

| Tier | What the bot gets |
|---|---|
| `docker` | container, `--network none`, read-only rootfs, `--cap-drop ALL`, `--pids-limit 16`, `no-new-privileges` |
| `bwrap` | user + net + PID + IPC namespace, read-only `/usr`, tmpfs cwd, **no `/home`, no `/etc`, no repo**, `--die-with-parent` |
| `unshare` | network namespace only; the filesystem is protected by rlimits alone |
| `sudo` | a dedicated unprivileged account, no namespaces |
| `plain` | rlimits and in-process shims only — **development fallback, not acceptable on the VM** |

Verified under `bwrap`: reading `/etc/passwd` fails with `FileNotFoundError`,
reading `/var/www/html/secret/config.py` fails the same way, and connecting to
`1.1.1.1` fails with `ENETUNREACH`.

The admin console shows the tier in use and warns in red when it is `plain`.
Install bubblewrap on the VM (`sudo apt install bubblewrap`) — it needs no
daemon and no image build, unlike Docker.

### Why one process per bot, not one per group

A per-round timeout is only enforceable if the thing you kill is *just that
bot*. Running twenty bots in one interpreter would mean an infinite loop in one
submission hangs its nineteen neighbours, a memory blow-up kills the group, and
bots share an address space. Twenty pipes costs about 15 s per 2000-round game —
cheap for what it buys.

### Failure handling

Every failure mode reaches the engine as an exception, which `auction.player.Player`
already turns into a bid of `0` plus an incremented error count:

| Failure | Result |
|---|---|
| exceeded the round timeout | killed, disqualified for that game |
| exceeded memory | `MemoryError` or process death, disqualified |
| raised inside `get_bid` | bid 0 that round; disqualified after 25 consecutive |
| crashed in `__init__` | disqualified before round 0, game continues |
| returned NaN / inf / negative / a string | `Player._sanitise` files it as an illegal bid → 0 |

A disqualified bot never breaks its group's game — it sits out and sorts last.

---

## 3. The web application

**Authentication.** Google OAuth, restricted to `@smail.iitm.ac.in`, with
`verified_email` checked. The OAuth `state` parameter is generated per attempt,
stored in a short-lived `HttpOnly` cookie and compared in constant time — a
callback without a matching state cookie is refused, so a sign-in cannot be
completed on someone else's behalf.

**Sessions** are opaque 32-byte tokens in an `HttpOnly`, `SameSite=Lax`,
`Secure`-when-HTTPS cookie, stored server-side with an expiry. JavaScript never
sees the token.

> Last year's site passed the session token back in the redirect **URL**
> (`?token=...`) and kept it in `sessionStorage`. That puts credentials in
> browser history, in the Referer header and within reach of any XSS. The cookie
> approach here is a deliberate change.

**Identity binding.** A smail local part *is* a roll number, so the roll is
derived from the email and a submission whose filename claims a different roll
is rejected. You cannot submit as someone else.

**CSRF.** `SameSite=Lax` stops a cross-site form POST from carrying the session
cookie, and every state-changing endpoint additionally checks `Origin`.

**Rate limiting.** Per IP per route (6 submissions/minute), plus a per-roll
cooldown (60 s, admin-tunable). Uploads are capped at 512 KB and must decode as
UTF-8.

**Authorisation.** Admin is an email allowlist in the environment, checked
server-side on every admin route. Hiding the nav link is cosmetic.

**Content-Security-Policy.** `default-src 'self'`, `script-src 'self'`, no
`unsafe-inline` — which is why the frontend has no inline `<script>`, no
`onclick=` handlers, and no `style="..."` attributes anywhere. Dynamic styling
(progress bar widths) is set through the CSSOM, which CSP permits.

**XSS.** All markup is built from template strings, and every value that came
from a person — names, roll numbers, sandbox rejection messages — goes through
`esc()`. A participant who names themselves `<img onerror=...>` renders as text.

**Leaking the game.** `block_bounds` (the hidden distribution) and `seed` are
filtered out of every public response by `store.public_settings()`; only the
admin endpoint returns them. `tests/test_server.py::test_state_never_leaks_the_hidden_distribution`
guards this.

---

## 4. Known gaps

- **The `plain` tier is not safe for the VM.** Install bubblewrap or Docker
  before real submissions arrive. The admin page says so in red.
- **No HTTPS yet.** Run certbot, then set `QG_PUBLIC_ORIGIN=https://...` so
  cookies get the `Secure` flag. Until then sessions travel in clear text.
- **The memory ceiling is 512 MB, not the 100 MB the PS quotes.** numpy and
  pandas cost most of 100 MB just to import, and a false disqualification is
  worse than a generous limit. Tunable from the admin page.
- **A bot can still burn its full CPU budget every round.** It is bounded
  (1 s/round, 300 s/game) but a field of slow bots makes a showdown slow. The
  admin page shows an estimated wall-clock cost and warns when it exceeds 70% of
  the interval.
- **No per-participant audit of submitted source beyond the policy check.**
  Read the winners' code before shortlisting.
