# Retrobox setup orchestrator.
#
# Meant to be sourced by retrobox.sh (not executed directly), which is why
# there's no shebang and no `set -euo pipefail` here: those would leak into
# whatever sources this file. Callers are expected to check return codes.
#
# Exposes:
#   is_setup_done              -> 0 if the marker file exists, 1 otherwise
#   full_setup                 -> runs platform setup + git submodules, then
#                                  writes the marker
#   setup_emulator <name>      -> builds setup/emulators/<name>.sh from
#                                  source, auto-detecting which flag it wants
#   list_available_emulators   -> prints every setup/emulators/*.sh found,
#                                  with the flag each would be called with
#   setup_util <name>          -> runs setup/utils/<name>.sh, auto-detecting
#                                  which flag it wants (same convention as
#                                  setup_emulator)
#   list_available_utils       -> prints every setup/utils/*.sh found, with
#                                  the flag each would be called with

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
RETROBOX_ROOTDIR="$(cd "${SETUP_DIR}/.." >/dev/null 2>&1 && pwd -P)"

# shellcheck source=lib/log.sh
source "${SETUP_DIR}/lib/log.sh"

readonly SETUP_MARKER="${RETROBOX_ROOTDIR}/.retrobox_setup_done"

# ---------------------------------------------------------------------------
# Flag detection.
#
# No per-emulator table to keep in sync: each installer's accepted flags are
# read straight from its own `case "$1" in ... esac` (or `case $1 in`, both
# quoted and unquoted flags) dispatch block — the script is never executed
# just to find out what it supports. As soon as an installer starts
# accepting "-s", it gets picked up automatically here.
#
# This is a heuristic text scan, not a shell parser: it assumes each
# installer's flags are plain single-letter case labels (`"-i")`, `-i)`,
# `"-u"|"-d")`...), which is true for every installer in setup/emulators/
# today. If a future installer's usage text happens to mention one of the
# flags below immediately followed by ")" or "|" without it actually being
# implemented, this would report a false positive — acceptable for a
# convenience tool like this one, but worth knowing.
#
# setup/utils/ installers follow the exact same convention, so this same
# scan is reused for both.
# ---------------------------------------------------------------------------

# Preferred, in order, for building from source. "-s" is the convention
# Retrobox is standardizing on; "-c" is kept as a fallback for installers
# (vita3k.sh, as of this writing) that haven't been migrated to "-s" yet.
readonly -a _SOURCE_BUILD_FLAG_PRIORITY=("-s" "-c")

# Preferred, in order, when an installer has no source-build flag at all —
# i.e. it only ships prebuilt binaries/AppImages/tarballs.
readonly -a _INSTALL_FALLBACK_FLAG_PRIORITY=("-i" "-a" "-b")

# Prints the flags an installer script accepts, one per line, sorted.
function _installer_flags() {
    local script="$1"
    sed -n -E '/case[[:space:]]+"?\$1"?[[:space:]]+in/,/esac/p' "${script}" \
        | grep -oP '(?<![A-Za-z0-9_])"?-[A-Za-z]"?(?=[|)])' \
        | tr -d '"' \
        | sort -u
}

# $1 = installer script, $2.. = candidate flags in priority order.
# Prints the first candidate the script actually accepts, or nothing.
function _pick_flag() {
    local script="$1"
    shift
    local -a available
    mapfile -t available < <(_installer_flags "${script}")

    local candidate
    for candidate in "$@"; do
        local a
        for a in "${available[@]}"; do
            [[ "${a}" == "${candidate}" ]] && { echo "${candidate}"; return 0; }
        done
    done
    return 1
}

# Prints the flag to build <script> from source, or "none" if it has no
# source-build option.
function _source_build_flag() {
    local script="$1"
    _pick_flag "${script}" "${_SOURCE_BUILD_FLAG_PRIORITY[@]}" || echo "none"
}

# Prints the best "just install it somehow" flag for <script>, used when it
# has no source-build option. Falls back to the first non-uninstall flag
# found if none of the usual install flags (-i/-a/-b) are present.
function _fallback_install_flag() {
    local script="$1"
    local flag
    if flag="$(_pick_flag "${script}" "${_INSTALL_FALLBACK_FLAG_PRIORITY[@]}")"; then
        echo "${flag}"
        return 0
    fi

    local a
    while IFS= read -r a; do
        [[ "${a}" == "-u" || "${a}" == "-d" ]] && continue
        echo "${a}"
        return 0
    done < <(_installer_flags "${script}")

    return 1
}

