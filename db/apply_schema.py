"""
Idempotent schema loader for container startup: applies db/schema.sql only if the
'department' table doesn't already exist (so restarting the backend container against
an existing Postgres volume doesn't fail on 'relation already exists').
"""
import os
import sys
import time
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))

CONN_KWARGS = dict(
    host=os.environ.get("APTG_DB_HOST", "localhost"),
    port=os.environ.get("APTG_DB_PORT", "5432"),
    dbname=os.environ.get("APTG_DB_NAME", "aptg"),
    user=os.environ.get("APTG_DB_USER", "postgres"),
    password=os.environ.get("APTG_DB_PASSWORD", "postgres"),
)

# Wait for Postgres to accept connections (compose 'depends_on' only waits for the
# container to start, not for Postgres to finish initializing).
last_err = None
for attempt in range(30):
    try:
        conn = psycopg2.connect(**CONN_KWARGS)
        break
    except psycopg2.OperationalError as e:
        last_err = e
        print(f"Waiting for Postgres... ({attempt + 1}/30)")
        time.sleep(2)
else:
    print(f"Could not connect to Postgres: {last_err}", file=sys.stderr)
    sys.exit(1)

conn.autocommit = True
cur = conn.cursor()
cur.execute("select to_regclass('public.department')")
exists = cur.fetchone()[0] is not None

if exists:
    print("Schema already applied (department table exists) -- skipping.")
else:
    with open(os.path.join(HERE, "schema.sql")) as f:
        sql = f.read()
    cur.execute(sql)
    print("Schema applied.")

cur.close()
conn.close()
