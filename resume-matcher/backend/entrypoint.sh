#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for database to accept connections..."
python - <<'PY'
import os
import time

import psycopg

dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
for attempt in range(1, 61):
    try:
        with psycopg.connect(dsn, connect_timeout=3):
            print("[entrypoint] database is ready")
            break
    except Exception as exc:  # noqa: BLE001 - startup probe
        print(f"[entrypoint] database not ready ({attempt}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit("[entrypoint] database was not reachable in time")
PY

echo "[entrypoint] applying database migrations..."
alembic upgrade head

if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  echo "[entrypoint] seeding demo accounts and sample materials..."
  python -m app.seed
fi

echo "[entrypoint] starting api server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
