#!/usr/bin/env bash
## INSTALADOR DE CEMU
## FECHA DE CREACIÓN: 19 de mayo de 2026
## FECHAS DE MODIFICACIÓN: Creado con soporte para AppImage (x86_64) y Flatpak

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

FLATPAK_ID="info.cemu.Cemu"
GITHUB_REPO="cemu-project/Cemu"
APPIMAGE_DIR="/opt/cemu"
BIN_LINK="/usr/local/bin/cemu"
DESKTOP_FILE="/usr/local/share/applications/cemu.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/cemu.svg"

## FUNCIONES

function error(){
    echo "[ERROR] $@. F"
    exit 1
}

function check_root(){
    if [ $(id -u) -ne 0 ]; then
        echo "[ERROR] Se necesitan permisos de root."
        exit 1
    fi
}

function install_flatpak(){
    echo "[INFO] Instalando Cemu vía Flatpak..."
    if ! dpkg --get-selections | grep -q "^flatpak[[:space:]]"; then
        if [ -f "$ROOTDIR/flatpak.sh" ]; then
            $ROOTDIR/flatpak.sh
        else
            echo "[WARNING] No se encontró $ROOTDIR/flatpak.sh. Asegúrate de que Flatpak esté instalado."
        fi
    fi
    flatpak install -y flathub $FLATPAK_ID
    echo "[INFO] Instalación de Flatpak completada."
}

