#!/usr/bin/env bash
# setup/bios-check.sh
#
# Comprueba que las BIOS/firmware necesarias para los cores de RetroArch
# instalados están presentes en bios/<sistema-batocera>/.
#
# La lógica de parseo (YAML de systems_config + .info de los cores) vive en
# bios_check.py, ya que en bash sería frágil/ilegible. Este fichero es solo
# el punto de entrada, para mantener el mismo estilo que el resto de
# setup/*.sh.
#
# Uso (normalmente invocado vía `retrobox.sh --bios-check [sistema...]`):
#   bios_check                # comprueba todos los sistemas
#   bios_check megadrive snes # comprueba solo esos sistemas

BIOS_CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

function bios_check() {
    local python_bin
    python_bin="$(command -v python3 || true)"

    if [[ -z "${python_bin}" ]]; then
        if declare -F log_warn >/dev/null; then
            log_warn "python3 no está disponible; no se puede ejecutar bios-check."
        else
            echo "ERROR: python3 no está disponible; no se puede ejecutar bios-check." >&2
        fi
        return 2
    fi

    "${python_bin}" "${BIOS_CHECK_DIR}/bios_check.py" "$@"
}
