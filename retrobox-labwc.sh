#!/bin/bash

RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

# forma "habitual" de entrar en el entorno
if [[ "$1" == "-n" ]] || [[ "$1" == "--non-immersive" ]]; then
	shift 1
	exec ${RETROBOX_ROOTDIR}/retrobox.sh "${@}"
	exit $?
fi

# nueva forma de acceder al entorno, desde tty8,
# con labwc para sortear los problemas de rendimiento de plasma

#!/bin/bash
VT_DESTINO=8

vt_origen=$(sed 's/tty//' /sys/class/tty/tty0/active)
echo "$vt_origen" >"/tmp/retrobox-ttysave"

sudo /usr/local/bin/go2tty "$VT_DESTINO"

exit $?
