from __future__ import annotations

import glob
import locale
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from configgen.utils.language import _detect_language

from ... import Command
from ...exceptions import BatoceraException
from ...controller import generate_sdl_game_controller_config
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

# Constantes de temporización
POLL_INTERVAL   = 3    # segundos entre comprobaciones
LAUNCH_TIMEOUT  = 90   # máximo esperando a que aparezca el .exe
MAX_TOTAL       = 7200 # timeout global de seguridad (2 h)

# Procesos Ubisoft a purgar al salir
UBISOFT_PROCS = [
    "UbisoftConnect.exe",
    "UbisoftGameLauncher.exe",
    "upc.exe",
    "UplayWebCore.exe",
]

# Binarios "wrapper" que NUNCA deben considerarse como el proceso del juego,
# aunque el nombre del .exe del juego aparezca en su línea de comandos
# (p.ej. Ubisoft Connect lanza el juego a través de su steam.exe emulado,
# que se queda zombi tras cerrar el juego real y rompía la detección).
WRAPPER_BASENAMES = [
    "steam.exe",
]


# ─
# Helpers Python
# ─

def _get_lutris_info(game_id: str) -> tuple[str, str]:
    """
    Ejecuta 'lutris -l' y extrae (slug, nombre) para el game_id numérico.
    Formato de línea: ID | slug | Nombre del juego | …
                      0     1      2
    """
    try:
        output = subprocess.check_output(
            ["lutris", "-l"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise BatoceraException(f"No se pudo ejecutar 'lutris -l': {e}")

    for line in output.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[0] == game_id:
            return parts[2], parts[1]  # (slug, nombre)

    raise BatoceraException(
        f"No se encontró ningún juego con ID {game_id} en 'lutris -l'"
    )


def _parse_lutris_yml(slug: str) -> tuple[str, str]:
    """
    Localiza el YML más reciente para el slug dado y extrae (exe_name, wine_prefix).
    Devuelve (exe_basename, prefix_path).
    """
    conf_dir = Path.home() / ".local/share/lutris/games"
    candidates = sorted(
        conf_dir.glob(f"{slug}*.yml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise BatoceraException(
            f"No se encontró archivo .yml para el slug '{slug}' en {conf_dir}"
        )

    yml_path = candidates[0]
    exe_path = ""
    wine_prefix = ""

    with yml_path.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("  exe: ") and not exe_path:
                exe_path = line.removeprefix("  exe: ").strip()
            if line.startswith("  prefix: ") and not wine_prefix:
                wine_prefix = line.removeprefix("  prefix: ").strip()

    if not exe_path:
        raise BatoceraException(
            f"No se encontró 'exe:' en {yml_path}"
        )

    exe_name = Path(exe_path).name  # p.ej. "RaymanLegends.exe"
    return exe_name, wine_prefix


# ─
# Generador del wrapper bash
# ─

def _make_wrapper(lutris_link: str, exe_name: str, wine_prefix: str) -> str:
    """
    Genera un script bash temporal que:
      1. Lanza el juego vía lutris <link> (fire & forget)
      2. Espera hasta LAUNCH_TIMEOUT a que aparezca el .exe del juego
      3. Vigila el .exe hasta que termine
      4. Purga procesos de Ubisoft Connect y el wineserver del prefijo

    Detección del proceso del juego
    --
    Se exige que ARGV[0] (el comando realmente ejecutado, NO un
    argumento posterior) sea una ruta tipo "<letra>:\...\$EXE_NAME".

    Esto es necesario porque, en juegos de Ubisoft Connect lanzados con
    Proton/umu, Ubisoft lanza el juego a través de un "steam.exe" emulado
    propio, pasándole la ruta del .exe del juego como ARGUMENTO:

        argv[0] = c:\windows\system32\steam.exe
        argv[1] = ...\Rayman Origins\Rayman Origins.exe

    Ese steam.exe se queda zombi tras cerrar el juego real. Si se busca
    el nombre del .exe en toda la línea de comandos (como hacía la
    versión anterior con `pgrep -f`), este zombi sigue matcheando
    indefinidamente y el script nunca detecta que el juego ha terminado.

    Para evitarlo se lee directamente /proc/PID/cmdline, que separa los
    argumentos con bytes NUL reales (no con espacios), y se compara
    SOLO argv[0] contra el nombre del .exe. Esto es imprescindible
    porque tanto las rutas del juego como los nombres de carpetas de
    Windows suelen contener espacios sin escapar (p.ej. "Rayman
    Origins.exe", "Ubisoft Game Launcher"), lo que haría que cortar por
    espacios (`cmd="${{line%% *}}"`) parta el argv[0] real a la mitad y
    rompa la detección incluso en el caso normal. No se asume ninguna
    letra de unidad concreta (Z:, C:, D:...), ya que varía según dónde
    esté instalado cada juego dentro de su wineprefix.

    Nota sobre la condición de carrera con /proc
    --
    El glob `/proc/[0-9]*/cmdline` lo expande bash una sola vez al
    construir la lista del `for`, capturando los PIDs vivos en ESE
    instante. Muchos de esos procesos (helpers de pressure-vessel,
    hijos efímeros de bwrap/Steam Runtime, etc.) pueden morir entre esa
    expansión y la lectura de cada `cmdline`, lo que hace que la
    redirección `< "$proc"` falle con "No existe el fichero o el
    directorio". Ese error lo emite el propio bash al intentar abrir el
    fichero para la redirección, ANTES de invocar `tr` — por eso el
    `2>/dev/null` puesto sobre el comando `tr` no lo silencia (ese
    `2>/dev/null` solo cubre errores del propio `tr`, no errores de
    apertura de la redirección por parte del shell). Para evitarlo se
    comprueba `[ -r "$proc" ]` antes de leer, y se mantiene un
    `2>/dev/null` adicional alrededor de la redirección como red de
    seguridad por si el proceso muere justo entre el check y la
    lectura (la ventana de carrera nunca se puede cerrar del todo).
    """
    purge_lines = "\n".join(
        f'pkill -f "{proc}" 2>/dev/null || true' for proc in UBISOFT_PROCS
    )

    wineserver_kill = (
        f'WINEPREFIX="{wine_prefix}" wineserver -k 2>/dev/null || true'
        if wine_prefix
        else "# (sin prefijo Wine detectado)"
    )

    wrapper_excl = "|".join(re.escape(name) for name in WRAPPER_BASENAMES)

    script = f"""\
#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT

EXE_NAME="{exe_name}"
WRAPPER_EXCL_RE="({wrapper_excl})$"
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
START=$(date +%s)

_elapsed() {{ echo $(( $(date +%s) - START )); }}
_timeout()  {{ [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; }}

# Comprueba si el .exe del juego está corriendo como ARGV[0] (el
# comando realmente ejecutado), no como argumento de otro proceso.
# Esto evita falsos positivos con wrappers tipo "steam.exe <ruta al
# juego>" que Ubisoft Connect deja zombis tras cerrar el juego real.
#
# Se lee /proc/PID/cmdline en vez de `ps -eo args=` porque cmdline
# separa los argumentos con bytes NUL reales: así se extrae argv[0]
# de forma fiable aunque la ruta contenga espacios sin escapar
# (p.ej. "Rayman Origins.exe"), cosa que cortar por espacios no
# garantiza.
#
# El check "[ -r "$proc" ]" evita el ruido en el log por procesos
# efímeros que mueren entre la expansión del glob y la lectura (ver
# nota en _make_wrapper). El "2>/dev/null" extra en la redirección es
# una red de seguridad para la ventana de carrera residual.
_game_running() {{
    local proc cmd base
    for proc in /proc/[0-9]*/cmdline; do
        [ -r "$proc" ] || continue
        cmd=$( {{ tr '\\0' '\\n' < "$proc" 2>/dev/null || true; }} 2>/dev/null | head -n1)
        [ -z "$cmd" ] && continue
        base="${{cmd##*[\\\\/]}}"             # basename, soporta \\ y /
        if [[ "$base" =~ $WRAPPER_EXCL_RE ]]; then
            continue                          # ignorar wrappers conocidos (steam.exe, etc.)
        fi
        if [[ "$cmd" =~ ^[A-Za-z]:.*"$EXE_NAME"$ ]]; then
            return 0
        fi
    done
    return 1
}}

# 1. Lanzar el juego via Lutris (fire & forget)
echo "[lutris-wrapper] Lanzando: lutris {lutris_link}"
lutris "{lutris_link}" > /dev/null 2>&1 &

# 2. Esperar a que aparezca el .exe del juego
echo "[lutris-wrapper] Esperando a que '$EXE_NAME' arranque..."
APPEARED=0
DEADLINE=$(( START + LAUNCH_TIMEOUT ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if _game_running; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[lutris-wrapper] Timeout: '$EXE_NAME' no detectado tras ${{LAUNCH_TIMEOUT}}s."
    exit 1
fi

echo "[lutris-wrapper] '$EXE_NAME' detectado. Monitorizando..."

# 3. Vigilar hasta que el juego cierre
while true; do
    _timeout && echo "[lutris-wrapper] Timeout global alcanzado, saliendo." && exit 0

    if ! _game_running; then
        # Confirmación anti-falso-positivo (reinicios del .exe por el propio juego)
        sleep 5
        if ! _game_running; then
            echo "[lutris-wrapper] '$EXE_NAME' ha terminado."
            break
        fi
        echo "[lutris-wrapper] Falsa alarma, '$EXE_NAME' sigue corriendo."
    fi

    sleep "$POLL"
done

# 4. Purga de procesos Ubisoft Connect
echo "[lutris-wrapper] Purgando procesos de Ubisoft Connect..."
{purge_lines}

echo "[lutris-wrapper] Matando wineserver del prefijo..."
{wineserver_kill}

echo "[lutris-wrapper] Limpieza completada."
exit 0
"""

    fd, path = tempfile.mkstemp(prefix="lutris_wrapper_", suffix=".sh")
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path


# ─
# Generador
# ─

class LutrisGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "wine",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # Limpiar wrappers anteriores huérfanos
        for old in glob.glob("/tmp/lutris_wrapper_*.sh"):
            try:
                os.remove(old)
            except OSError:
                pass

        # Leer el enlace del .rom
        try:
            with open(rom, "r", encoding="utf-8") as f:
                lutris_link = f.read().strip()
        except OSError as e:
            raise BatoceraException(f"No se pudo leer el archivo .rom: {e}")

        if not lutris_link.startswith("lutris:rungameid/"):
            raise BatoceraException(
                f"Formato de enlace no reconocido: '{lutris_link}'"
            )

        game_id = lutris_link.removeprefix("lutris:rungameid/")

        # Resolver ID → (slug, nombre) → YML → exe + prefix
        slug, game_name       = _get_lutris_info(game_id)
        exe_name, wine_prefix = _parse_lutris_yml(slug)

        # Generar wrapper
        wrapper_path = _make_wrapper(lutris_link, exe_name, wine_prefix)

        # Entorno
        lang = _detect_language()
        environment: dict[str, str] = {
            "LANG":   f"{lang}.UTF-8",
            "LC_ALL": f"{lang}.UTF-8",
        }

        if system.config.get_bool("sdl_config", True):
            environment.update({
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0",
            })

        return Command.Command(array=[wrapper_path], env=environment)

    def getMouseMode(self, config, rom):
        return config.get_bool("force_mouse")