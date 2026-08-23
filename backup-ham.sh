#!/usr/bin/env sh
set -eu

mkdir -p data/backups
timestamp="$(date +%Y%m%d-%H%M%S)"
docker compose exec -T ham python -c "import sqlite3; source=sqlite3.connect('/app/data/database/ham.db'); target=sqlite3.connect('/app/data/backups/ham-${timestamp}.db'); source.backup(target); target.close(); source.close()"
echo "Varnostna kopija: data/backups/ham-${timestamp}.db"

