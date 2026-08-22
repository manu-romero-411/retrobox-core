#!/usr/bin/env bash
## INSTALADOR DE RETROARCH (Multi-plataforma: x86_64 y aarch64/Switch L4T)
## FECHA DE ACTUALIZACIÓN: 23 de agosto de 2026
set -eo pipefail

## VARIABLES
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
INSTALL_DIR="${SCRIPT_DIR}/retroarch"
SRC_DIR="${SCRIPT_DIR}/_src"
RETROARCH_SRC="${SRC_DIR}/RetroArch"
TMP_DIR="$(mktemp -d)"
SOURCE_UPSTREAM="https://github.com/libretro/RetroArch.git"
ARCH="$(uname -m)"

# Flags de optimización. -march=native es seguro aquí porque compilamos en el propio dispositivo.
EXTRA_CFLAGS="-O3 -march=native -pipe"

# Cores a gestionar
CORES=(
  fbneo
  mupen64plus_next
)

## FUNCIONES

function error() {
  echo "[ERROR] $*." >&2
  exit 1
}

function desinstalar() {
  echo "[INFO] Desinstalando..."
  rm -rf "${INSTALL_DIR}/app"
  echo "[INFO] Desinstalación completada."
}

function check_deps() {
  echo "[INFO] Comprobando e instalando dependencias de compilación..."
  if command -v dnf &> /dev/null; then
    sudo dnf install -y \
      gcc-c++ cmake make git pkgconf-pkg-config \
      SDL2-devel vulkan-loader-devel vulkan-headers \
      mesa-libGL-devel mesa-libEGL-devel mesa-libGLES-devel \
      libX11-devel freetype-devel libxml2-devel \
      libavcodec-free-devel libavformat-free-devel libavutil-free-devel \
      libswresample-free-devel libswscale-free-devel \
      openal-soft-devel libsndfile-devel libusb1-devel \
      systemd-devel alsa-lib-devel pipewire-devel \
      || error "No se pudieron instalar las dependencias (dnf)"
  else
    sudo apt-get update
    sudo apt-get install -y \
      build-essential cmake make git pkg-config \
      libsdl2-dev libvulkan-dev \
      libgl1-mesa-dev libegl1-mesa-dev libgles2-mesa-dev libx11-dev \
      libfreetype6-dev libxml2-dev \
      libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
      libopenal-dev libsndfile1-dev libusb-1.0-0-dev \
      libudev-dev libasound2-dev libpipewire-0.3-dev \
      || error "No se pudieron instalar las dependencias (apt)"
  fi
}

