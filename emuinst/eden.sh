#!/usr/bin/env bash
## INSTALADOR DE EMULADOR DE SWITCH - EDEN (FORGEJO API VERSION)
## FECHA DE MODIFICACIÓN: 2026 (Adaptado para git.eden-emu.dev)
set -o pipefail

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"

if [ -z "$TARGET_USER" ]; then
    TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi

if [ -n "$TARGET_USER" ]; then
    USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
    USER_ID="$(getent passwd "$TARGET_USER" | cut -d: -f3)"
    USER_GRP="$(getent passwd "$TARGET_USER" | cut -d: -f4)"
else
    USER_HOME=/home/$(id -nu 1000)
    USER_ID=1000
    USER_GRP=1000
fi

INSTALL_DIR="/var/opt/eden-emu"
TMP_DIR="$(mktemp -d)"

## FUNCIONES
function error() {
    echo "[ERROR] $@"
    exit 1
}

function check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "[MALAMENTE] No eres root. Ejecuta con sudo."
    fi
}

function appimage_install(){
    # 2. Variables de la API de Forgejo (git.eden-emu.dev)
    # Estructura del repositorio: eden-emu/eden
    REPO_OWNER="eden-emu"
    REPO_NAME="eden"
    API_URL="https://git.eden-emu.dev/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

    # 3. Comprobar dependencias críticas (curl y jq)
    if ! command -v curl &> /dev/null; then
        echo "Instalando curl..."
        if command -v dnf &> /dev/null; then dnf install -y curl; else apt-get update && apt-get install -y curl; fi
    fi
    
    if ! command -v jq &> /dev/null; then
        echo "Instalando jq..."
        if command -v dnf &> /dev/null; then dnf install -y jq; else apt-get update && apt-get install -y jq; fi
    fi

    # 4. Obtener JSON desde la API de Forgejo
    echo "Conectando con la API de git.eden-emu.dev..."
    json=$(curl -sL -H "Accept: application/json" "$API_URL")

    if [[ -z "$json" || "$json" == *"404 Not Found"* ]]; then
        error "No se pudo conectar a la API o el repositorio no existe."
    fi

    # 5. Extraer tag_name
    TAG_NAME=$(echo "$json" | jq -r '.tag_name')
    echo "Última versión detectada: $TAG_NAME"

    # 6. Extraer URL del AppImage desde los assets de Forgejo
    # Filtramos por .AppImage, que no sea zsync y que sea para x86_64
    APPIMAGE_URL=$(echo "$json" | jq -r '.assets[] | 
        select(.name | endswith(".AppImage") 
        and (contains("arm") or contains("aarch") or contains("AppImage.zsync") | not)) 
        | .browser_download_url' | head -n 1)

    if [[ -z "$APPIMAGE_URL" || "$APPIMAGE_URL" == "null" ]]; then
        error "No se encontró ningún AppImage válido en la última release de Forgejo."
    fi

    echo "Descargando desde: $APPIMAGE_URL"

    # 7. Preparar directorio de instalación
    mkdir -p "$INSTALL_DIR"

    # 8. Descargar y mover
    curl -L "$APPIMAGE_URL" -o "$TMP_DIR/eden-emu.AppImage" || error "Error al descargar el archivo."

    mv "$TMP_DIR/eden-emu.AppImage" "$INSTALL_DIR/eden-emu.AppImage"
    chmod +x "$INSTALL_DIR/eden-emu.AppImage"

    # 9. Limpiar temporal inicial
    rm -rf "$TMP_DIR"

    # 10. Extracción e instalación de la AppImage (Desempaquetado)
    cd "$INSTALL_DIR" || error "No se pudo acceder a $INSTALL_DIR"
    
    echo "Extrayendo AppImage..."
    "$INSTALL_DIR/eden-emu.AppImage" --appimage-extract > /dev/null
    
    mv "${INSTALL_DIR}"/squashfs-root/* "${INSTALL_DIR}/."
    rm -rf "${INSTALL_DIR}/squashfs-root"
    rm -rf "$INSTALL_DIR/eden-emu.AppImage"

    # Asignar permisos al usuario real detectado dinámicamente
    chown -R "${USER_ID}:${USER_GRP}" "${INSTALL_DIR}"

    # 11. Crear ejecutables globales en el PATH
    cat << EOF > /usr/local/bin/eden
#!/bin/bash
DIR="$INSTALL_DIR"
cd "\$DIR"
"\$DIR/AppRun" "\${@}"
exit \$?
EOF
    ln -sf /usr/local/bin/eden /usr/local/bin/eden-emu
    chmod +x /usr/local/bin/eden*

    # 12. Crear el archivo de Lanzador de Escritorio (.desktop)
    mkdir -p /usr/local/share/applications
    cat << EOF > /usr/local/share/applications/dev.eden_emu.eden.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Eden
GenericName=Switch Emulator
Comment=Multiplatform FOSS Switch 1 emulator written in C++, derived from Yuzu and Sudachi
Icon=${INSTALL_DIR}/dev.eden_emu.eden.svg
TryExec=eden
Exec=eden %f
Categories=Game;Emulator;Qt;
MimeType=application/x-nx-nro;application/x-nx-nso;application/x-nx-nsp;application/x-nx-xci;
Keywords=Nintendo;Switch;
StartupWMClass=eden
X-AppImage-Version=${TAG_NAME}
X-AppImage-Arch=x86_64
EOF

    echo "¡Eden Emulator ($TAG_NAME) instalado con éxito!"
}

function desinstalar() {
    echo "Desinstalando Eden Emulator..."
    rm -f "/usr/local/bin/eden"
    rm -f "/usr/local/bin/eden-emu"
    rm -rf "${INSTALL_DIR}"
    rm -f /usr/local/share/applications/dev.eden_emu.eden.desktop
    echo "Desinstalación completa."
}

## LLAMADAS
check_root

case "$1" in
    -i) appimage_install ;;
    -u) desinstalar ;;
    *) echo "Uso: $0 {-i (instalar) | -u (desinstalar)}" ; exit 1 ;;
esac

exit 0
