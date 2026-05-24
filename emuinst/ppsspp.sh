#!/usr/bin/env bash
## INSTALADOR DE PPSSPP
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## Adaptado para soportar AppImage (multi-arquitectura) y Flatpak
set -eo pipefail

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

FLATPAK_ID="org.ppsspp.PPSSPP"
GITHUB_REPO="hrydgard/ppsspp" # Repositorio oficial (o cámbialo al fork de AppImages que uses)
INSTALL_DIR="/opt/ppsspp"
BIN_LINK="/usr/local/bin/ppsspp"
DESKTOP_FILE="/usr/local/share/applications/ppsspp-appimage.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/ppsspp.svg"
TMP_DIR="$(mktemp -d)"

## FUNCIONES

function error() {
    echo "[ERROR] $@. F"
    exit 1
}

function check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "[MALAMENTE] No eres root. Se necesitan permisos de administrador."
    fi
}

function install_flatpak() {
    echo "[INFO] Instalando PPSSPP vía Flatpak..."
    if ! dpkg --get-selections | grep -q "^flatpak[[:space:]]"; then
        if [[ -f "$ROOTDIR/flatpak.sh" ]]; then
            $ROOTDIR/flatpak.sh
        else
            echo "[WARNING] No se encontró $ROOTDIR/flatpak.sh. Asegúrate de que Flatpak esté instalado."
        fi
    fi
    flatpak install -y flathub $FLATPAK_ID
    echo "[INFO] Instalación de Flatpak completada."
}

function svg_icon(){
    echo "[INFO] Generando icono SVG..."
    mkdir -p "$(dirname "$ICON_PATH")"
    cat << 'EOF' > "$ICON_PATH"
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   version="1.1"
   viewBox="0 0 512 512"
   id="svg13"
   width="512"
   height="512"
   xmlns:xlink="http://www.w3.org/1999/xlink"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:cc="http://creativecommons.org/ns#"
   xmlns:dc="http://purl.org/dc/elements/1.1/">
  <defs
     id="defs5">
    <linearGradient
       id="cvfh"
       x1="458"
       x2="442"
       y1="-51.700001"
       y2="-202"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfa" />
    <linearGradient
       id="cvfa">
      <stop
         style="stop-color:#5ca2b8"
         offset="0"
         id="stop1" />
      <stop
         style="stop-color:#aedce8"
         offset="1"
         id="stop2" />
    </linearGradient>
    <linearGradient
       id="cvff"
       x1="396"
       x2="379"
       y1="-225"
       y2="-368"
       gradientTransform="translate(-3.63,-1.82)"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfa" />
    <linearGradient
       id="cvfe"
       x1="450"
       x2="433"
       y1="-143"
       y2="-242"
       gradientTransform="translate(-3.63,-1.82)"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfa" />
    <linearGradient
       id="cvfd"
       x1="490"
       x2="442"
       y1="-113"
       y2="-202"
       gradientTransform="translate(-3.63,-1.82)"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfa" />
    <linearGradient
       id="cvfg"
       x1="447"
       x2="425"
       y1="-140"
       y2="-268"
       gradientTransform="translate(-3.63,-1.82)"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfa" />
    <linearGradient
       id="cvfi"
       x1="20.1"
       x2="462"
       y1="-202"
       y2="-202"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfc" />
    <linearGradient
       id="cvfc">
      <stop
         style="stop-color:#5587a3"
         offset="0"
         id="stop3" />
      <stop
         style="stop-color:#457d8f"
         offset="1"
         id="stop4" />
    </linearGradient>
    <filter
       id="cvfj"
       x="-0.027155465"
       y="-0.027291335"
       width="1.0543109"
       height="1.0636798"
       color-interpolation-filters="sRGB">
      <feGaussianBlur
         in="SourceAlpha"
         result="blur"
         stdDeviation="5"
         id="feGaussianBlur4" />
      <feColorMatrix
         result="bluralpha"
         values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.3 0 "
         id="feColorMatrix4" />
      <feOffset
         dx="0"
         dy="4"
         in="bluralpha"
         result="offsetBlur"
         id="feOffset4" />
      <feMerge
         id="feMerge5">
        <feMergeNode
           in="offsetBlur"
           id="feMergeNode4" />
        <feMergeNode
           in="SourceGraphic"
           id="feMergeNode5" />
      </feMerge>
    </filter>
    <linearGradient
       id="cvfb"
       x1="20.1"
       x2="32.599998"
       y1="-202"
       y2="-124"
       gradientUnits="userSpaceOnUse"
       xlink:href="#cvfc" />
    <linearGradient
       xlink:href="#cvfc"
       id="linearGradient2"
       gradientUnits="userSpaceOnUse"
       x1="20.1"
       y1="-202"
       x2="32.599998"
       y2="-124" />
    <linearGradient
       xlink:href="#cvfc"
       id="linearGradient3"
       gradientUnits="userSpaceOnUse"
       x1="20.1"
       y1="-202"
       x2="32.599998"
       y2="-124" />
    <linearGradient
       xlink:href="#cvfc"
       id="linearGradient4"
       gradientUnits="userSpaceOnUse"
       x1="20.1"
       y1="-202"
       x2="32.599998"
       y2="-124" />
  </defs>
  <title
     id="title5">ppsspp</title>
  <metadata
     id="metadata5">
    <rdf:RDF>
      <cc:Work
         rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type
           rdf:resource="http://purl.org/dc/dcmitype/StillImage" />
        <dc:title>ppsspp</dc:title>
      </cc:Work>
    </rdf:RDF>
  </metadata>
  <g
     transform="translate(-0.15000026,-542.6)"
     id="g13">
    <g
       id="g1"
       transform="matrix(0.99904401,0,0,0.99519892,1.4433188e-4,2.6050661)">
      <g
         transform="matrix(1.1,0,0,1.1,-8.76,1020)"
         style="fill:url(#cvfi);filter:url(#cvfj)"
         id="g8">
        <path
           d="m 267,-422 26.6,117 -56.6,91 -90.2,-57.5 -26.6,-117 z"
           style="fill:url(#linearGradient2)"
           id="path5" />
        <path
           d="m 20.1,-230 117,-26.6 91,56.6 -57.5,90.2 -117,26.6 z"
           style="fill:url(#linearGradient3)"
           id="path6" />
        <path
           d="m 213,17.7 -26.6,-117 56.6,-91 90.2,57.5 26.6,117 z"
           style="fill:url(#linearGradient4)"
           id="path7" />
        <path
           d="m 462,-175 -117,26.6 -91,-56.6 57.5,-90.2 117,-26.6 z"
           style="fill:url(#cvfb)"
           id="path8" />
      </g>
      <g
         transform="matrix(1.1,0,0,1.1,-4.76,1022)"
         style="fill:url(#cvfh)"
         id="g12">
        <path
           d="m 252,-404 20.4,89.4 -45.3,70.6 -71.2,-44.1 -20.4,-89.4 z"
           style="fill:url(#cvff)"
           id="path9" />
        <path
           d="m 36,-220 89.4,-20.4 70.6,45.3 -44.1,71.2 -89.4,20.4 z"
           style="fill:url(#cvfe)"
           id="path10" />
        <path
           d="m 221,-3.63 -20.4,-89.4 45.3,-70.6 71.2,44.1 20.4,89.4 z"
           style="fill:url(#cvfd)"
           id="path11" />
        <path
           d="m 439,-188 -89.4,20.4 -70.6,-45.3 44.1,-71.2 89.4,-20.4 z"
           style="fill:url(#cvfg)"
           id="path12" />
      </g>
    </g>
  </g>
</svg>
EOF
    chmod 644 "$ICON_PATH"
}

