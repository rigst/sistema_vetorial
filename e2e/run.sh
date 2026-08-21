#!/usr/bin/env bash
# Sobe uma instância descartável do app (banco SQLite, mídia e broker próprios),
# roda a suíte Playwright contra ela e derruba tudo ao final.
set -euo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$E2E_DIR")"
TMP_DIR="$E2E_DIR/.tmp"
PORT="${E2E_PORT:-8099}"

PYTHON="${VETORIAL_PYTHON:-}"
if [ -z "$PYTHON" ]; then
    for candidate in "$BASE_DIR/../venv/bin/python" "$BASE_DIR/.venv/bin/python" "$(command -v python3 || true)"; do
        if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
    done
fi
[ -x "$PYTHON" ] || { echo "Python do projeto não encontrado; defina VETORIAL_PYTHON." >&2; exit 1; }

rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR/media" "$TMP_DIR/static"

# Ambiente isolado: nada aqui toca o banco, a mídia ou a fila de produção.
export DJANGO_SETTINGS_MODULE=config.settings
export DJANGO_DEBUG=1
export DJANGO_SECRET_KEY="e2e-only-key-nao-usar-em-producao-0123456789"
export DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost,testserver"
export DB_ENGINE=django.db.backends.sqlite3
export DB_NAME="$TMP_DIR/db.sqlite3"
export DJANGO_MEDIA_ROOT="$TMP_DIR/media"
export DJANGO_STATIC_ROOT="$TMP_DIR/static"
export CELERY_TASK_ALWAYS_EAGER=0
# Índice 9 do Redis local: fila separada da de produção (índice 0).
export CELERY_BROKER_URL="${E2E_CELERY_BROKER_URL:-redis://127.0.0.1:6379/9}"
export CELERY_RESULT_BACKEND="$CELERY_BROKER_URL"
export E2E_BASE_URL="http://127.0.0.1:$PORT"

cd "$BASE_DIR"
"$PYTHON" manage.py migrate --noinput >"$TMP_DIR/migrate.log" 2>&1
"$PYTHON" e2e/seed.py >"$TMP_DIR/seed.log" 2>&1

pids=()
cleanup() {
    for pid in "${pids[@]:-}"; do
        [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$PYTHON" -m celery -A config worker -l warning --concurrency 1 \
    >"$TMP_DIR/celery.log" 2>&1 &
pids+=($!)

"$PYTHON" manage.py runserver "127.0.0.1:$PORT" --noreload \
    >"$TMP_DIR/runserver.log" 2>&1 &
pids+=($!)

for _ in $(seq 1 60); do
    if curl -sf -o /dev/null "http://127.0.0.1:$PORT/login/"; then break; fi
    sleep 0.5
done
curl -sf -o /dev/null "http://127.0.0.1:$PORT/login/" || {
    echo "O servidor não subiu. Log:" >&2
    cat "$TMP_DIR/runserver.log" >&2
    exit 1
}

cd "$E2E_DIR"
npx playwright test "$@"
