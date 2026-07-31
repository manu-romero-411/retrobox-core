#!/usr/bin/env bash

RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
exec "${RETROBOX_ROOTDIR}/runtime/startup/retrobox_run.py" "${@}"