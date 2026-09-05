#!/usr/bin/env bash
# setup/bios-check.sh
#
# Verifies that the BIOS/firmware required by Batocera are present under
# bios/<system>/. The actual logic lives in bios_manager.py, shared with
# bios-fetch.sh (both are thin entry points over the same module, to keep
# the same style as the rest of setup/*.sh).
#
# Usage (normally invoked via `retrobox.sh --bios-check [system...]`):
#   bios_check                # check every system
#   bios_check megadrive ps2  # check only those systems

BIOS_CHECK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

function bios_check() {
    local python_bin
    python_bin="$(command -v python3 || true)"

    if [[ -z "${python_bin}" ]]; then
        if declare -F log_warn >/dev/null; then
            log_warn "python3 is not available; cannot run bios-check."
        else
            echo "ERROR: python3 is not available; cannot run bios-check." >&2
        fi
        return 2
    fi

    "${python_bin}" "${BIOS_CHECK_DIR}/bios_check.py" "$@"
}
