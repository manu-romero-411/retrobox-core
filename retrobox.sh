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
#   retrobox.sh --setup-util <name>          run a single utility installer
#                                            (e.g. mangohud) (repeatable)
#   retrobox.sh --setup-util                 list available utility installers
#   retrobox.sh --setup-music <name>         install a single music pack
#                                            (e.g. music-pack-2). Can be
#                                            repeated. Called with no name,
#                                            lists every installer available
#                                            under setup/music/.
#   retrobox.sh --bios-check [system...]    check installed RetroArch BIOS
#                                            files against what the cores
#                                            need (all systems if none given)
#   retrobox.sh --bios-fetch [opts] [system...]
#                                            download missing BIOS files for
#                                            the given systems straight from
#                                            the RetroBIOS project, one file
#                                            at a time (no full repo clone).
#                                            Run '--bios-fetch --list' for
#                                            available systems, or
#                                            '--bios-fetch --dry-run <system>'
#                                            to preview without downloading.
#
# All of the above are maintenance operations: they run and then exit,
# they don't start the frontend afterwards. Any other argument is passed
# through to runtime/startup/retrobox_run.py untouched.
set -eo pipefail
RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
SETUP_DIR="${RETROBOX_ROOTDIR}/setup"
RUN_SCRIPT="${RETROBOX_ROOTDIR}/runtime/startup/retrobox_run.py"

# shellcheck source=setup/setup.sh
source "${SETUP_DIR}/setup.sh"
# shellcheck source=setup/bios-check.sh
source "${SETUP_DIR}/bios/bios-check.sh"
# shellcheck source=setup/bios-fetch.sh
source "${SETUP_DIR}/bios/bios-fetch.sh"

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
--setup-util <name>         Run a single utility installer (e.g.
                            --setup-util mangohud). Can be repeated to
                            install several at once. Called with no name,
                            lists every installer available under
                            setup/utils/.
--setup-music <name>        Install a single music pack (e.g.
                            --setup-music music-pack-2). Can be
                            repeated to install several at once. Called
                            with no name, lists every installer available
                            under setup/music/.
--bios-check [system...]    Check installed RetroArch BIOS files under
                            bios/<system>/ against what each system's
                            cores require. With no system given, checks
                            everything defined in resources/systems_config.
--bios-fetch [opts] [system...]
                            Download BIOS files for the given system(s)
                            (Batocera native_id, e.g. psx, gba, dreamcast,
                            neocd) straight from the RetroBIOS project
                            (github.com/Abdess/retrobios), one file at a
                            time, verifying checksums. Everything after
                            --bios-fetch is forwarded as-is; run
                            '--bios-fetch --list' to see available
                            systems, or '--bios-fetch --dry-run <system>'
                            to preview without downloading.
-h, --help                  Show this help and exit.

With no options, Retrobox runs the platform setup automatically the first
time (and only the first time) it's launched, then starts the frontend.
Anything else you pass is forwarded as-is to the frontend.
EOF
}

force_setup=0
do_bios_check=0
do_bios_fetch=0
declare -a emulators_to_setup=()
declare -a utils_to_setup=()
declare -a music_to_setup=()
declare -a bios_check_systems=()
declare -a bios_fetch_args=()
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
--setup-util)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_utils
        exit 0
    fi
    utils_to_setup+=("$2")
    shift 2
    ;;
--setup-music)
    if [[ -z "${2:-}" || "${2:0:1}" == "-" ]]; then
        list_available_music
        exit 0
    fi
    music_to_setup+=("$2")
    shift 2
    ;;
--bios-check)
    do_bios_check=1
    shift
    while [[ -n "${1:-}" && "${1:0:1}" != "-" ]]; do
        bios_check_systems+=("$1")
        shift
    done
    ;;
--bios-fetch)
    do_bios_fetch=1
    shift
    bios_fetch_args=("$@")
    break
    ;;
-h | --help)
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

if [[ "${#utils_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${utils_to_setup[@]}"; do
        setup_util "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${#music_to_setup[@]}" -gt 0 ]]; then
    status=0
    for name in "${music_to_setup[@]}"; do
        setup_music "${name}" || status=1
    done
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${do_bios_check}" -eq 1 ]]; then
    bios_check "${bios_check_systems[@]}"
    status=$?
    did_maintenance=1
    [[ "${status}" -eq 0 ]] || exit "${status}"
fi

if [[ "${do_bios_fetch}" -eq 1 ]]; then
    bios_fetch "${bios_fetch_args[@]}"
    status=$?
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