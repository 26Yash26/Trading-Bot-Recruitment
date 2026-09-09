#!/usr/bin/env bash
# Installed to /opt/quantguild/bin/apply-deploy.sh and run by
# quantguild-deploy.service whenever a deploy lands in /var/www/html.
set -euo pipefail

REPO=/var/www/html
VENV=/opt/quantguild/venv
STAMP=/opt/quantguild/.requirements.sha256

# Only rebuild the venv when the dependency list actually changed — a restart
# should be a couple of seconds, not a pip resolve.
current=$(sha256sum "$REPO/requirements.txt" | cut -d' ' -f1)
previous=$(cat "$STAMP" 2>/dev/null || echo "")

if [[ "$current" != "$previous" ]]; then
    echo "requirements.txt changed — updating the virtualenv"
    "$VENV/bin/pip" install --quiet --upgrade -r "$REPO/requirements.txt"
    echo "$current" > "$STAMP"
fi

# The nginx snippet used to install only from setup_vm.sh, which is run by hand.
# So a routing or caching change committed to the repo silently never reached the
# VM — the file was right in git and wrong in production, with nothing to say so.
# Sync it here, but never let a bad snippet take the site down: validate first,
# restore on failure, and treat the whole step as non-fatal so a config mistake
# cannot block the API restart below.
SNIPPET_SRC="$REPO/deploy/nginx-app.conf"
SNIPPET_DST=/etc/nginx/snippets/quantguild-app.conf

if [[ -f "$SNIPPET_SRC" ]] && ! cmp -s "$SNIPPET_SRC" "$SNIPPET_DST"; then
    echo "nginx snippet changed — validating"
    BACKUP=$(mktemp)
    cp -a "$SNIPPET_DST" "$BACKUP" 2>/dev/null || true
    install -m 644 "$SNIPPET_SRC" "$SNIPPET_DST"

    if nginx -t >/dev/null 2>&1; then
        systemctl reload nginx && echo "nginx reloaded with the new snippet"
    else
        echo "WARNING: new nginx snippet failed validation — keeping the old one" >&2
        nginx -t 2>&1 | tail -3 >&2
        if [[ -s "$BACKUP" ]]; then
            install -m 644 "$BACKUP" "$SNIPPET_DST"
        else
            rm -f "$SNIPPET_DST"
        fi
        nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
    fi
    rm -f "$BACKUP"
fi

systemctl restart quantguild.service
echo "deploy applied: $(cd "$REPO" && git log -1 --format='%h %s')"
