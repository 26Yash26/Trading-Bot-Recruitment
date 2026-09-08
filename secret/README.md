# secret/

**Superseded, kept for offline use.**

The hidden competition config — the four `(min, max)` distribution bounds, the
starting capitals to sweep, and the master seed — now lives in the SQLite
settings table in `QG_DATA_DIR` (`/var/lib/quantguild` on the VM), and is edited
from the admin console under **Sandbox & secrets**.

That is a deliberate move *out* of this repo. `/var/www/html` is a checkout of
the whole repo and nginx's document root points at it, so a file here is one
nginx misconfiguration away from being public. The database is outside the web
root and never served, and `store.public_settings()` filters `block_bounds` and
`seed` out of every public API response.

`config.example.py` remains as a template for running the harness offline —
for example a local rehearsal of the final evaluation without the web service.
If you do create a `config.py` here it stays git-ignored.