function appimage_desktop_file(){
    echo "[INFO] Creando acceso directo (.desktop)..."
    cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Categories=Game;Emulator;
Comment=ppsspp (fast and portable PSP emulator)\s
Exec=$INSTALL_DIR/ppsspp.AppImage %U
Icon=$ICON_PATH
Keywords=Sony;PlayStation;Portable;PSP;handheld;console;
MimeType=application/x-cd-image;application/x-iso9660-image;application/x-compressed-iso;application/zip;
Name=PPSSPP
NoDisplay=false
Path=
PrefersNonDefaultGPU=false
StartupNotify=true
Terminal=false
TerminalOptions=
Type=Application
X-Desktop-File-Install-Version=0.28
X-Flatpak=org.ppsspp.PPSSPP
X-Flatpak-RenamedFrom=PPSSPPSDL.desktop;
X-KDE-SubstituteUID=false
X-KDE-Username=
EOF
    chmod 644 "$DESKTOP_FILE"
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
    if ! command -v curl &> /dev/null; then
        echo "[INFO] Instalando dependencias (curl)..."
        apt-get update && apt-get install -y curl || dnf install -y curl
    fi

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
    ln -sf "$INSTALL_DIR/ppsspp.AppImage" "$BIN_LINK"

    # 7. Configurar icono y desktop
    svg_icon
    appimage_desktop_file

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

check_root

if [[ -z "$1" ]]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -f : Instalar usando Flatpak"
    echo "  -i : Instalar usando AppImage (detecta automáticamente x86_64 o aarch64)"
    echo "  -u : Desinstalar (elimina Flatpak y/o AppImage según lo que encuentre)"
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
