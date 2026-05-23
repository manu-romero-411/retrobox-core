import os
import subprocess

def launch_antimicrox(
    profile_path,
    guid=None,
    device_index=None,
    hidden=True,
    tray=True,
    use_uinput=True,
    wayland_fix=True,
    extra_args=None
):
    """
    Lanza antimicrox con un perfil.

    Args:
        profile_path (str): Ruta al perfil .amgp
        guid (str): GUID SDL del mando (recomendado)
        device_index (int): Índice del mando (fallback)
        hidden (bool): Ejecutar sin ventana
        tray (bool): Ejecutar en bandeja
        use_uinput (bool): Forzar uinput (mejor en Wayland)
        wayland_fix (bool): Fuerza QT_QPA_PLATFORM=xcb
        extra_args (list): Argumentos adicionales
    """

    #if not guid and device_index is None:
    #    raise ValueError("Debes especificar guid o device_index")

    if not guid:
        return None
    
    cmd = ["antimicrox"]

    if hidden:
        cmd.append("--hidden")

    if tray:
        cmd.append("--tray")

    if use_uinput:
        cmd.extend(["--eventgen", "uinput"])

    cmd.extend(["--profile", profile_path])

    if guid:
        cmd.extend(["--profile-controller", guid])
    else:
        cmd.extend(["--profile-controller", str(device_index)])

    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    env["SDL_GAMECONTROLLER_IGNORE_DEVICES"] = f"!{guid}"

    if wayland_fix:
        env["QT_QPA_PLATFORM"] = "xcb"

    print(cmd)
    return subprocess.Popen(cmd, env=env)


def stop_antimicrox(force=False):
    """
    Cierra todas las instancias de antimicrox.

    Args:
        force (bool): Si True, usa SIGKILL (-9). Si False, intenta cierre limpio.
    """

    sig = "-9" if force else "-15"  # SIGKILL o SIGTERM

    subprocess.run([
        "pkill",
        sig,
        "-f",
        "antimicrox"
    ])

def list_controllers():
    """
    Devuelve la salida de 'antimicrox --list'
    """
    result = subprocess.run(
        ["antimicrox", "--list"],
        capture_output=True,
        text=True
    )
    return result.stdout


def is_running():
    """
    Comprueba si antimicrox está corriendo
    """
    result = subprocess.run(
        ["pgrep", "-f", "antimicrox"],
        stdout=subprocess.DEVNULL
    )
    return result.returncode == 0