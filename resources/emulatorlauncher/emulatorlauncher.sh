#!/usr/bin/env bash
unset LD_PRELOAD
CONFIGGEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
RETROBOX_ROOT=$(realpath "${CONFIGGEN_DIR}"/../..)
FRONTEND_DIR=$(realpath "${RETROBOX_ROOT}"/frontend)

#PYTHON="$CONFIGGEN_DIR/.venv/bin/python"
PYTHON=$(which python3)
# Fuerza a las AppImages a extraerse y ejecutarse sin requerir FUSE dentro del contenedor
export APPIMAGE_EXTRACT_AND_RUN=1
cd "${FRONTEND_DIR}" || exit

# --- Absolutizar el argumento -rom donde quiera que aparezca ---
args=("$@")
for i in "${!args[@]}"; do
    if [[ "${args[$i]}" == "-rom" ]]; then
        next=$((i + 1))
        if [[ -n "${args[$next]+set}" ]]; then
            rom_path="${args[$next]}"
            # Solo absolutizar si no es ya una ruta absoluta
            if [[ "$rom_path" != /* ]]; then
                args[$next]="$(realpath -m -- "$rom_path")"
            fi
        fi
        break
    fi
done
# ---------------------------------------------------------------

#"$PYTHON" -m configgen.sync_settings
mkdir -p /tmp/batocera-run/{squashfs,evmapy,overlays,mame_software,mame_artwork,cmdfiles,shader_bezels,batocera-overlays}

cd "${CONFIGGEN_DIR}" || exit
exec "$PYTHON" -m configgen.emulatorlauncher "${args[@]}"
#exec "$PYTHON" -m configgen.emulatorlauncher "${args[@]}" 2>&1 | grep -i 'bezel\|decoration\|overlay'