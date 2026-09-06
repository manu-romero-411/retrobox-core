#!/usr/bin/env bash
# setup/bios-fetch.sh
#
# Descarga BIOS/firmware para Batocera directamente desde el repositorio
# RetroBIOS (https://github.com/Abdess/retrobios), archivo por archivo,
# sin clonar el repo completo.
#
# Se apoya en dos manifiestos oficiales de ese proyecto (se cachean
# localmente y se refrescan cada cierto tiempo):
#   - platforms/batocera.yml   -> qué ficheros necesita cada sistema
#                                 Batocera (nombre de carpeta = native_id,
#                                 el mismo que usamos en resources/systems_config)
#                                 y su destino relativo a bios/.
#   - install/batocera.json    -> ruta real de cada fichero dentro del
#                                 repo RetroBIOS + hash sha1, para poder
#                                 construir la URL de descarga individual
#                                 y verificar la integridad.
#
# La lógica de resolución/descarga vive en bios_fetch.py (igual que
# bios-check delega en bios_check.py); este fichero es solo el punto de
# entrada, para mantener el mismo estilo que el resto de setup/*.sh.
#
# Uso (normalmente invocado vía `retrobox.sh --bios-fetch [opciones] [sistema...]`):
#   bios_fetch --list                # lista los sistemas disponibles
#   bios_fetch psx gba               # descarga BIOS de PSX y GBA
#   bios_fetch --dry-run dreamcast   # muestra qué haría, sin descargar
#   bios_fetch --all                 # descarga todo (~1.2 GB, todos los sistemas)
#   bios_fetch --refresh psx         # fuerza refresco del manifiesto antes de resolver

BIOS_FETCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

function bios_fetch() {
    local python_bin
    python_bin="$(command -v python3 || true)"

    if [[ -z "${python_bin}" ]]; then
        if declare -F log_warn >/dev/null; then
            log_warn "python3 no está disponible; no se puede ejecutar bios-fetch."
        else
            echo "ERROR: python3 no está disponible; no se puede ejecutar bios-fetch." >&2
        fi
        return 2
    fi

    "${python_bin}" "${BIOS_FETCH_DIR}/bios_fetch.py" "$@"
}