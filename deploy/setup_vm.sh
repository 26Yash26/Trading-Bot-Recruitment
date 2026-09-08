#!/usr/bin/env bash
# One-shot, idempotent VM setup. Run as root on the GCP instance:
#
#   sudo bash /var/www/html/deploy/setup_vm.sh
#
# Safe to re-run: it never overwrites /etc/quantguild.env, never touches the
# database, and skips anything already in place. It does the root-level half of
# docs/RUNBOOK.md §"VM setup"; the parts needing your Google OAuth client stay
# manual because only you have those values.
set -euo pipefail

REPO=/var/www/html
# Deploy assets are taken from this script's own directory, so it works both
# from the deployed checkout and from a staging copy pushed ahead of the code.
ASSETS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV=/opt/quantguild/venv
DATA=/var/lib/quantguild
SVC_USER=quantguild

log()  { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m %s\n' "$*"; }
warn() { printf '    \033[31m!!\033[0m %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "run me with sudo"; exit 1; }

# --- packages ---------------------------------------------------------------
log "packages"
missing=()
for pkg in bubblewrap python3-venv sqlite3; do
    dpkg -s "$pkg" &>/dev/null || missing+=("$pkg")
done
if ((${#missing[@]})); then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
    ok "installed: ${missing[*]}"
else
    ok "bubblewrap, python3-venv, sqlite3 already present"
fi

# bubblewrap is what actually contains participant code. Without it the sandbox
# silently falls back to a weaker tier.
command -v bwrap >/dev/null && ok "bwrap: $(bwrap --version)" || warn "bwrap MISSING"

# --- service account and directories ----------------------------------------
log "service account and directories"
if id "$SVC_USER" &>/dev/null; then
    ok "user $SVC_USER exists"
else
    useradd --system --create-home --shell /usr/sbin/nologin "$SVC_USER"
    ok "created user $SVC_USER"
fi

install -d -o "$SVC_USER" -g "$SVC_USER" -m 700 "$DATA"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 755 /opt/quantguild /opt/quantguild/bin
ok "$DATA (0700) and /opt/quantguild ready"

# --- virtualenv --------------------------------------------------------------
log "virtualenv"
if [[ ! -x "$VENV/bin/python" ]]; then
    sudo -u "$SVC_USER" python3 -m venv "$VENV"
    ok "created $VENV"
fi
if [[ -f "$REPO/requirements.txt" ]]; then
    sudo -u "$SVC_USER" "$VENV/bin/pip" install --quiet --upgrade pip
    sudo -u "$SVC_USER" "$VENV/bin/pip" install --quiet -r "$REPO/requirements.txt"
    sha256sum "$REPO/requirements.txt" | cut -d' ' -f1 > /opt/quantguild/.requirements.sha256
    ok "dependencies installed"
else
    warn "no $REPO/requirements.txt yet — deploy the new code, then re-run this"
fi

# --- secrets -----------------------------------------------------------------
log "secrets"
if [[ -f /etc/quantguild.env ]]; then
    ok "/etc/quantguild.env exists (left untouched)"
else
    if [[ -f "$ASSETS/quantguild.env.example" ]]; then
        cp "$ASSETS/quantguild.env.example" /etc/quantguild.env
    else
        cat > /etc/quantguild.env <<'ENVEOF'
QG_GOOGLE_CLIENT_ID=
QG_GOOGLE_CLIENT_SECRET=
QG_ALLOWED_DOMAIN=smail.iitm.ac.in
QG_ADMIN_EMAILS=
QG_PUBLIC_ORIGIN=http://35.226.121.223
QG_OAUTH_REDIRECT_URI=http://35.226.121.223/api/auth/callback
ENVEOF
    fi
    warn "created /etc/quantguild.env — YOU MUST FILL IN the OAuth client and admin emails"
fi
chown root:"$SVC_USER" /etc/quantguild.env
chmod 640 /etc/quantguild.env
ok "/etc/quantguild.env is root:$SVC_USER 0640 (outside the web root)"

# --- deploy hook -------------------------------------------------------------
log "deploy hook"
if [[ -f "$ASSETS/apply-deploy.sh" ]]; then
    install -m 755 "$ASSETS/apply-deploy.sh" /opt/quantguild/bin/apply-deploy.sh
    ok "installed /opt/quantguild/bin/apply-deploy.sh"
else
    warn "apply-deploy.sh not found next to this script"
fi

# --- systemd -----------------------------------------------------------------
log "systemd units"
if compgen -G "$ASSETS/systemd/*" >/dev/null; then
    install -m 644 "$ASSETS"/systemd/*.service "$ASSETS"/systemd/*.path /etc/systemd/system/
    systemctl daemon-reload
    ok "units installed"

    # The API can only start once the new code is on main. Enable it either way
    # so a later deploy brings it up on its own.
    systemctl enable quantguild.service >/dev/null 2>&1 || true
    systemctl enable --now quantguild-deploy.path >/dev/null 2>&1 || true
    ok "quantguild-deploy.path enabled (restarts the API on every deploy)"

    if [[ -f "$REPO/server/app.py" ]]; then
        systemctl restart quantguild.service
        sleep 3
        if systemctl is-active --quiet quantguild.service; then
            ok "quantguild.service is running"
        else
            warn "quantguild.service failed — journalctl -u quantguild -n 40"
        fi
    else
        warn "server/ not deployed yet; leaving quantguild.service stopped"
    fi
else
    warn "systemd/ not found next to this script"
fi

# --- nginx -------------------------------------------------------------------
log "nginx"
if [[ -f "$ASSETS/nginx.conf" && -f "$ASSETS/nginx-app.conf" ]]; then
    # Snapshot what is live so a broken rollout can be undone completely.
    BACKUP=/root/nginx-backup-$(date +%Y%m%d-%H%M%S)
    mkdir -p "$BACKUP"
    cp -a /etc/nginx/sites-available /etc/nginx/sites-enabled "$BACKUP"/ 2>/dev/null || true
    ok "backed up nginx config to $BACKUP"

    install -d -m 755 /etc/nginx/snippets
    install -m 644 "$ASSETS/nginx-app.conf" /etc/nginx/snippets/quantguild-app.conf
    install -m 644 "$ASSETS/nginx.conf"     /etc/nginx/sites-available/quantguild
    ln -sf /etc/nginx/sites-available/quantguild /etc/nginx/sites-enabled/quantguild
    rm -f /etc/nginx/sites-enabled/default

    rollback_nginx() {
        warn "rolling nginx back to the previous config"
        rm -f /etc/nginx/sites-enabled/quantguild
        cp -a "$BACKUP/sites-enabled/." /etc/nginx/sites-enabled/ 2>/dev/null || true
        systemctl reload nginx || systemctl restart nginx || true
    }

    if ! nginx -t 2>&1 | tail -2; then
        rollback_nginx; exit 1
    fi
    systemctl reload nginx
    sleep 2

    # `nginx -t` only proves the syntax parses. A config that dropped the TLS
    # listener would validate perfectly and take HTTPS down, so check what the
    # server actually answers before calling this a success.
    http_ok=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://localhost/ || echo 000)
    tls_ok=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 https://localhost/ || echo 000)
    if [[ "$http_ok" != "200" || "$tls_ok" != "200" ]]; then
        warn "post-reload check failed (http=$http_ok https=$tls_ok)"
        rollback_nginx
        exit 1
    fi
    ok "allowlist active on 80 and 443 (http=$http_ok https=$tls_ok); default site removed"
else
    warn "nginx.conf / nginx-app.conf not found next to this script — document root still exposed"
fi

# --- belt and braces ---------------------------------------------------------
# Even with the nginx allowlist, drop the "other" bits on organiser-only paths so
# a future config mistake cannot re-expose them. Directory modes survive
# `git reset --hard`, and git runs as the checkout owner, so deploys still work.
log "filesystem hardening"
cd "$REPO"
for p in .git .github secret harness tests docs server sandbox scripts deploy conftest.py; do
    [[ -e "$p" ]] && chmod -R o-rwx "$p" 2>/dev/null && ok "blocked $p"
done

# --- verify ------------------------------------------------------------------
log "verification"
BASE=${QG_VERIFY_BASE:-https://quantguildiitm.in}
fail=0
for path in /.git/config /.git/HEAD /.git/index /secret/config.example.py /server/store.py \
            /harness/evaluate.py /tests/test_engine.py /conftest.py /docs/BUILD_CHECKLIST.md \
            /src/auction/engine.py /requirements.txt; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 "$BASE$path" || echo "---")
    if [[ "$code" == "200" ]]; then warn "STILL EXPOSED $path -> $code"; fail=1
    else ok "$path -> $code"; fi
done
for path in / /leaderboard /rules; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 "$BASE$path" || echo "---")
    ok "site $path -> $code"
done
(( fail == 0 )) && ok "nothing from the checkout is reachable" || warn "SOME PATHS ARE STILL PUBLIC"

cat <<'DONE'

--------------------------------------------------------------------
Remaining manual steps (they need values only you have):

  1. Edit /etc/quantguild.env — Google OAuth client id/secret and
     QG_ADMIN_EMAILS. Then: sudo systemctl restart quantguild
  2. Register the redirect URI in Google Cloud Console, exactly:
       <QG_PUBLIC_ORIGIN>/api/auth/callback
  3. HTTPS:  sudo certbot --nginx -d <domain>
     then set QG_PUBLIC_ORIGIN=https://<domain> in /etc/quantguild.env
     and restart, so session cookies get the Secure flag.
  4. In /admin: set the hidden distribution bounds and the master seed.
--------------------------------------------------------------------
DONE
