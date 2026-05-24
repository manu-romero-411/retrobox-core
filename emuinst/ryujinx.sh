#!/usr/bin/env bash
## MULTI-INSTALADOR DE EMULADOR DE SWITCH - RYUJINX / RYUBING
## FECHA DE MODIFICACIÓN: Mayo de 2026
set -o pipefail

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"

if [ -z "$TARGET_USER" ]; then
    TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi

if [ -n "$TARGET_USER" ]; then
    USER_ID="$(getent passwd "$TARGET_USER" | cut -d: -f3)"
    USER_GRP="$(getent passwd "$TARGET_USER" | cut -d: -f4)"
else
    USER_ID=1000
    USER_GRP=1000
fi

# Ajustes de Ryujinx
FLATPAK_ID="org.ryujinx.Ryujinx"
REPO_OWNER="projects"
REPO_NAME="Ryubing"
API_URL="https://git.ryujinx.app/api/v1/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"

INSTALL_DIR="/var/opt/ryubing"
BIN_LINK="/usr/local/bin/ryujinx"
DESKTOP_FILE="/usr/local/share/applications/org.ryujinx.Ryubing.desktop"
ICON_PATH="/usr/share/icons/hicolor/scalable/apps/ryujinx.svg"
TMP_DIR="$(mktemp -d)"

## FUNCIONES DE CONTROL

function error(){
    echo "[ERROR] $@. F"
    rm -rf "$TMP_DIR" 2>/dev/null
    exit 1
}

function check_root(){
    if [ $(id -u) -ne 0 ]; then
        error "Se necesitan permisos de root. Ejecuta con sudo."
    fi
}

function install_dependencies() {
    if ! command -v curl &> /dev/null || ! command -v jq &> /dev/null; then
        echo "[INFO] Instalando dependencias críticas (curl y jq)..."
        if command -v dnf &> /dev/null; then
            dnf install -y curl jq
        elif command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y curl jq
        elif command -v pacman &> /dev/null; then
            pacman -Sy --noconfirm curl jq
        fi
    fi
}

function get_api_json() {
    install_dependencies
    echo "[INFO] Conectando con la API de git.ryujinx.app..."
    JSON_DATA=$(curl -sL -H "Accept: application/json" "$API_URL")
    if [[ -z "$JSON_DATA" || "$JSON_DATA" == *"404 Not Found"* ]]; then
        error "No se pudo obtener respuesta de la API de Ryujinx."
    fi
    TAG_NAME=$(echo "$JSON_DATA" | jq -r '.tag_name')
}

function create_shortcuts() {
    # 1. Detectar dinámicamente el ejecutable o iniciador principal
    local exec_name=""

    if [ -f "$INSTALL_DIR/AppRun" ]; then
        # Si viene de AppImage, el punto de entrada oficial SIEMPRE debe ser AppRun
        exec_name="AppRun"
    elif [ -f "$INSTALL_DIR/Ryujinx" ]; then
        exec_name="Ryujinx"
    elif [ -f "$INSTALL_DIR/Ryubing" ]; then
        exec_name="Ryubing"
    else
        error "No se encontró ningún ejecutable válido en $INSTALL_DIR"
    fi

    echo "[INFO] Creando enlaces globales en /usr/local/bin..."
    cat << EOF > "$BIN_LINK"
#!/bin/bash
DIR="$INSTALL_DIR"
cd "\$DIR"
"\$DIR/$exec_name" "\${@}"
exit \$?
EOF
    ln -sf "$BIN_LINK" /usr/local/bin/ryubing
    chmod +x "$BIN_LINK" /usr/local/bin/ryu*

    # 2. Buscar y configurar el icono extraído
    echo "[INFO] Configurando el icono de la aplicación..."
    local found_icon=$(find "$INSTALL_DIR" -type f \( -name "*ryujinx*.png" -o -name "*ryubing*.png" -o -name "*.svg" \) | head -n 1)

    if [ -n "$found_icon" ]; then
        mkdir -p "$(dirname "$ICON_PATH")"
        cp -f "$found_icon" "$ICON_PATH"
        local final_icon="$ICON_PATH"
    else
        local final_icon="controller" # Fallback por seguridad
    fi

    # 3. Crear Lanzador de Escritorio (.desktop)
    echo "[INFO] Generando archivo de escritorio .desktop..."
    mkdir -p /usr/local/share/applications
    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=Ryubing (Ryujinx)
GenericName=Switch Emulator
Comment=Experimental Nintendo Switch Emulator written in C# / .NET
Icon=${final_icon}
TryExec=ryujinx
Exec=ryujinx %f
Categories=Game;Emulator;
MimeType=application/x-nx-nro;application/x-nx-nso;application/x-nx-nsp;application/x-nx-xci;
Keywords=Nintendo;Switch;Emulator;Ryujinx;Ryubing;
StartupWMClass=Ryujinx
X-Forgejo-Version=${TAG_NAME}
EOF

    # Ajustar permisos globales para el usuario real
    chown -R "${USER_ID}:${USER_GRP}" "$INSTALL_DIR"
}

## MÉTODOS DE INSTALACIÓN

function install_flatpak(){
    echo "[INFO] Instalando Ryujinx vía Flatpak..."
    if ! command -v flatpak &> /dev/null; then
        if [ -f "$ROOTDIR/flatpak.sh" ]; then
            $ROOTDIR/flatpak.sh
        else
            error "Flatpak no está instalado en el sistema y no se encontró flatpak.sh"
        fi
    fi
    flatpak install -y flathub $FLATPAK_ID
    echo "[INFO] Instalación de Flatpak completada."
}

