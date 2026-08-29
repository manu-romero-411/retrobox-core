#!/usr/bin/env bash
# Retrobox entrypoint.
#
# On a normal launch, runs the one-time platform setup automatically the
# first time it's invoked (detecting Debian- vs Fedora-based systems), then
# starts the frontend. Setup can also be triggered manually:
#
#   retrobox.sh --setup                     force the platform setup again
#   retrobox.sh --setup-emulator <name>      build a single emulator from
#                                            source (repeatable)
#   retrobox.sh --setup-emulator             list available emulators
#
# Both of the above are maintenance operations: they run and then exit,
# they don't start the frontend afterwards. Any other argument is passed
# through to runtime/startup/retrobox_run.py untouched.
set -eo pipefail

RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SETUP_DIR="${RETROBOX_ROOTDIR}/setup"
RUN_SCRIPT="${RETROBOX_ROOTDIR}/runtime/startup/retrobox_run.py"

# shellcheck source=setup/setup.sh
source "${SETUP_DIR}/setup.sh"

function usage() {
    cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [OPTIONS] [-- ARGS...]

  --setup                     Force the platform setup (system packages,
                               udev rules, git submodules) even if it has
                               already run before.
  --setup-emulator <name>     Build/install a single emulator from source
                               (e.g. --setup-emulator retroarch). Can be
                               repeated to install several at once. Called
                               with no name, lists every installer available
                               under setup/emulators/.
  -h, --help                  Show this help and exit.

With no options, Retrobox runs the platform setup automatically the first
time (and only the first time) it's launched, then starts the frontend.
Anything else you pass is forwarded as-is to the frontend.
EOF
}

force_setup=0
declare -a emulators_to_setup=()
declare -a frontend_args=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --setup)
            force_setup=1
            shift
            ;;
        --setup-emulator)
            if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
                list_available_emulators
                exit 0
            fi
            emulators_to_setup+=("$2")
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            frontend_args+=("$@")
            break
            ;;
        *)
            frontend_args+=("$1")
            shift
            ;;
    esac
done

did_maintenance=0

if [[ "${force_setup}" -eq 1 ]]; then
    log_info "Forcing platform setup..."
    full_setup
    did_maintenance=1
fi

if [[ "${#emulators_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${emulators_to_setup[@]}"; do
        setup_emulator "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${did_maintenance}" -eq 1 ]]; then
    exit 0
fi

if ! is_setup_done; then
    log_warn "Retrobox hasn't been set up on this machine yet. Running first-time setup..."
    full_setup
fi

exec "${RUN_SCRIPT}" "${frontend_args[@]}"
