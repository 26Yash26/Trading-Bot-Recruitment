#!/usr/bin/env bash
# Build both variants of the scoring document from docs/scoring.tex.
#
#     ./scripts/build_docs.sh
#
# Produces, in docs/:
#   scoring-public.pdf   variations 1 and 2, what /api/docs/scoring.pdf serves now
#   scoring.pdf          all four, served once variations 3 or 4 are released
#
# Both are committed: the VM has no TeX install, and the API serves them
# straight out of the checkout.
set -euo pipefail

cd "$(dirname "$0")/.."
DOCS=docs

command -v pdflatex >/dev/null || { echo "pdflatex not found" >&2; exit 1; }

build() {
    local jobname=$1 prefix=$2
    # Three passes: the table of contents needs two, and hyperref's bookmarks
    # settle on the third. -halt-on-error so a broken doc fails the script.
    for _ in 1 2 3; do
        pdflatex -interaction=nonstopmode -halt-on-error \
                 -output-directory "$DOCS" -jobname "$jobname" \
                 "${prefix}\\input{$DOCS/scoring.tex}" >/dev/null
    done
    echo "  built $DOCS/$jobname.pdf"
}

build scoring-public ""
build scoring "\\def\\RELEASED{1}"

rm -f "$DOCS"/scoring.aux "$DOCS"/scoring.log "$DOCS"/scoring.out "$DOCS"/scoring.toc
rm -f "$DOCS"/scoring-public.aux "$DOCS"/scoring-public.log \
      "$DOCS"/scoring-public.out "$DOCS"/scoring-public.toc

# The public build must not describe a variation that has not been released.
# Same phrases as tests/test_embargo.py; checked here too so a bad build never
# reaches a commit in the first place.
if command -v pdftotext >/dev/null; then
    text=$(pdftotext "$DOCS/scoring-public.pdf" - | tr '[:upper:]' '[:lower:]')
    for phrase in "runner-up penalty" "funded second price" "top_bids_last_round" \
                  "zero-sum" "0.5, 0.3 and 0.2"; do
        if grep -qF -- "$phrase" <<<"$text"; then
            echo "REFUSING: scoring-public.pdf leaks '$phrase'" >&2
            exit 1
        fi
    done
    echo "  scoring-public.pdf says nothing about the unreleased variations"
else
    echo "  WARNING: pdftotext not installed, embargo check skipped" >&2
fi