function check_deps_appimage() {
  echo "[INFO] Comprobando dependencias para AppImage..."
  local falta=()
  command -v curl &> /dev/null || falta+=(curl)
  command -v 7z &> /dev/null || falta+=(p7zip-full)

  if [[ ${#falta[@]} -gt 0 ]]; then
    if command -v dnf &> /dev/null; then
      sudo dnf install -y curl p7zip p7zip-plugins || error "Fallo instalando deps AppImage (dnf)"
    else
      sudo apt-get install -y curl p7zip-full || error "Fallo instalando deps AppImage (apt)"
    fi
  fi
}

function compile_mupen64_next_aarch64() {
  echo "[INFO] El core mupen64plus_next no está en el buildbot para aarch64."
  echo "[INFO] Compilando mupen64plus_next desde fuentes (optimizado para Tegra/ARM)..."
  
  local core_src_dir="${SRC_DIR}/mupen64plus-libretro-nx"
  if [[ ! -d "${core_src_dir}" ]]; then
    git clone --depth 1 https://github.com/libretro/mupen64plus-libretro-nx.git "${core_src_dir}"
  else
    git -C "${core_src_dir}" pull
  fi

  (
    cd "${core_src_dir}" || exit 1
    make clean
    # FORCE_GLES3 y HAVE_NEON son cruciales para el rendimiento en la Switch
    make -j"$(nproc)" platform=unix HAVE_NEON=1 FORCE_GLES3=1
  ) || error "Fallo al compilar mupen64plus_next"

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  cp "${core_src_dir}/mupen64plus_next_libretro.so" "${INSTALL_DIR}/app/share/retroarch/cores/"
  echo "[INFO] Core mupen64plus_next compilado e instalado correctamente."
}

function download_cores() {
  local buildbot_arch=""
  case "${ARCH}" in
    x86_64|amd64) buildbot_arch="x86_64" ;;
    aarch64|arm64) buildbot_arch="aarch64" ;;
    armv7l|armhf) buildbot_arch="armhf" ;;
    i686|i386|x86) buildbot_arch="x86" ;;
    *) echo "[AVISO] Arquitectura no soportada para descarga de cores (${ARCH})."; return ;;
  esac

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  local base="https://buildbot.libretro.com/nightly/linux/${buildbot_arch}/latest"

  echo "[INFO] Obteniendo lista de cores disponibles desde el buildbot (${buildbot_arch})..."
  local cores_list
  cores_list=$(curl -sfL "${base}/" | grep -oE '[a-zA-Z0-9_\-]+_libretro\.so\.zip' | sed -E 's/_libretro\.so\.zip//' | sort -u) || true

  if [[ -z "${cores_list}" ]]; then
    echo "[AVISO] No se pudo obtener la lista de cores del buildbot."
    return
  fi

  for core in ${cores_list}; do
    # Si es aarch64 y el core es mupen64plus_next, lo compilamos en vez de descargar
    if [[ "${buildbot_arch}" == "aarch64" && "${core}" == "mupen64plus_next" ]]; then
      compile_mupen64_next_aarch64
      continue
    fi

    echo "[INFO] Descargando core: ${core}..."
    if curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
      rm -f "${TMP_DIR}/${core}.zip"
    else
      echo "[AVISO] No se pudo descargar el core '${core}', saltando."
    fi
  done
}

function download_selected_cores() {
  local buildbot_arch=""
  case "${ARCH}" in
    x86_64|amd64) buildbot_arch="x86_64" ;;
    aarch64|arm64) buildbot_arch="aarch64" ;;
    armv7l|armhf) buildbot_arch="armhf" ;;
    i686|i386|x86) buildbot_arch="x86" ;;
    *) echo "[AVISO] Arquitectura no soportada para descarga de cores (${ARCH})."; return ;;
  esac

  mkdir -p "${INSTALL_DIR}/app/share/retroarch/cores"
  local base="https://buildbot.libretro.com/nightly/linux/${buildbot_arch}/latest"

  for core in "${CORES[@]}"; do
    if [[ "${buildbot_arch}" == "aarch64" && "${core}" == "mupen64plus_next" ]]; then
      compile_mupen64_next_aarch64
      continue
    fi

    echo "[INFO] Descargando core: ${core}..."
    if curl -sfL "${base}/${core}_libretro.so.zip" -o "${TMP_DIR}/${core}.zip"; then
      unzip -qo "${TMP_DIR}/${core}.zip" -d "${INSTALL_DIR}/app/share/retroarch/cores/"
      rm -f "${TMP_DIR}/${core}.zip"
    else
      echo "[AVISO] No se pudo descargar el core '${core}', saltando."
    fi
  done
}

function download_frontend_assets() {
  local base="https://buildbot.libretro.com/assets/frontend"
  local zip dest
  for entry in \
    "info.zip:${INSTALL_DIR}/app/share/retroarch/cores" \
    "assets.zip:${INSTALL_DIR}/app/share/retroarch/assets" \
    "autoconfig.zip:${INSTALL_DIR}/app/share/retroarch/autoconfig" \
    "cheats.zip:${INSTALL_DIR}/app/share/retroarch/cheats" \
    "database-rdb.zip:${INSTALL_DIR}/app/share/retroarch/database/rdb" \
    "shaders_slang.zip:${INSTALL_DIR}/app/share/retroarch/shaders" \
    "overlays.zip:${INSTALL_DIR}/app/share/retroarch/overlays"
  do
    zip="${entry%%:*}"
    dest="${entry#*:}"
    mkdir -p "${dest}"
    echo "[INFO] Descargando ${zip}..."
    if curl -sfL "${base}/${zip}" -o "${TMP_DIR}/${zip}"; then
      unzip -qo "${TMP_DIR}/${zip}" -d "${dest}/"
      rm -f "${TMP_DIR}/${zip}"
    else
      echo "[AVISO] No se pudo descargar ${zip}, saltando."
    fi
  done
}

