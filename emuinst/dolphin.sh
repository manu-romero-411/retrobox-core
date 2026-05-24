#!/usr/bin/env bash
## INSTALADOR DE DOLPHIN
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHAS DE MODIFICACIÓN: Modificado para soportar AppImage y Flatpak

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"

FLATPAK_ID="org.DolphinEmu.dolphin-emu"
GITHUB_REPO="pkgforge-dev/Dolphin-emu-AppImage"
APPIMAGE_DIR="/opt/dolphin-emu"
BIN_LINK="/usr/local/bin/dolphin-emu"
DESKTOP_FILE="/usr/local/share/applications/dolphin-emu.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/dolphin-emu.svg"

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
    echo "[INFO] Instalando Dolphin vía Flatpak..."
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
    #mkdir -p /home/$(id -nu 1000)/.app-icons/svg
    cat << EOF > ${ICON_PATH}
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 459.97 2048.07 1128.55">
 <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="506" x2="0" y2="1588">
  <stop offset="0" stop-color="#46D4FF"/>
  <stop offset="1" stop-color="#1792FF"/>
 </linearGradient>
 <path fill="#0057ab" d="m2046.8,1538.65 c-6.813,-22.834 -49.283,-160.537 -120.831,-292.567 -94.261,-173.943 -175.33,-298.279 -310.402,-424.563 -43.445,-40.618 -84.6,-76.916 -127.448,-109.498 l0.047,0 c0,0 -0.329,-0.232 -0.926,-0.673 -0.801,-0.607 -1.602,-1.214 -2.403,-1.818 -15.987,-12.352 -83.345,-69.109 -59.382,-131.767 8.031,-21 27.421,-38.45 50.479,-52.569 l124.091,-1.011 v-46 l-0.03,10e-4 c10e-4,0 0.016,-0.003 0.016,-0.003 0,0 -72.661,-24.686 -199.807,-16.53 -119.328,7.655 -226.545,77.432 -246.588,87.241 -64.265,-18.396 -137.59,-34.619 -223.344,-49.168 -296.609,-50.323 -547.639,29.896 -673.604,117.325 -165.101,114.592 -160.533,221.368 -174.144,274.776 -8.431,33.085 -83.408,94.263 -82.51,137.183 v45.18 l15.489,15.96 58.397,-19.849 6.985,-24.359 c24.022,-8.59 50.325,-20.532 74.217,-30.359 59.615,-24.521 64.209,-37.858 227.133,-62.167 74.956,-11.184 153.843,-14.393 212.575,-14.886 22.855,48.26 79.68,147.46 178.133,195.042 64.027,30.944 135.739,46.795 192.883,54.915 l-7.493,37.679 113.668,16.846 v-45.969 l-0.087,-0.035 c0.022,0 0.035,0 0.035,0 0,0 -95.434,-39.648 -154.146,-98.356 -39.956,-39.953 -49.518,-100.64 -51.552,-135.342 l0.359,0.033 c96.193,18.278 180.215,31.468 381.156,108.425 37.166,14.233 71.829,29.835 103.407,45.589 l-5.935,3.35 90.575,73.044 108.183,89.527 v-45.969 l-0.358,-0.332 c-1.596,-1.983 -124.799,-154.603 -331.827,-256.712 -171.102,-84.392 -311.585,-126.087 -506.229,-135.527 -212.756,-10.319 -369.522,16.999 -369.522,16.999 0,0 4.385,-94.537 165.003,-169.88 139.666,-65.516 359.388,-76.481 611.558,-12.15 356.261,90.886 477.766,245.646 631.012,405.573 97.226,101.465 186.606,244.229 242.951,343.009 l-9.49,-4.259 29.19,75.387 41.753,89.096 v-46.264 l-1.237,-3.603 z"/>
 <path fill="url(#g)" d="m1926,1292 c-94.261,-173.943 -175.33,-298.279 -310.402,-424.563 -43.446,-40.619 -84.601,-76.917 -127.45,-109.499 l0.049,0.01 c0,0 -0.34,-0.24 -0.962,-0.699 -0.773,-0.586 -1.547,-1.172 -2.321,-1.757 -15.904,-12.279 -83.413,-69.084 -59.428,-131.801 26.32,-68.822 174.556,-99.582 174.556,-99.582 0,0 -72.661,-24.686 -199.807,-16.53 -119.328,7.655 -226.545,77.432 -246.588,87.241 -64.265,-18.396 -137.59,-34.619 -223.344,-49.168 -296.609,-50.323 -547.639,29.896 -673.604,117.325 -165.101,114.592 -160.533,221.368 -174.144,274.776 -9.794,38.432 -109.389,114.772 -75.534,156.367 21.122,25.95 91.411,-9.289 148.113,-32.611 59.615,-24.521 64.209,-37.859 227.133,-62.168 74.956,-11.184 153.843,-14.393 212.575,-14.886 22.855,48.26 79.68,147.46 178.133,195.042 132.934,64.246 299.005,63.438 299.005,63.438 0,0 -95.434,-39.648 -154.146,-98.356 -39.956,-39.953 -49.518,-100.64 -51.552,-135.342 l0.359,0.033 c96.193,18.278 180.215,31.468 381.156,108.425 175.815,67.334 295.91,165.256 295.91,165.256 0,0 -123.479,-153.98 -331.865,-256.76 -171.102,-84.391 -311.585,-126.086 -506.229,-135.526 -212.756,-10.319 -369.522,16.999 -369.522,16.999 0,0 4.385,-94.537 165.003,-169.88 139.666,-65.516 359.388,-76.481 611.558,-12.15 356.261,90.886 477.766,245.646 631.012,405.573 163.107,170.22 304.146,456.685 304.146,456.685 0,0 -43.489,-151.357 -121.81,-295.887 z"/>
