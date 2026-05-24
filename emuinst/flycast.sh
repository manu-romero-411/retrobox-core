#!/usr/bin/env bash
## INSTALADOR DE FLYCAST
## FECHA DE CREACIÓN: 19 de mayo de 2026
## FECHAS DE MODIFICACIÓN: Creado con soporte para AppImage (x86_64) y Flatpak

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

FLATPAK_ID="org.flycast.Flycast"
GITHUB_REPO="flyinghead/flycast"
APPIMAGE_DIR="/opt/flycast"
BIN_LINK="/usr/local/bin/flycast"
DESKTOP_FILE="/usr/local/share/applications/flycast.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/flycast.svg"

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
    echo "[INFO] Instalando Flycast vía Flatpak..."
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
    # Genera un logo en formato SVG (espiral azul inspirada en el logo de Flycast)
    mkdir -p "$(dirname "$ICON_PATH")"
    cat << 'EOF' > "${ICON_PATH}"
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   version="1.1"
   x="0px"
   y="0px"
   viewBox="0 0 397.88 354.59"
   xml:space="preserve"
   id="svg32"
   width="397.88"
   height="354.59"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg"><defs
   id="defs32"><linearGradient
     id="SVGID_1_"
     gradientUnits="userSpaceOnUse"
     x1="275.88239"
     y1="356.82349"
     x2="275.88239"
     y2="17.0588"
     gradientTransform="translate(-70,-17.06)">
		<stop
   offset="0.1"
   style="stop-color:#6F2EE4"
   id="stop17" />
		<stop
   offset="0.9"
   style="stop-color:#9C55FE"
   id="stop18" />
	</linearGradient></defs>