function generate_config() {
  mkdir -p "${INSTALL_DIR}/config/retroarch"
  if [[ ! -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
    echo "[INFO] Generando configuración inicial..."
    # Generamos una config básica que apunta a las carpetas correctas
    cat > "${INSTALL_DIR}/config/retroarch.cfg" <<EOF
assets_directory = "${INSTALL_DIR}/app/share/retroarch/assets"
autoconfig_directory = "${INSTALL_DIR}/app/share/retroarch/autoconfig"
cheat_database_path = "${INSTALL_DIR}/app/share/retroarch/cheats"
content_database_path = "${INSTALL_DIR}/app/share/retroarch/database/rdb"
core_directory = "${INSTALL_DIR}/app/share/retroarch/cores"
core_info_path = "${INSTALL_DIR}/app/share/retroarch/cores"
overlay_directory = "${INSTALL_DIR}/app/share/retroarch/overlays"
screenshot_directory = "${INSTALL_DIR}/screenshots"
shader_directory = "${INSTALL_DIR}/app/share/retroarch/shaders"
savefile_directory = "${INSTALL_DIR}/saves"
savestate_directory = "${INSTALL_DIR}/saves"
system_directory = "${INSTALL_DIR}/bios"
video_driver = "vulkan"
video_vsync = "true"
EOF
    echo "[INFO] Configuración inicial creada en ${INSTALL_DIR}/config/retroarch.cfg"
  else
    echo "[INFO] Ya existe retroarch.cfg, se respeta la configuración existente."
  fi
}

function install_source() {
  mkdir -p "${SRC_DIR}"
  check_deps

  echo "[INFO] Clonando RetroArch..."
  if [[ ! -d "${RETROARCH_SRC}" ]]; then
    git clone --recursive "${SOURCE_UPSTREAM}" "${RETROARCH_SRC}"
  else
    git -C "${RETROARCH_SRC}" pull
    git -C "${RETROARCH_SRC}" submodule update --init --recursive
  fi

  echo "[INFO] Configurando y compilando (prefijo: ${INSTALL_DIR}/app)..."
  (
    cd "${RETROARCH_SRC}" || exit 1
    
    # Array de flags de configuración
    local configure_flags=(
      --prefix="${INSTALL_DIR}/app"
      --enable-vulkan
      --enable-pipewire
      --enable-alsa
      --enable-networking
      --enable-discord
      --enable-udev
      --enable-egl
    )

    # Lógica crítica: En ARM (Switch) deshabilitamos GL de escritorio para evitar el conflicto de enlazado
    # En x86_64, habilitamos ambos para máxima compatibilidad con monitores y cores antiguos.
    if [[ "${ARCH}" == "aarch64" || "${ARCH}" == "arm64" ]]; then
      echo "[INFO] Detectada arquitectura ARM. Forzando OpenGL ES 3.0 y Vulkan, deshabilitando OpenGL de escritorio."
      configure_flags+=(--enable-opengles3 --disable-opengl)
    else
      echo "[INFO] Detectada arquitectura x86. Habilitando OpenGL, OpenGL ES 3.0 y Vulkan."
      configure_flags+=(--enable-opengl --enable-opengles3)
    fi

    CFLAGS="${EXTRA_CFLAGS}" CXXFLAGS="${EXTRA_CFLAGS}" ./configure "${configure_flags[@]}" || exit 1
    make -j"$(nproc)" || exit 1
    make install || exit 1
  ) || error "Fallo al compilar/instalar RetroArch."

  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] \
    || error "El build terminó pero no encuentro el binario en ${INSTALL_DIR}/app/bin/retroarch"

  download_selected_cores
  download_frontend_assets
  generate_config

  echo "[INFO] Limpiando fuentes temporales de RetroArch (se conservan las del core N64 si se compiló)..."
  rm -rf "${RETROARCH_SRC}" "${TMP_DIR}"
  
  echo "=========================================================="
  echo "[INFO] ¡Instalación completada con éxito!"
  echo "[INFO] Binario: ${INSTALL_DIR}/app/bin/retroarch"
  echo "[INFO] Config: ${INSTALL_DIR}/config/retroarch.cfg"
  echo "[INFO] Para ejecutar: ${INSTALL_DIR}/app/bin/retroarch -c ${INSTALL_DIR}/config/retroarch.cfg"
  echo "=========================================================="
}

function install_appimage() {
  if [[ "${ARCH}" != "x86_64" && "${ARCH}" != "amd64" ]]; then
    error "Instalación por AppImage solo soportada para x86_64 (detectada: ${ARCH})"
  fi

  desinstalar 2>/dev/null || true
  check_deps_appimage

  local url="https://buildbot.libretro.com/nightly/linux/x86_64/RetroArch.7z"
  local archive="${TMP_DIR}/RetroArch.7z"
  local extract_dir="${TMP_DIR}/extracted"

  echo "[INFO] Descargando RetroArch AppImage..."
  curl -fSL -o "${archive}" "${url}" || error "No se pudo descargar el AppImage"

  echo "[INFO] Extrayendo..."
  mkdir -p "${extract_dir}"
  7z x -y -o"${extract_dir}" "${archive}" >/dev/null || error "Fallo al extraer el .7z"

  local appimage="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage"
  [[ -f "${appimage}" ]] || error "No se ha encontrado el AppImage tras la extracción"
  chmod +x "${appimage}"

  echo "[INFO] Descomprimiendo el AppImage..."
  (
    cd "${extract_dir}" || exit 1
    "${appimage}" --appimage-extract >/dev/null 2>&1 || exit 1
  ) || error "Fallo al descomprimir el AppImage"

  [[ -d "${extract_dir}/squashfs-root/usr" ]] || error "Estructura de squashfs-root inesperada"

  mkdir -p "${INSTALL_DIR}/app"
  cp -r "${extract_dir}/squashfs-root/usr"/* "${INSTALL_DIR}/app"

  [[ -x "${INSTALL_DIR}/app/bin/retroarch" ]] || error "No se encontró el binario tras extraer el AppImage"

  local home_cfg="${extract_dir}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch"
  if [[ -d "${home_cfg}" ]]; then
    mkdir -p "${INSTALL_DIR}/app/share/retroarch"
    cp -r "${home_cfg}"/* "${INSTALL_DIR}/app/share/retroarch/" 2>/dev/null || true
  fi

  mkdir -p "${INSTALL_DIR}/config"
  if [[ -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" ]]; then
    if [[ ! -f "${INSTALL_DIR}/config/retroarch.cfg" ]]; then
      mv "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg" "${INSTALL_DIR}/config/retroarch.cfg"
    else
      rm -f "${INSTALL_DIR}/app/share/retroarch/retroarch.cfg"
    fi
  fi
  generate_config

  download_selected_cores
  rm -rf "${extract_dir}" "${archive}" "${TMP_DIR}"
  
  echo "[INFO] Instalación por AppImage completada."
}

## LLAMADAS
case "$1" in
  "-s") install_source ;;
  "-a") install_appimage ;;
  "-u"|"-d") desinstalar ;;
  *) 
    echo "Uso: $0 {-s|-a|-u}"
    echo "  -s : Instalar desde código fuente (Recomendado para Switch/aarch64 y PCs personalizados)"
    echo "  -a : Instalar desde AppImage (Solo x86_64)"
    echo "  -u : Desinstalar"
    exit 1 
    ;;
esac

exit 0