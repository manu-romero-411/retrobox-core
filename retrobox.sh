#!/usr/bin/env bash

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
export USERDATA="${HERE:-$HOME/.local/share/batocera}"
exec "${USERDATA}/runtime/startup/startup.py" "${@}"