function install_appimage(){
    get_api_json
    echo "[INFO] Filtrando AppImage x64 para la versión: $TAG_NAME"

    DOWNLOAD_URL=$(echo "$JSON_DATA" | jq -r '.assets[] |
        select(.name | endswith(".AppImage") and (contains("arm") or contains("aarch") or contains("zsync") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$DOWNLOAD_URL" || "$DOWNLOAD_URL" == "null" ]]; then
        error "No se encontró un AppImage x64 válido en los assets."
    fi

    echo "[INFO] Descargando AppImage..."
    curl -L "$DOWNLOAD_URL" -o "$TMP_DIR/ryujinx.AppImage" || error "Fallo al descargar la AppImage."
    chmod +x "$TMP_DIR/ryujinx.AppImage"

    # Preparar directorio destino limpio
    rm -rf "$INSTALL_DIR" && mkdir -p "$INSTALL_DIR"

    echo "[INFO] Extrayendo AppImage e importando iconos internos..."
    cd "$INSTALL_DIR" || error "No se pudo acceder al directorio de instalación."
    "$TMP_DIR/ryujinx.AppImage" --appimage-extract > /dev/null

    # Reubicar estructura interna
    mv "${INSTALL_DIR}"/squashfs-root/* "${INSTALL_DIR}/."
    rm -rf "${INSTALL_DIR}/squashfs-root"
    rm -rf "$TMP_DIR"

    create_shortcuts
    echo "[INFO] Instalación mediante AppImage completada con éxito."
}

function install_tar_gz(){
    get_api_json
    echo "[INFO] Filtrando Tarball (.tar.gz) de Linux x64 para la versión: $TAG_NAME"

    DOWNLOAD_URL=$(echo "$JSON_DATA" | jq -r '.assets[] |
        select(.name | (contains("linux") or contains("Linux")) and endswith(".tar.gz") and (contains("arm") or contains("aarch") | not))
        | .browser_download_url' | head -n 1)

    if [[ -z "$DOWNLOAD_URL" || "$DOWNLOAD_URL" == "null" ]]; then
        error "No se encontró un archivo .tar.gz compatible con Linux x64."
    fi

    echo "[INFO] Descargando binarios compactados..."
    curl -L "$DOWNLOAD_URL" -o "$TMP_DIR/ryujinx.tar.gz" || error "Fallo al descargar el archivo comprimido."

    rm -rf "$INSTALL_DIR" && mkdir -p "$INSTALL_DIR"

    echo "[INFO] Desempaquetando archivos..."
    tar -xzf "$TMP_DIR/ryujinx.tar.gz" -C "$TMP_DIR"

    # Manejo flexible de la raíz interna del archivo comprimido
    if [ -d "$TMP_DIR/publish" ]; then
        mv "$TMP_DIR/publish"/* "$INSTALL_DIR/"
    elif ls "$TMP_DIR"/*/Ryujinx &>/dev/null || ls "$TMP_DIR"/*/Ryubing &>/dev/null; then
        mv "$TMP_DIR"/*/* "$INSTALL_DIR/"
    else
        rm -f "$TMP_DIR/ryujinx.tar.gz"
        mv "$TMP_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    fi

    rm -rf "$TMP_DIR"

    # Forzar ejecución en binarios crudos
    find "$INSTALL_DIR" -type f -name "Ryujinx*" -exec chmod +x {} \;
    find "$INSTALL_DIR" -type f -name "Ryubing*" -exec chmod +x {} \;

    create_shortcuts
    echo "[INFO] Instalación mediante tar.gz completada con éxito."
}

function uninstall_all(){
    echo "[INFO] Buscando restos e instalaciones activas..."
    local found=0

    if command -v flatpak >/dev/null 2>&1 && flatpak list | grep -q "$FLATPAK_ID"; then
        echo "[INFO] Removiendo distribución de Flatpak..."
        flatpak uninstall -y $FLATPAK_ID
        flatpak uninstall -y --unused
        found=1
    fi

    if [ -d "$INSTALL_DIR" ] || [ -f "$BIN_LINK" ]; then
        echo "[INFO] Eliminando instalación local (/var/opt)..."
        rm -f "$BIN_LINK"
        rm -f /usr/local/bin/ryubing
        rm -rf "$INSTALL_DIR"
        rm -f "$DESKTOP_FILE"
        rm -f "$ICON_PATH"
        found=1
    fi

    if [ $found -eq 0 ]; then
        echo "[INFO] No se localizó ninguna instalación previa en el sistema."
    fi
}

## CONTROL DE EJECUCIÓN

check_root

if [ -z "$1" ]; then
    echo "Uso: $0 [-f | -i | -t | -u]"
    echo "  -f : Instalar vía Flatpak (Flathub)"
    echo "  -i : Instalar vía AppImage extraído (API Forgejo)"
    echo "  -t : Instalar vía ejecutable directo .tar.gz (API Forgejo)"
    echo "  -u : Desinstalar limpiamente cualquier método detectado"
    exit 1
fi

case $1 in
    "-f") install_flatpak ;;
    "-i") install_appimage ;;
    "-t") install_tar_gz ;;
    "-u") uninstall_all ;;
    *)
        echo "[ERROR] Opción no válida."
        exit 1
        ;;
esac

exit 0
