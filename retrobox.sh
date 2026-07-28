#!/usr/bin/env bash
# --- Raíz del proyecto: NO depende del .env (el .env aún no está cargado) ---
RETROBOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Carga centralizada del .env, exportado a TODO el árbol de procesos hijos ---
if [ -f "${RETROBOX_ROOT}/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${RETROBOX_ROOT}/.env"
    set +a
fi

export PROJECT_PATH="${PROJECT_PATH:-$RETROBOX_ROOT}"
export USERDATA="${USERDATA:-$PROJECT_PATH}"

# --- Visibilidad de retrobox_paths.py para TODOS los módulos python hijos ---
export PYTHONPATH="${PROJECT_PATH}/resources${PYTHONPATH:+:${PYTHONPATH}}"

#cd "${USERDATA}/frontend" || exit 1
#"${USERDATA}/frontend/emulationstation" --home "${USERDATA}/frontend" "$@"
