#!/usr/bin/env bash

set -eo pipefail
## INSTALADOR DE RETROARCH
## INSTALABLE EN: x86_64
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHAS DE MODIFICACIÓN:

get_arch(){
	case $(arch) in
		"amd64"|"x86_64") GETARCH="x86_64";;
		*) GETARCH="$(arch)"
	esac
	echo "${GETARCH}"
}

## VARIABLES

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
INSTALL_DIR="${SCRIPT_DIR}/retroarch"
GETARCH=$(get_arch)
URL="https://buildbot.libretro.com/nightly/linux/${GETARCH}/RetroArch.7z"
CORES_URL="https://buildbot.libretro.com/nightly/linux/${GETARCH}/RetroArch_cores.7z"
TMPDIR="$(mktemp -d)"
ARCHIVE="$TMPDIR/RetroArch.7z"

## FUNCIONES

cleanup() {
	rm -rf "$TMPDIR"
}

#trap cleanup EXIT

function install_app(){
	uninstall_app
	# 3. Comprobar curl
	if ! command -v curl &> /dev/null; then
		dnf install curl
	fi

	# Instalar jq si no existe
	if ! command -v jq &> /dev/null; then
		dnf install -y jq
	fi
  
	curl -fSL -o "$ARCHIVE" "$URL"

	# Extraer respetando la estructura dentro del 7z; usamos una extracción temporal y luego movemos
	EXTRACT_DIR="$TMPDIR/extracted"
	mkdir -p "$EXTRACT_DIR"

	# Extraer archivos; la opción -y responde sí a todas las preguntas si las hubiera
	7z x -y -o"$EXTRACT_DIR" "$ARCHIVE"

	mkdir -p "${INSTALL_DIR}/configs/retroarch/cores"
	mkdir -p "${INSTALL_DIR}/app"

	if [ ${GETARCH} == "x86_64" ]; then
		cp -r "${EXTRACT_DIR}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch"/* "${INSTALL_DIR}/configs/retroarch"

		chmod +x "${EXTRACT_DIR}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage"
		(
			cd "${EXTRACT_DIR}" || exit 1
			"${EXTRACT_DIR}/RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage" --appimage-extract >/dev/null 2>&1
			mkdir -p "${INSTALL_DIR}/app"
			cp -r "${PWD}/squashfs-root"/* "${INSTALL_DIR}/app"
		)
	else
		mv "${EXTRACT_DIR}/retroarch" "${INSTALL_DIR}/app/AppRun"
	fi

	rm -r "${EXTRACT_DIR}"
	curl -fSL -o "$ARCHIVE" "$CORES_URL"
	mkdir -p "$EXTRACT_DIR"

	# Extraer archivos; la opción -y responde sí a todas las preguntas si las hubiera
	7z x -y -o"$EXTRACT_DIR" "$ARCHIVE"

	mv "${EXTRACT_DIR}/RetroArch-Linux-${GETARCH}/RetroArch-Linux-${GETARCH}.AppImage.home/.config/retroarch/cores/"* "${INSTALL_DIR}/configs/retroarch/cores"
}

function uninstall_app(){
    rm -rf "${INSTALL_DIR}/app" || true
}

## LLAMADAS

case $1 in
	"-i") install_app;;
	"-u") uninstall_app;;
	*) exit 1;;
esac

exit 0
