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

systemctl restart quantguild.service
echo "deploy applied: $(cd "$REPO" && git log -1 --format='%h %s')"
