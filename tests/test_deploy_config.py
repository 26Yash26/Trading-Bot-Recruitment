"""Deploy-time configuration that has bitten us, pinned so it cannot come back.

These assert on `deploy/*.conf` as text rather than on a running nginx, because
the failure they guard is silent: the site keeps serving, it just serves the
wrong thing, and nobody notices until a participant reports a blank page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NGINX_APP = REPO_ROOT / "deploy" / "nginx-app.conf"
APPLY_DEPLOY = REPO_ROOT / "deploy" / "apply-deploy.sh"


def _location_block(conf: str, prefix: str) -> str:
    """The body of `location ^~ <prefix> { ... }`."""
    match = re.search(
        r"location\s+\^~\s+" + re.escape(prefix) + r"\s*\{(.*?)\n\}",
        conf,
        re.DOTALL,
    )
    assert match, f"no `location ^~ {prefix}` block in nginx-app.conf"
    return match.group(1)


@pytest.mark.parametrize("prefix", ["/web/", "/public/"])
def test_static_assets_are_not_cached_without_revalidation(prefix):
    """The JS has no content hash, so a cached copy must never be used blind.

    `index.html` is `no-cache`, so a returning visitor revalidates the HTML and
    then pulls the module graph from cache. ES modules resolve every import
    before executing anything, so one stale file missing an export that a fresh
    file imports is a link-time failure of the WHOLE graph — a blank page with
    no error, persisting for the whole max-age. A deploy mid-event would have
    done that to everyone with the site already open.

    `no-cache` still allows storage; nginx answers with a 304 off the ETag.
    """
    body = _location_block(NGINX_APP.read_text(encoding="utf-8"), prefix)

    assert "no-cache" in body, f"{prefix} must send Cache-Control: no-cache"
    assert not re.search(r"max-age=(?!0)\d+", body), (
        f"{prefix} sets a positive max-age — a deploy will strand returning "
        "visitors on a half-stale module graph"
    )
    assert not re.search(r"^\s*expires\s+(?!-1)", body, re.MULTILINE), (
        f"{prefix} uses `expires`, which emits a second Cache-Control header "
        "alongside add_header"
    )


def test_nginx_snippet_is_synced_on_deploy():
    """A config change in git that never reaches the VM is worse than no change:
    the repo says one thing and production does another."""
    script = APPLY_DEPLOY.read_text(encoding="utf-8")
    assert "nginx-app.conf" in script, "apply-deploy.sh does not sync the snippet"
    assert "nginx -t" in script, "the snippet is installed without validation"
    assert "systemctl reload nginx" in script


def test_snippet_sync_cannot_break_the_deploy():
    """A bad snippet must not leave nginx down or stop the API restarting."""
    script = APPLY_DEPLOY.read_text(encoding="utf-8")
    restart = script.index("systemctl restart quantguild.service")
    sync = script.index("nginx-app.conf")
    assert sync < restart, "the API restart must come after the nginx sync"
    # `set -e` is on, so every failing branch needs an explicit escape hatch.
    assert "|| true" in script[sync:restart], (
        "the nginx sync can abort the script under `set -e`, skipping the "
        "API restart"
    )