# Prints "debian", "fedora", or "unknown" on stdout.
function detect_distro_family() {
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        local ids="${ID:-} ${ID_LIKE:-}"

        if grep -qiE '(^|[[:space:]])fedora([[:space:]]|$)' <<<"${ids}"; then
            echo "fedora"
            return
        fi
        if grep -qiE '(^|[[:space:]])debian([[:space:]]|$)' <<<"${ids}"; then
            echo "debian"
            return
        fi
    fi

    # Fallback for systems without (or with an unrecognized) os-release:
    # guess from whichever package manager is on PATH.
    if command -v dnf &>/dev/null; then
        echo "fedora"
    elif command -v apt-get &>/dev/null; then
        echo "debian"
    else
        echo "unknown"
    fi
}

function init_submodules() {
    if [[ ! -f "${RETROBOX_ROOTDIR}/.gitmodules" ]]; then
        log_info "No .gitmodules found, skipping git submodule init."
        return 0
    fi
    if ! command -v git &>/dev/null; then
        log_warn "git not found on PATH, cannot initialize submodules."
        return 0
    fi

    log_info "Initializing git submodules..."
    if (cd "${RETROBOX_ROOTDIR}" && git submodule update --init --recursive); then
        log_ok "Git submodules ready."
    else
        log_err "Failed to initialize git submodules."
        return 1
    fi
}

function run_platform_setup() {
    local family="$1"

    case "${family}" in
        debian)
            log_info "Detected a Debian-based system."
            bash "${SETUP_DIR}/setup-debian.sh"
            ;;
        fedora)
            log_info "Detected a Fedora-based system."
            bash "${SETUP_DIR}/setup-fedora.sh"
            ;;
        *)
            log_err "Could not detect a supported distro family (Debian- or Fedora-based). Skipping platform setup."
            log_warn "You can still install individual emulators with: retrobox.sh --setup-emulator <name>"
            return 1
            ;;
    esac
}

# $1 = human-readable kind ("emulator" or "utility"), $2 = installer script,
# $3 = name (for logging).
function _run_installer() {
    local kind="$1" script="$2" name="$3"

    local flag
    flag="$(_source_build_flag "${script}")"

    if [[ "${flag}" == "none" ]]; then
        local fallback
        if ! fallback="$(_fallback_install_flag "${script}")"; then
            log_err "Could not find any usable flag for '${name}' (checked its case \"\$1\" dispatch)."
            return 1
        fi
        log_warn "'${name}' has no source-build option in its installer, falling back to ${fallback} (prebuilt/AppImage)."
        flag="${fallback}"
    fi

    log_info "Running ${kind} installer for '${name}' (${flag})..."
    if bash "${script}" "${flag}"; then
        log_ok "'${name}' installed."
    else
        log_err "Installer for '${name}' failed."
        return 1
    fi
}

function setup_emulator() {
    local name="$1"
    local script="${SETUP_DIR}/emulators/${name}.sh"

    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for emulator '${name}' (expected ${script})."
        return 1
    fi

    _run_installer "emulator" "${script}" "${name}"
}

function setup_util() {
    local name="$1"
    local script="${SETUP_DIR}/utils/${name}.sh"

    if [[ ! -f "${script}" ]]; then
        log_err "No installer found for utility '${name}' (expected ${script})."
        return 1
    fi

    _run_installer "utility" "${script}" "${name}"
}

# $1 = directory (emulators/ or utils/), $2 = label for the log line.
function _list_available_installers() {
    local dir="$1" label="$2"

    shopt -s nullglob
    local -a scripts=("${dir}"/*.sh)
    shopt -u nullglob

    if [[ "${#scripts[@]}" -eq 0 ]]; then
        log_warn "No ${label} installers found in ${dir}/."
        return 0
    fi

    log_info "Available ${label} installers:"
    local f name flag
    for f in "${scripts[@]}"; do
        name="$(basename "${f}" .sh)"
        flag="$(_source_build_flag "${f}")"
        if [[ "${flag}" == "none" ]]; then
            flag="$(_fallback_install_flag "${f}")" || flag="?"
            printf '  - %-14s (no source build; installs with %s)\n' "${name}" "${flag}"
        else
            printf '  - %-14s (source build: %s)\n' "${name}" "${flag}"
        fi
    done
}

function list_available_emulators() {
    _list_available_installers "${SETUP_DIR}/emulators" "emulator"
}

function list_available_utils() {
    _list_available_installers "${SETUP_DIR}/utils" "utility"
}

function mark_setup_done() {
    local family="$1"
    {
        echo "distro_family=${family}"
        echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${SETUP_MARKER}"
}

function is_setup_done() {
    [[ -f "${SETUP_MARKER}" ]]
}

function full_setup() {
    local family status=0
    family="$(detect_distro_family)"

    run_platform_setup "${family}" || status=1
    init_submodules || status=1

    if [[ "${status}" -eq 0 ]]; then
        mark_setup_done "${family}"
        log_ok "Retrobox setup complete."
    else
        log_err "Retrobox setup finished with errors — not marking it as done."
    fi

    return "${status}"
}