# secret/

Hidden competition parameters. **Do not share, do not deploy.**

- `config.example.py` — committed template showing the shape.
- `config.py` — the real values. **Git-ignored** (see repo `.gitignore`). Create it
  by copying the example and filling in real numbers. Keep a backup somewhere safe
  (it is not version-controlled).

Even though the GitHub repo is private, every push to `main` hard-resets
`/var/www/html` on the public VM. Keeping `config.py` out of git is what stops the
hidden bounds from ever landing in the web root. Before Phase 2, also confirm the
web server does not serve `harness/` or `secret/` (`docs/BUILD_CHECKLIST.md` §0.1).
