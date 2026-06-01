#!/usr/bin/env bash
## INSTALADOR DE DOLPHIN
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHAS DE MODIFICACIÓN: Modificado para soportar AppImage y Flatpak

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

GITHUB_REPO="pkgforge-dev/Dolphin-emu-AppImage"
APPIMAGE_DIR="${SCRIPT_DIR}/dolphin-emu"
BIN_LINK="/usr/local/bin/dolphin-emu"
DESKTOP_FILE="/usr/local/share/applications/dolphin-emu.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/dolphin-emu.svg"

## FUNCIONES

function error(){
    echo "[ERROR] $*. F"
    exit 1
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Dolphin AppImage en GitHub..."

    # Obtener la URL de descarga del último release usando la API de GitHub
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep x86_64 | grep "browser_download_url.*\.AppImage" |  cut -d '"' -f 4 | head -n 1)

    if [ -z "${DOWNLOAD_URL}" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: $DOWNLOAD_URL"
    mkdir -p "${APPIMAGE_DIR}"
    curl -L "${DOWNLOAD_URL}" -o "${APPIMAGE_DIR}/dolphin.AppImage"

    if [ $? -ne 0 ]; then
        error "Error durante la descarga del AppImage"
    fi

    echo "[INFO] Configurando permisos y enlaces..."
    chmod +x "${APPIMAGE_DIR}/dolphin.AppImage"
    ln -sf "${APPIMAGE_DIR}/dolphin.AppImage" "$BIN_LINK"

    mkdir -p "${APPIMAGE_DIR}/config" "${APPIMAGE_DIR}/data"

    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Dolphin..."
    local found=0

    # Comprobar y desinstalar AppImage
    if [ -f "$APPIMAGE_DIR/dolphin.AppImage" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -f "$BIN_LINK"
        rm -rf "$APPIMAGE_DIR"
        rm -f "$DESKTOP_FILE"
        rm -f "${ICON_PATH}"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Dolphin (ni Flatpak ni AppImage)."
    else
        echo "[INFO] Desinstalación completada."
    fi
}

## LLAMADAS
if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -f : Instalar usando Flatpak"
    echo "  -i : Instalar usando AppImage (desde GitHub)"
    echo "  -u : Desinstalar (elimina Flatpak y/o AppImage según lo que encuentre)"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case $1 in
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0