function svg_icon(){
    # Genera un logo en formato SVG inspirado en el diseño azul y geométrico de Cemu
    mkdir -p "$(dirname "$ICON_PATH")"
    cat << 'EOF' > "${ICON_PATH}"
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   viewBox="0 0 1024 1024"
   version="1.1"
   id="svg16"
   width="1024"
   height="1024"
   xmlns:xlink="http://www.w3.org/1999/xlink"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns:bx="https://boxy-svg.com">
  <defs
     id="defs12">
    <linearGradient
       id="linearGradient65">
      <stop
         style="stop-color:#fbfbfb;stop-opacity:1;"
         offset="0"
         id="stop65" />
      <stop
         style="stop-color:#d5d5d5;stop-opacity:1;"
         offset="1"
         id="stop66" />
    </linearGradient>
    <linearGradient
       id="linearGradient63">
      <stop
         style="stop-color:#00adee;stop-opacity:1;"
         offset="0"
         id="stop63" />
      <stop
         style="stop-color:#0088bb;stop-opacity:1;"
         offset="1"
         id="stop64" />
    </linearGradient>
    <bx:guide
       x="-10"
       y="100"
       angle="90" />
    <bx:guide
       x="100"
       y="-10"
       angle="0" />
    <bx:guide
       x="924"
       y="-10"
       angle="0" />
    <bx:guide
       x="-10"
       y="924"
       angle="90" />
    <linearGradient
       xlink:href="#linearGradient63"
       id="linearGradient64"
       x1="576.76422"
       y1="51.5"
       x2="576.76422"
       y2="972.5"
       gradientUnits="userSpaceOnUse" />
    <linearGradient
       xlink:href="#linearGradient65"
       id="linearGradient66"
       x1="428.74286"
       y1="203.06596"
       x2="536.77301"
       y2="812.17596"
       gradientUnits="userSpaceOnUse" />
    <filter
       style="color-interpolation-filters:sRGB"
       id="filter69"
       x="0"
       y="0"
       width="1.0057613"
       height="1.0098504">
      <feFlood
         result="flood"
         in="SourceGraphic"
         flood-opacity="0.498039"
         flood-color="rgb(0,0,0)"
         id="feFlood68" />
      <feGaussianBlur
         result="blur"
         in="SourceGraphic"
         stdDeviation="0.000000"
         id="feGaussianBlur68" />
      <feOffset
         result="offset"
         in="blur"
         dx="3.000000"
         dy="6.000000"
         id="feOffset68" />
      <feComposite
         result="comp1"
         operator="in"
         in="flood"
         in2="offset"
         id="feComposite68" />
      <feComposite
         result="comp2"
         operator="over"
         in="SourceGraphic"
         in2="comp1"
         id="feComposite69" />
    </filter>
  </defs>
  <path
     d="M 284.99805,51.5 C 138.76354,51.5 51.5,160.60109 51.5,285.00195 v 454 C 51.5,863.40283 138.76277,972.5 284.99805,972.5 h 454.0039 C 885.23723,972.5 972.5,863.40283 972.5,739.00195 v -454 C 972.5,160.60109 885.23646,51.5 739.00195,51.5 Z"
     style="baseline-shift:baseline;display:inline;overflow:visible;vector-effect:none;fill:url(#linearGradient64);fill-opacity:1;paint-order:markers fill stroke;enable-background:accumulate;stop-color:#000000"
     id="path63" />
  <path
     d="M 284.99805,1.5 C 112.7794,1.5 1.5,135.74862 1.5,285.00195 v 454 C 1.5,888.25529 112.77939,1022.5 284.99805,1022.5 h 454.0039 C 911.22061,1022.5 1022.5,888.25529 1022.5,739.00195 v -454 C 1022.5,135.74862 911.2206,1.5 739.00195,1.5 Z m 0,50 h 454.0039 C 885.23646,51.5 972.5,160.60109 972.5,285.00195 v 454 C 972.5,863.40283 885.23723,972.5 739.00195,972.5 H 284.99805 C 138.76277,972.5 51.5,863.40283 51.5,739.00195 v -454 C 51.5,160.60109 138.76354,51.5 284.99805,51.5 Z"
     style="baseline-shift:baseline;display:inline;overflow:visible;vector-effect:none;paint-order:markers fill stroke;enable-background:accumulate;stop-color:#000000"
     id="path62" />
  <path
     style="font-size:822.861px;font-family:Arial;-inkscape-font-specification:Arial;font-variant-ligatures:none;fill:url(#linearGradient66);stroke-width:617.148;paint-order:markers fill stroke;filter:url(#filter69)"
     d="m 691.4314,595.61246 77.9468,19.68759 q -24.50904,96.02724 -88.39327,146.65248 -63.48245,50.22345 -155.49181,50.22345 -95.22366,0 -155.09002,-38.57161 -59.46456,-38.9734 -90.804,-112.50053 -30.93764,-73.52714 -30.93764,-157.90253 0,-92.00937 34.95552,-160.31326 35.35731,-68.70568 100.04512,-104.06299 65.08959,-35.7591 143.03638,-35.7591 88.39328,0 148.66142,45.00021 60.26814,45.00022 83.97361,126.5631 l -76.74143,18.08044 q -20.49117,-64.28601 -59.46457,-93.61651 -38.9734,-29.3305 -98.03618,-29.3305 -67.9021,0 -113.70589,32.5448 -45.402,32.5448 -63.88423,87.5897 -18.48223,54.64311 -18.48223,112.90232 0,75.13428 21.69653,131.38455 22.09832,55.84847 68.3039,83.57182 46.20557,27.72334 100.04511,27.72334 65.49138,0 110.89338,-37.76803 45.402,-37.76804 61.4735,-112.09874 z"
     id="text64"
     aria-label="C" />
</svg>
EOF
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Cemu AppImage (x86_64) en GitHub..."

    # Obtener la URL de descarga del último release usando la API de GitHub (filtrando por AppImage y x86_64)
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep -i "x86_64" | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

    if [ -z "$DOWNLOAD_URL" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: $DOWNLOAD_URL"
    mkdir -p "$APPIMAGE_DIR"
    curl -L "$DOWNLOAD_URL" -o "$APPIMAGE_DIR/cemu.AppImage"

    if [ $? -ne 0 ]; then
        error "Error durante la descarga del AppImage"
    fi

    echo "[INFO] Configurando permisos y enlaces..."
    chmod +x "$APPIMAGE_DIR/cemu.AppImage"
    ln -sf "$APPIMAGE_DIR/cemu.AppImage" "$BIN_LINK"

    svg_icon

    # Crear acceso directo para el menú de aplicaciones
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Categories=Game;Emulator;
Comment=Wii U Emulator
Exec=$BIN_LINK
GenericName=Wii U Emulator
Icon=$ICON_PATH
Name=Cemu
StartupNotify=true
Terminal=false
Type=Application
Version=1.0
EOF

    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Cemu..."
    local found=0

    # Comprobar y desinstalar Flatpak
    if command -v flatpak >/dev/null 2>&1 && flatpak list | grep -q "$FLATPAK_ID"; then
        echo "[INFO] Desinstalando versión Flatpak..."
        flatpak uninstall -y $FLATPAK_ID
        flatpak uninstall -y --unused
        found=1
    fi

    # Comprobar y desinstalar AppImage
    if [ -f "$APPIMAGE_DIR/cemu.AppImage" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -f "$BIN_LINK"
        rm -rf "$APPIMAGE_DIR"
        rm -f "$DESKTOP_FILE"
        rm -f "${ICON_PATH}"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Cemu (ni Flatpak ni AppImage)."
    else
        echo "[INFO] Desinstalación completada."
    fi
}

## LLAMADAS

check_root

if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -f : Instalar usando Flatpak"
    echo "  -i : Instalar usando AppImage (x86_64 desde GitHub)"
    echo "  -u : Desinstalar (elimina Flatpak y/o AppImage según lo que encuentre)"
    exit 1
fi

echo "[INFO] Ejecutando acción para el parámetro: $1"

case $1 in
    "-f") install_flatpak;;
    "-i") install_appimage;;
    "-u") uninstall_app;;
    *)
        echo "[ERROR] Parámetro no reconocido."
        exit 1
        ;;
esac

exit 0
