#!/usr/bin/env bash
# Rebuild web/css/app.css from web/src/input.css.
#
# Tailwind ships a standalone binary, so this needs no node, no npm and no
# node_modules — which matters because the VM has none of those and serves
# web/css/app.css straight out of the repo. Run this after editing input.css or
# after adding classes to index.html / web/js, then commit the built CSS.
#
#   ./scripts/build_css.sh          one-off build
#   ./scripts/build_css.sh --watch  rebuild on change while developing
set -euo pipefail

VERSION="v4.3.3"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/quantguild"
BIN="$CACHE/tailwindcss-$VERSION"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "$BIN" ]]; then
    echo "  fetching the tailwind $VERSION standalone binary (once, ~110 MB)"
    mkdir -p "$CACHE"
    case "$(uname -m)" in
        x86_64)         ASSET="tailwindcss-linux-x64" ;;
        aarch64|arm64)  ASSET="tailwindcss-linux-arm64" ;;
        *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
    esac
    curl -fsSL -o "$BIN" \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"
    chmod +x "$BIN"
fi

if [[ "${1:-}" == "--watch" ]]; then
    exec "$BIN" -i "$ROOT/web/src/input.css" -o "$ROOT/web/css/app.css" --watch
fi

"$BIN" -i "$ROOT/web/src/input.css" -o "$ROOT/web/css/app.css" --minify
echo "  built web/css/app.css ($(du -h "$ROOT/web/css/app.css" | cut -f1))"
