#!/usr/bin/env bash
## INSTALADOR DE DOLPHIN
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHAS DE MODIFICACIÓN: Modificado para soportar AppImage, Flatpak y build desde source

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

GITHUB_REPO="pkgforge-dev/Dolphin-emu-AppImage"
APPIMAGE_DIR="${SCRIPT_DIR}/dolphin-emu"
BIN_LINK="/usr/local/bin/dolphin-emu"
DESKTOP_FILE="/usr/local/share/applications/dolphin-emu.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/dolphin-emu.svg"

# --- NUEVO: build desde source ---
SOURCE_UPSTREAM="https://github.com/dolphin-emu/dolphin.git"
SOURCE_DIR="${APPIMAGE_DIR}/source-build"
SOURCE_REPO_DIR="${SOURCE_DIR}/dolphin"
SOURCE_BUILD_DIR="${SOURCE_REPO_DIR}/Build"
# ruta del binario tras un build local (no se usa `make install`, queda relocalizable)
SOURCE_BIN="${SOURCE_BUILD_DIR}/Binaries/dolphin-emu"
# ----------------------------------

## FUNCIONES

function error(){
    echo "[ERROR] $*. F"
    exit 1
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Dolphin AppImage en GitHub..."

    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

    if [ -z "${DOWNLOAD_URL}" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: $DOWNLOAD_URL"
    mkdir -p "${APPIMAGE_DIR}"
    curl -L "${DOWNLOAD_URL}" -o "${APPIMAGE_DIR}/dolphin.AppImage"
    chmod +x "${APPIMAGE_DIR}/dolphin.AppImage"

    echo "[INFO] Extrayendo AppImage..."
    (
        cd "${APPIMAGE_DIR}" || exit 1
        ./dolphin.AppImage --appimage-extract >/dev/null 2>&1
        mv AppDir app
        rm ./dolphin.AppImage
    )
    echo "[INFO] Instalación completada."
}

# --- NUEVO: build desde source ---

function install_builddeps(){
    echo "[INFO] Instalando dependencias de compilación..."

    # dnf builddep instala exactamente lo que usa el paquete dolphin-emu de Fedora,
    # que se mantiene razonablemente al día con lo que el proyecto necesita.
    # Requiere que los repos -source estén habilitados (Fedora los trae activos por defecto en dnf5).
    if ! sudo dnf builddep -y dolphin-emu; then
        echo "[AVISO] dnf builddep falló o no encontró el paquete. Cayendo a lista manual del wiki oficial..."
        sudo dnf install -y \
            pkgconf-pkg-config mesa-libGL-devel libX11-devel libXrandr-devel libXi-devel \
            mesa-libEGL-devel libavcodec-free-devel libavformat-free-devel libavutil-free-devel \
            libswresample-free-devel libswscale-free-devel systemd-devel libevdev-devel \
            SDL3-devel fmt-devel glslang-devel pugixml-devel enet-devel xxhash-devel \
            bzip2-devel xz-devel libzstd-devel zlib-devel minizip-ng-devel lzo-devel lz4-devel \
            libspng-devel cubeb-devel libusb1-devel miniupnpc-devel libcurl-devel hidapi-devel \
            gcc-c++ cmake git ninja-build \
            || error "No se pudieron instalar las dependencias de compilación"
    fi
}

function install_source(){
    install_builddeps

    mkdir -p "${SOURCE_DIR}"

    if [ -d "${SOURCE_REPO_DIR}/.git" ]; then
        echo "[INFO] Ya existe un clon en ${SOURCE_REPO_DIR}, actualizando en vez de re-clonar..."
        rebuild_source
        return
    fi

    echo "[INFO] Clonando Dolphin (esto puede tardar, el repo es grande)..."
    git clone --recursive "${SOURCE_UPSTREAM}" "${SOURCE_REPO_DIR}" \
        || error "Fallo al clonar el repositorio"

    _configure_and_build_source

    _link_source_binary

    mkdir -p "${APPIMAGE_DIR}/config" "${APPIMAGE_DIR}/data"
    echo "[INFO] Build desde source completado. Binario en: ${SOURCE_BIN}"
}

function rebuild_source(){
    if [ ! -d "${SOURCE_REPO_DIR}/.git" ]; then
        error "No hay ningún clon en ${SOURCE_REPO_DIR}. Usa -s primero para el build inicial"
    fi

    echo "[INFO] Actualizando repositorio..."
    (
        cd "${SOURCE_REPO_DIR}" || exit 1
        git pull --rebase
        git submodule update --init --recursive
    ) || error "Fallo al actualizar el repositorio"

    _configure_and_build_source

    _link_source_binary

    echo "[INFO] Rebuild completado. Binario en: ${SOURCE_BIN}"
}

function _configure_and_build_source(){
    mkdir -p "${SOURCE_BUILD_DIR}"
    (
        cd "${SOURCE_BUILD_DIR}" || exit 1
        # USE_SYSTEM_* en OFF para SFML/mbedtls/libmgba: Fedora no trae las versiones
        # que Dolphin espera (SFML 3.0 aún no está en Fedora, mbedtls de Fedora es 3.x
        # y Dolphin usa 2.x), así que se vendorizan igual que hace el paquete oficial.
        cmake .. \
            -DCMAKE_BUILD_TYPE=Release \
            -DUSE_SYSTEM_SFML=OFF \
            -DUSE_SYSTEM_MBEDTLS=OFF \
            -DUSE_SYSTEM_LIBMGBA=OFF \
            || exit 1
        make -j"$(nproc)" || exit 1
    ) || error "Fallo al compilar Dolphin. Revisa la salida de cmake/make arriba"
}

function _link_source_binary(){
    if [ ! -f "${SOURCE_BIN}" ]; then
        error "El build terminó pero no encuentro el binario en ${SOURCE_BIN} — revisa la ruta de salida de CMake"
    fi
    ln -sf "${SOURCE_BIN}" "$BIN_LINK"
}
# ----------------------------------

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Dolphin..."
    local found=0

    # Comprobar y desinstalar AppImage
    if [ -f "$APPIMAGE_DIR/dolphin.AppImage" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -f "$BIN_LINK"
        rm -rf "${APPIMAGE_DIR}/app"
        rm -f "$DESKTOP_FILE"
        rm -f "${ICON_PATH}"
        found=1
    fi

    # --- NUEVO: limpiar build desde source ---
    if [ -d "${SOURCE_DIR}" ]; then
        echo "[INFO] Eliminando build desde source..."
        rm -rf "${SOURCE_DIR}"
        found=1
    fi
    # ------------------------------------------

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Dolphin (ni Flatpak, ni AppImage, ni build desde source)."
    else
        echo "[INFO] Desinstalación completada."
    fi
}

## LLAMADAS
if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -s | -r | -u]"
    echo "  -f : Instalar usando Flatpak"
    echo "  -i : Instalar usando AppImage (desde GitHub)"
    echo "  -s : Compilar e instalar desde source (build inicial, tarda)"
    echo "  -r : Actualizar y recompilar un build de source ya existente (rápido, incremental)"
    echo "  -u : Desinstalar (elimina Flatpak, AppImage y/o build de source según lo que encuentre)"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case $1 in
    "-i") install_appimage;;
    "-s") install_source;;
    "-r") rebuild_source;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0