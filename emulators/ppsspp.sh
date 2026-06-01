#!/usr/bin/env bash
## INSTALADOR DE PPSSPP
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## Adaptado para soportar AppImage (multi-arquitectura) y Flatpak
set -eo pipefail

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

GITHUB_REPO="hrydgard/ppsspp" # Repositorio oficial (o cámbialo al fork de AppImages que uses)
INSTALL_DIR="${SCRIPT_DIR}/ppsspp"
TMP_DIR="$(mktemp -d)"

## FUNCIONES

function error() {
    echo "[ERROR] $*. F"
    exit 1
}

function install_appimage(){
    # 1. Detectar Arquitectura
    ARCH=$(uname -m)
    if [[ "$ARCH" == "x86_64" ]]; then
        SEARCH_ARCH="x86_64"
    elif [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        SEARCH_ARCH="aarch64"
    else
        error "Arquitectura no soportada para este script: $ARCH"
    fi

    echo "[INFO] Arquitectura detectada: $SEARCH_ARCH"
    echo "[INFO] Buscando la última versión de PPSSPP AppImage en GitHub..."

    # 2. Comprobar curl
    #if ! command -v curl &> /dev/null; then
    #    echo "[INFO] Instalando dependencias (curl)..."
    #    apt-get update && apt-get install -y curl || dnf install -y curl
    #fi

    # 3. Obtener JSON de la última release
    json=$(curl -sL "https://api.github.com/repos/$GITHUB_REPO/releases/latest")

    # 4. Extraer URL del AppImage compatible con la arquitectura
    APPIMAGE_URL=$(printf '%s\n' "$json" \
        | grep '"browser_download_url":' \
        | grep -i "\.AppImage" \
        | grep -i "$SEARCH_ARCH" \
        | head -n1 \
        | cut -d '"' -f4)

    if [[ -z "$APPIMAGE_URL" ]]; then
        rm -rf "$TMP_DIR"
        error "No se encontró ningún AppImage para $SEARCH_ARCH en la última release de $GITHUB_REPO."
    fi

    echo "[INFO] Descargando: $APPIMAGE_URL"

    # 5. Preparar directorio y descargar
    mkdir -p "$INSTALL_DIR"
    curl -L "$APPIMAGE_URL" -o "$TMP_DIR/ppsspp.AppImage"

    # 6. Mover e instalar
    mv "$TMP_DIR/ppsspp.AppImage" "$INSTALL_DIR/ppsspp.AppImage"
    chmod +x "$INSTALL_DIR/ppsspp.AppImage"
    mkdir -p "${INSTALL_DIR}/config"

    # 8. Limpiar
    rm -rf "$TMP_DIR"
    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app() {
    echo "[INFO] Buscando instalaciones de PPSSPP..."
    local found=0

    # Comprobar Flatpak
    if command -v flatpak >/dev/null 2>&1 && flatpak list | grep -q "$FLATPAK_ID"; then
        echo "[INFO] Desinstalando versión Flatpak..."
        flatpak uninstall -y $FLATPAK_ID
        flatpak uninstall -y --unused
        found=1
    fi

    # Comprobar AppImage
    if [[ -d "$INSTALL_DIR" || -f "$BIN_LINK" ]]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -rf "$INSTALL_DIR"
        rm -f "$BIN_LINK"
        rm -f "$DESKTOP_FILE"
        rm -f "$ICON_PATH"
        found=1
    fi

    if [[ $found -eq 0 ]]; then
        echo "[INFO] No se encontró ninguna instalación de PPSSPP."
    else
        echo "[INFO] Desinstalación completada de forma limpia."
    fi
}

## LLAMADAS


if [[ -z "$1" ]]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -i : Instalar usando AppImage"
    echo "  -u : Desinstalar"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case "$1" in
    "-f") install_flatpak;;
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0
