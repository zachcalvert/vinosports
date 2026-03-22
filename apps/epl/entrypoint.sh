#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
while ! python -c "
import os
import socket
from urllib.parse import urlparse

database_url = os.environ.get('DATABASE_URL', '')
parsed = urlparse(database_url)
host = parsed.hostname or 'db'
port = parsed.port or 5432

s = socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(5)
    s.connect((host, port))
    s.close()
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

# Only run collectstatic for the web (Daphne) process.
case "$1" in
    daphne)
        echo "Collecting static files..."
        python manage.py collectstatic --noinput
        ;;
esac

exec "$@"