<style
   type="text/css"
   id="style1">
	.st0{opacity:0.5;}
	.st1{fill:#5B01BD;}
	.st2{fill:url(#SVGID_1_);}
	.st3{fill:url(#SVGID_2_);stroke:#F5A400;stroke-miterlimit:10;}
	.st4{fill:url(#SVGID_3_);stroke:#F5A400;stroke-miterlimit:10;}
	.st5{fill:url(#SVGID_4_);stroke:#F5A400;stroke-miterlimit:10;}
	.st6{fill:url(#SVGID_5_);stroke:#F5A400;stroke-miterlimit:10;}
	.st7{fill:url(#SVGID_6_);stroke:#F5A400;stroke-miterlimit:10;}
	.st8{fill:url(#SVGID_7_);stroke:#F5A400;stroke-miterlimit:10;}
	.st9{fill:url(#SVGID_8_);stroke:#F5A400;stroke-miterlimit:10;}
</style>
<path
   class="st0"
   d="m 337.65,238.12 c 0,14.35 4.47,23.76 12.47,23.76 8,0 35.06,0.47 35.06,-36.71 0,-27.29 -24.29,-99.53 -56.06,-132 C 300.28,63.69 241.59,13.99 167.59,13.99 45.71,14 0,91.76 0,165.65 c 0,67.29 33.02,110.59 52.94,133.18 24.4,27.67 75.53,55.76 116.24,55.76 138.59,0 140.53,-120.96 140.53,-144.35 0,-85.65 -73.47,-140.82 -141.24,-140.82 -33.88,0 -99.29,21.41 -99.29,104.47 0,81.65 88.47,106.12 107.29,106.12 31.06,0 71.29,-33.06 71.29,-73.18 0,-31.59 -25.94,-85.88 -67.76,-85.88 -25.65,0 -48.24,26.35 -48.24,49.18 0,20.71 9.06,32.83 20.24,43.06 12.53,11.47 16.18,6.53 21.82,2.76 5.65,-3.76 20.06,-16.86 12.29,-25.12 -6.8,-7.23 -25.12,-20.12 -25.12,-20.12 0,0 0.32,-13.29 17.35,-13.29 25.41,0 36.94,20.24 36.94,40.47 0,20.47 -26.12,48 -26.12,48 0,0 -84.94,-32.24 -84.94,-72.47 0,-40.47 24,-69.88 67.06,-69.88 19.06,0 50.18,5.91 71.76,28.94 16.79,17.91 32.71,43.29 32.71,69.65 0,21.4 -12,82.12 -57.41,106.82 L 134.22,322.71 58.57,249.89 19.76,130.59 c 0,0 25.62,-28.49 50.82,-47.53 32.71,-24.71 62.34,-29.18 91.06,-29.18 22.35,0 77.19,3.96 127.76,51.53 27.85,26.19 50.12,76.47 50.12,106.82 0.01,12.24 -1.87,20.71 -1.87,25.89 z"
   id="path8" />
<path
   class="st1"
   d="m 351.29,227.06 c 0,13.62 3.12,23.76 12.47,23.76 8,0 26.88,-1.41 26.88,-34.18 0,-25.94 -22.76,-91.7 -54.53,-122.57 C 307.27,66.05 248.58,18.81 174.58,18.81 52.7,18.81 14.16,90.12 14.16,160.35 c 0,42.94 10.96,72.87 43.48,117.52 23.65,32.47 80.92,65.65 124.34,65.65 77.05,0 98.89,-33.07 107.9,-44.47 9.01,-11.4 32.47,-88.15 32.47,-97.76 0,-81.41 -80.47,-127.9 -148.24,-127.9 -22.99,0 -62.26,8.45 -80.43,38.29 -11.8,19.38 -10.78,46.44 -10.78,56.08 0,27.41 12.54,49.28 33.57,68.71 24.71,22.82 54.35,32.24 73.18,32.24 30,0 65.12,-28.48 65.12,-66.61 0,-30.02 -28.24,-86.81 -70.06,-86.81 -20.82,0 -39.53,24 -39.53,43.29 0,25.06 11.29,36.18 22.47,45.9 12.53,10.9 16.17,1.03 21.82,-2.55 5.65,-3.58 5.83,-10.1 -1.94,-17.94 -6.8,-6.87 -12.71,-12.8 -12.71,-19.06 0,-6.26 1.32,-18.35 18.35,-18.35 26.71,0 35.65,24.15 35.65,40.59 0,19.46 -23.18,56.47 -51.88,56.47 -43.06,0 -75.53,-31.99 -75.53,-70.24 0,-21.63 1.72,-34.22 19.06,-49.41 18.3,-16.03 33.65,-31.53 64,-31.53 22.12,0 49.65,6.35 72.24,29.88 16.56,17.25 32.47,41.18 32.47,67.99 0,20.01 -6.82,50.36 -23.76,76.24 -20.21,30.87 -64.47,53.65 -64.47,53.65 0,0 -90.81,-24.38 -118.95,-50.69 -32.34,-30.25 -47.65,-77.02 -47.65,-105.65 0,-29.84 12.12,-59.06 42.82,-85.53 30.7,-26.47 56.71,-35.18 96.24,-35.18 41.18,0 87.09,6.42 136.24,61.06 33.65,37.41 43.76,78.35 43.76,98.12 0,6.29 -2.12,19.12 -2.12,24.71 z"
   id="path9" />
<path
   class="st2"
   d="m 364.94,232.94 c 0,8.94 -0.56,17.07 8.61,17.07 8,0 24.33,-4.36 24.33,-41.54 0,-27.29 -18,-96.82 -49.76,-129.29 C 319.28,49.7 260.59,0 186.59,0 64.71,0 13.88,80 13.88,153.88 c 0,44.71 47.06,185.88 186.35,185.88 109.65,0 128.47,-120.13 128.47,-143.53 0,-85.65 -74.82,-138.82 -142.59,-138.82 -33.88,0 -101.29,21.76 -101.29,96.59 0,45.53 51.53,109.76 116.12,109.76 22.94,0 65.82,-30.82 65.82,-70.94 0,-31.59 -26.65,-83.12 -68.47,-83.12 -20.82,0 -47.82,15.88 -47.82,40.06 0,18.82 8.76,37.24 19.94,47.47 12.53,11.47 16.18,6.53 21.82,2.76 5.64,-3.77 7.77,-11.51 0,-19.76 -6.8,-7.23 -12.24,-16.94 -12.24,-23.53 0,-6.59 3.68,-20.71 20.71,-20.71 26.71,0 38,28.24 38,45.53 0,20.47 -15.41,51.41 -44.12,51.41 -43.06,0 -79.41,-40.82 -79.41,-81.06 0,-43.06 37.06,-70.59 81.88,-70.59 19.06,0 50.55,10.44 72.13,33.47 16.79,17.91 29.4,44.09 29.4,80.53 0,21.4 -8.38,47.66 -23.58,69.52 -17.23,24.77 -43.22,43.89 -75.72,43.89 -35.06,0 -77.16,-17.26 -105.29,-44.94 -32.34,-31.82 -51.88,-91.06 -51.88,-121.18 0,-40.26 20.92,-69.35 46.49,-87.89 30.62,-22.2 62.67,-29.17 91.39,-29.17 22.35,0 86.27,10.76 136.85,58.33 27.85,26.19 49.03,81.43 49.03,115.67 0.01,12.25 -0.93,33.43 -0.93,33.43 z"
   id="path18"
   style="fill:url(#SVGID_1_)" />
</svg>
EOF
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Flycast AppImage (x86_64) en GitHub..."

    # Obtener la URL de descarga del último release usando la API de GitHub
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep -i x86_64 | grep "browser_download_url.*\.AppImage" | cut -d '"' -f 4 | head -n 1)

    if [ -z "$DOWNLOAD_URL" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: $DOWNLOAD_URL"
    mkdir -p "$APPIMAGE_DIR"
    curl -L "$DOWNLOAD_URL" -o "$APPIMAGE_DIR/flycast.AppImage"

    if [ $? -ne 0 ]; then
        error "Error durante la descarga del AppImage"
    fi

    echo "[INFO] Configurando permisos y enlaces..."
    chmod +x "$APPIMAGE_DIR/flycast.AppImage"
    ln -sf "$APPIMAGE_DIR/flycast.AppImage" "$BIN_LINK"

    svg_icon

    # Crear acceso directo para el menú de aplicaciones
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Categories=Game;Emulator;
Comment=Sega Dreamcast, Naomi and Atomiswave Emulator
Exec=$BIN_LINK
GenericName=Dreamcast Emulator
Icon=$ICON_PATH
Name=Flycast
StartupNotify=true
Terminal=false
Type=Application
Version=1.0
EOF

    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Flycast..."
    local found=0

    # Comprobar y desinstalar Flatpak
    if command -v flatpak >/dev/null 2>&1 && flatpak list | grep -q "$FLATPAK_ID"; then
        echo "[INFO] Desinstalando versión Flatpak..."
        flatpak uninstall -y $FLATPAK_ID
        flatpak uninstall -y --unused
        found=1
    fi

    # Comprobar y desinstalar AppImage
    if [ -f "$APPIMAGE_DIR/flycast.AppImage" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Desinstalando versión AppImage..."
        rm -f "$BIN_LINK"
        rm -rf "$APPIMAGE_DIR"
        rm -f "$DESKTOP_FILE"
        rm -f "${ICON_PATH}"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se encontró ninguna instalación de Flycast (ni Flatpak ni AppImage)."
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