</svg>
EOF
	#chown -R 1000:1000 /home/$(id -nu 1000)/.app-icons/svg
}

function install_appimage(){
    echo "[INFO] Buscando la última versión de Dolphin AppImage en GitHub..."

    # Obtener la URL de descarga del último release usando la API de GitHub
    DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep x86_64 | grep "browser_download_url.*\.AppImage" |  cut -d '"' -f 4 | head -n 1)

    if [ -z "$DOWNLOAD_URL" ]; then
        error "No se pudo obtener la URL de descarga del AppImage desde GitHub"
    fi

    echo "[INFO] Descargando: $DOWNLOAD_URL"
    mkdir -p "$APPIMAGE_DIR"
    curl -L "$DOWNLOAD_URL" -o "$APPIMAGE_DIR/dolphin.AppImage"

    if [ $? -ne 0 ]; then
        error "Error durante la descarga del AppImage"
    fi

    echo "[INFO] Configurando permisos y enlaces..."
    chmod +x "$APPIMAGE_DIR/dolphin.AppImage"
    ln -sf "$APPIMAGE_DIR/dolphin.AppImage" "$BIN_LINK"
	svg_icon
    # Crear acceso directo para el menú de aplicaciones
    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Categories=Game;Emulator;
Comment=A Wii/GameCube Emulator\s
Exec=$BIN_LINK
GenericName=Wii/GameCube Emulator
Icon=$ICON_PATH
Name=Dolphin Emulator
NoDisplay=false
Path=
PrefersNonDefaultGPU=false
StartupNotify=true
Terminal=false
TerminalOptions=
Type=Application
Version=1.0
X-Desktop-File-Install-Version=0.28
X-Flatpak=org.DolphinEmu.dolphin-emu
X-Flatpak-RenamedFrom=dolphin-emu.desktop;
X-KDE-SubstituteUID=false
X-KDE-Username=
EOF

    echo "[INFO] Instalación de AppImage completada."
}

function uninstall_app(){
    echo "[INFO] Buscando instalaciones de Dolphin..."
    local found=0

    # Comprobar y desinstalar Flatpak
    if command -v flatpak >/dev/null 2>&1 && flatpak list | grep -q "$FLATPAK_ID"; then
        echo "[INFO] Desinstalando versión Flatpak..."
        flatpak uninstall -y $FLATPAK_ID
        flatpak uninstall -y --unused
        found=1
    fi

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

check_root

if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -u]"
    echo "  -f : Instalar usando Flatpak"
    echo "  -i : Instalar usando AppImage (desde GitHub)"
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
