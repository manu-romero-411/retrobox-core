#!/usr/bin/env bash

set -eo pipefail

## INSTALADOR DE RETROARCH
## INSTALABLE EN: x86_64
## FECHA DE CREACIÓN: 1 de noviembre de 2025
## FECHAS DE MODIFICACIÓN:

## VARIABLES

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOTDIR="$(realpath "$SCRIPT_DIR/..")"
if [ -z "$TARGET_USER" ]; then
	TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi

if [ -n "$TARGET_USER" ]; then
	USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
fi

if [ -z "${USER_HOME}" ]; then
  USER_HOME=/home/$(id -nu 1000)
fi

URL="https://buildbot.libretro.com/nightly/linux/x86_64/RetroArch.7z"
DESTDIR="$SCRIPT_DIR"
TMPDIR="$(mktemp -d)"
ARCHIVE="$TMPDIR/RetroArch.7z"

## FUNCIONES

cleanup() {
	rm -rf "$TMPDIR"
}

trap cleanup EXIT

function install_app(){
	uninstall_app
	mkdir -p "$DESTDIR"
	chmod 0755 "$DESTDIR"

	curl -fSL -o "$ARCHIVE" "$URL"

	# Extraer respetando la estructura dentro del 7z; usamos una extracción temporal y luego movemos
	EXTRACT_DIR="$TMPDIR/extracted"
	mkdir -p "$EXTRACT_DIR"

	# Extraer archivos; la opción -y responde sí a todas las preguntas si las hubiera
	7z x -y -o"$EXTRACT_DIR" "$ARCHIVE"

	rsync -av "$EXTRACT_DIR"/RetroArch-Linux-x86_64 "$DESTDIR"
	mv "$DESTDIR"/RetroArch-Linux-x86_64 "$DESTDIR"/retroarch

	# establecer permisos razonables: directorios 755, archivos 644, ejecutables detectados 755
	find "${DESTDIR}/retroarch" -type d -exec chmod 0755 {} +
	find "${DESTDIR}/retroarch" -type f -exec chmod 0644 {} +
	#mkdir -p "${USER_HOME}/.config/"
	#mv "${DESTDIR}/retroarch/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch" "${USER_HOME}/.config/retroarch"
	#rm -r "${DESTDIR}/retroarch/RetroArch-Linux-x86_64.AppImage.home"

	chown -R 1000:1000 "${DESTDIR}/retroarch" "${USER_HOME}/.config/retroarch"

	chmod +x ${DESTDIR}/retroarch/RetroArch-Linux-x86_64.AppImage
	#ln -s ${DESTDIR}/retroarch/RetroArch-Linux-x86_64.AppImage /usr/local/bin/retroarch
	#desktop_file
}

function uninstall_app(){
    rm -rf "/usr/local/bin/retroarch" || true
    rm -rf "${DESTDIR}/retroarch" || true
	rm -f "${USER_HOME}/.app-icons/svg/retroarch.svg" || true
    rm -f /usr/local/share/applications/retroarch-standalone.desktop || true
}

## LLAMADAS

case $1 in
	"-i") install_app;;
	"-u") uninstall_app;;
	*) exit 1;;
esac

exit 0
