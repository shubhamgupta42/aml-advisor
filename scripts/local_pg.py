"""Start a self-contained local Postgres (pgserver) with pgvector — no Docker needed.

pgserver bundles Postgres binaries + the pgvector extension inside a pip wheel.
The daemon keeps running after this script exits; re-running is idempotent.

Usage:
    python scripts/local_pg.py          # starts (or reuses) the server, applies
                                        # scripts/init_db.sql, prints the DSN
Then:
    export PG_DSN="$(python scripts/local_pg.py)"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    import pgserver
    import psycopg

    pgdata = ROOT / "pgdata"
    # cleanup_mode=None: leave the daemon running after this script exits, so
    # the ingest/demo processes (and the user's own shells) can connect to it.
    srv = pgserver.get_server(str(pgdata), cleanup_mode=None)
    uri = srv.get_uri()

    sql = (ROOT / "scripts" / "init_db.sql").read_text()
    with psycopg.connect(uri) as conn:
        conn.execute(sql)
        conn.commit()

    print(uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
