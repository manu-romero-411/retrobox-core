#!/usr/bin/env bash
# setup/utils/mangohud.sh — build & install MangoHud from source, following
# the exact version/patch set Batocera ships for it, installed under
# /usr/local. On x86_64 this builds dual 32+64 bit OpenGL/Vulkan support,
# same as Batocera; on any other host (aarch64 and friends) there's no
# 32-bit companion build, so it's 64-bit only.
#
# Invoked by setup/setup.sh's setup_util() as:
#   bash setup/utils/mangohud.sh -s     (source build — the only option
#                                        this installer has)
#   bash setup/utils/mangohud.sh -u     (uninstall)
#
# i.e. via `retrobox.sh --setup-util mangohud`.
#
# What -s does:
#   1. Detects and removes any existing MangoHud install (dnf, apt, or a
#      previous from-source install done by this same script).
#   2. Downloads package/batocera/utils/mangohud/mangohud.mk from the
#      batocera.linux repo to read which tag Batocera builds, and downloads
#      every patch in that same folder.
#   3. Clones MangoHud at that tag (with submodules) and applies the patches.
#   4. Builds it for the native architecture, plus a second 32-bit pass via
#      gcc -m32 when the host is x86_64, with --prefix /usr/local, mirroring
#      Batocera's meson options.
#   5. Installs the tree(s) under /usr/local/lib/mangohud/{lib64,lib32},
#      fixes the `mangohud` wrapper and recreates the $LIB/$PLATFORM
#      compatibility symlinks used by the project's own upstream build.sh
#      (only the x86_64 32-bit-companion ones are architecture-specific;
#      other 64-bit-only hosts get a smaller, generic set — see
#      fix_wrapper_and_symlinks below).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=../lib/log.sh
source "${SCRIPT_DIR}/../lib/log.sh"

MANGOHUD_GIT_URL="https://github.com/flightlessmango/MangoHud.git"
BATOCERA_PKG_DIR="package/batocera/utils/mangohud"
BATOCERA_MK_RAW_URL="https://raw.githubusercontent.com/batocera-linux/batocera.linux/master/${BATOCERA_PKG_DIR}/mangohud.mk"
BATOCERA_API_DIR_URL="https://api.github.com/repos/batocera-linux/batocera.linux/contents/${BATOCERA_PKG_DIR}"

PREFIX="/usr/local"
STATE_DIR="${PREFIX}/share/retrobox"
MANIFEST_FILE="${STATE_DIR}/mangohud.manifest"
VERSION_FILE="${STATE_DIR}/mangohud.version"

WORKDIR="${TMPDIR:-/tmp}/retrobox-mangohud-build"
SRC_DIR="${WORKDIR}/MangoHud"
PATCH_DIR="${WORKDIR}/patches"
STAGE_DIR="${WORKDIR}/stage"

MACHINE="$(uname -m)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

detect_pkg_manager() {
    if command -v dnf >/dev/null 2>&1; then
        echo dnf
    elif command -v apt-get >/dev/null 2>&1; then
        echo apt
    else
        echo unknown
    fi
}
PKG_MGR="$(detect_pkg_manager)"

as_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

# ---------------------------------------------------------------------------
# Remove any previous MangoHud installation
# ---------------------------------------------------------------------------

uninstall_from_source_manifest() {
    [[ -f "${MANIFEST_FILE}" ]] || { log_info "No install manifest to undo."; return 0; }
    log_info "Removing files listed in ${MANIFEST_FILE}..."
    tac "${MANIFEST_FILE}" | while IFS= read -r path; do
        [[ -e "${path}" || -L "${path}" ]] || continue
        as_root rm -f "${path}" 2>/dev/null || as_root rmdir "${path}" 2>/dev/null || true
    done
    as_root rm -f "${MANIFEST_FILE}" "${VERSION_FILE}"
}

remove_existing_install() {
    local found=0

    if rpm -q mangohud &>/dev/null 2>&1; then
        found=1
        log_warn "MangoHud installed via dnf/rpm — removing it."
        as_root dnf remove -y mangohud
    fi

    if dpkg -s mangohud &>/dev/null 2>&1; then
        found=1
        log_warn "MangoHud installed via apt/dpkg — removing it."
        as_root apt-get remove -y mangohud
    fi

    if [[ -f "${MANIFEST_FILE}" ]]; then
        found=1
        log_warn "A previous from-source install was detected — cleaning it up before rebuilding."
        uninstall_from_source_manifest
    fi

    for legacy in /usr/lib/mangohud /usr/bin/mangohud /usr/bin/mangoplot \
                  /usr/share/vulkan/implicit_layer.d/MangoHud.x86_64.json \
                  /usr/share/vulkan/implicit_layer.d/MangoHud.x86.json \
                  /usr/share/vulkan/implicit_layer.d/mangohud.json; do
        if [[ -e "${legacy}" ]]; then
            found=1
            log_warn "Leftover from a manual install under /usr: ${legacy}"
            as_root rm -rf "${legacy}"
        fi
    done

    [[ "${found}" -eq 0 ]] && log_info "No previous MangoHud installation found."
}

# ---------------------------------------------------------------------------
# Batocera's recipe: version + patches
# ---------------------------------------------------------------------------

fetch_batocera_recipe() {
    mkdir -p "${PATCH_DIR}"

    log_info "Downloading mangohud.mk from batocera.linux..."
    curl -fsSL "${BATOCERA_MK_RAW_URL}" -o "${WORKDIR}/mangohud.mk"

    BATOCERA_VERSION="$(sed -n 's/^MANGOHUD_VERSION\s*=\s*//p' "${WORKDIR}/mangohud.mk" | tr -d '[:space:]')"
    if [[ -z "${BATOCERA_VERSION}" ]]; then
        log_err "Could not extract MANGOHUD_VERSION from mangohud.mk"
        exit 1
    fi
    log_info "Version used by Batocera: ${BATOCERA_VERSION}"

    log_info "Listing patches in ${BATOCERA_PKG_DIR}..."
    local listing="${WORKDIR}/dir-listing.json"
    curl -fsSL -H "Accept: application/vnd.github+json" "${BATOCERA_API_DIR_URL}" -o "${listing}"

    # Batocera's patches follow the NNN-description(.patch|.json) pattern;
    # the odd .json in there (001-no-mangohud.json) is actually a diff too,
    # so we pick files by their numeric prefix, not by extension.
    python3 - "${listing}" "${PATCH_DIR}" <<'PYEOF'
import json, sys, re, urllib.request, os

listing_path, patch_dir = sys.argv[1], sys.argv[2]
with open(listing_path) as f:
    entries = json.load(f)

pat = re.compile(r'^\d{3}-.*')
picked = sorted(
    (e for e in entries if e.get("type") == "file" and pat.match(e.get("name", ""))),
    key=lambda e: e["name"],
)
if not picked:
    print("No patches matching the NNN-* pattern were found.", file=sys.stderr)

for e in picked:
    dest = os.path.join(patch_dir, e["name"])
    urllib.request.urlretrieve(e["download_url"], dest)
    print(f"  - {e['name']}")
PYEOF
}

fetch_and_patch_source() {
    rm -rf "${SRC_DIR}"
    log_info "Cloning MangoHud (${BATOCERA_VERSION})..."
    git clone --quiet --recurse-submodules --branch "${BATOCERA_VERSION}" --depth 1 \
        "${MANGOHUD_GIT_URL}" "${SRC_DIR}"

    cd "${SRC_DIR}"
    shopt -s nullglob
    local patches=("${PATCH_DIR}"/*)
    shopt -u nullglob
    if [[ "${#patches[@]}" -eq 0 ]]; then
        log_warn "No patches to apply (did the batocera.linux repo layout change?)."
    fi
    for p in "${patches[@]}"; do
        log_info "Applying patch: $(basename "${p}")"
        git apply --whitespace=nowarn -p1 "${p}" 2>/dev/null \
            || patch -p1 --forward < "${p}" \
            || { log_err "Patch $(basename "${p}") could not be applied."; exit 1; }
    done
    cd - >/dev/null
}

# ---------------------------------------------------------------------------
# Build dependencies (including 32-bit)
# ---------------------------------------------------------------------------

# Detects whether any "*-backports" repository is enabled and prints its
# suite name (e.g. "trixie-backports", "bookworm-backports",
# "noble-backports"...), or nothing if none is enabled.
#
# Relies on `apt-cache policy`, which already aggregates ALL configured
# sources regardless of where/how they're declared: the classic one-line
# format (/etc/apt/sources.list and /etc/apt/sources.list.d/*.list) and the
# newer deb822 format (*.sources). This way we don't have to hand-parse
# either format, and it works the same whether the system is on stable with
# backports enabled, on testing/sid (where backports doesn't exist, so
# nothing is detected), or on an Ubuntu with its own "<codename>-backports".
detect_apt_backports_suite() {
    # The "|| true" is needed because with `set -e` a grep with no matches
    # (a system without backports, e.g. testing/sid) returns 1 and would
    # abort the whole script when assigning the result to a variable.
    apt-cache policy 2>/dev/null \
        | grep -oP '\ba=\K[A-Za-z0-9._-]+-backports' \
        | sort -u | head -n1 || true
}

install_build_deps() {
    log_info "Installing build dependencies (${PKG_MGR})..."
    case "${PKG_MGR}" in
        dnf)
            local deps=(meson ninja-build gcc gcc-c++ git python3-mako glslang
                        dbus-devel json-devel wayland-devel libxkbcommon-devel
                        libX11-devel libdrm-devel mesa-libGL-devel
                        vulkan-loader-devel vulkan-headers libcurl-devel)
            local -a all_deps=("${deps[@]}")

            # The i686 (32-bit) multilib devel packages only exist as
            # companions to an x86_64 install; on any other host (aarch64,
            # etc.) there's no 32-bit build to satisfy, so skip them.
            if [[ "${MACHINE}" == "x86_64" ]]; then
                local deps32=(glibc-devel.i686 libstdc++-devel.i686 libX11-devel.i686
                              wayland-devel.i686 libxkbcommon-devel.i686
                              mesa-libGL-devel.i686 vulkan-loader-devel.i686)
                all_deps+=("${deps32[@]}")
            fi

            as_root dnf install -y "${all_deps[@]}"
            ;;
        apt)
            local deps=(meson ninja-build git python3-mako glslang-tools
                        libdbus-1-dev nlohmann-json3-dev libwayland-dev
                        libxkbcommon-dev libx11-dev libdrm-dev libgl1-mesa-dev
                        libvulkan-dev libcurl4-openssl-dev)
            local -a all_deps=("${deps[@]}")

            # Same reasoning as the dnf branch: the i386 foreign-arch
            # packages are only needed to build MangoHud's 32-bit
            # companion, which only happens on x86_64 hosts.
            if [[ "${MACHINE}" == "x86_64" ]]; then
                if ! dpkg --print-foreign-architectures | grep -q i386; then
                    log_info "Enabling the i386 architecture for 32-bit libs..."
                    as_root dpkg --add-architecture i386
                    as_root apt-get update
                fi
                # gcc/g++-multilib bring in whichever 32-bit libstdc++-dev
                # matches the current gcc version, instead of pinning a
                # versioned package name (libstdc++-12-dev...) that breaks
                # the moment the distro bumps its gcc version.
                local deps32=(gcc-multilib g++-multilib libx11-dev:i386
                              libwayland-dev:i386 libxkbcommon-dev:i386
                              libgl1-mesa-dev:i386)
                all_deps+=("${deps32[@]}")
            fi

            local -a apt_install_opts=(install -y)
            local backports_suite
            backports_suite="$(detect_apt_backports_suite)"
            if [[ -n "${backports_suite}" ]]; then
                log_info "Backports repository detected (${backports_suite}); it will be used for whatever needs it."
                apt_install_opts+=(-t "${backports_suite}")
            fi

            as_root apt-get "${apt_install_opts[@]}" "${all_deps[@]}"
            ;;
        *)
            log_warn "Unrecognized package manager; install meson, ninja, glslang, dbus/json/wayland/x11/drm/vulkan (dev) manually for your architecture (plus the 32-bit multilib variants too, if this is an x86_64 host)."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Build (64 + 32 bit) and install into /usr/local
# ---------------------------------------------------------------------------

meson_opts_common() {
    local opts=(-Dappend_libdir_mangohud=false -Dwith_xnvctrl=disabled)
    pkg-config --exists x11 2>/dev/null && opts+=(-Dwith_x11=enabled) || opts+=(-Dwith_x11=disabled)
    pkg-config --exists wayland-client 2>/dev/null && opts+=(-Dwith_wayland=enabled) || opts+=(-Dwith_wayland=disabled)
    printf '%s\n' "${opts[@]}"
}

build_arch() {
    local bits="$1" builddir="$2" libdir="$3"
    cd "${SRC_DIR}"

    local -a opts
    mapfile -t opts < <(meson_opts_common)

    if [[ "${bits}" == "32" ]]; then
        export CC="gcc -m32"
        export CXX="g++ -m32"
        export PKG_CONFIG_PATH="/usr/lib32/pkgconfig:/usr/lib/i386-linux-gnu/pkgconfig:/usr/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    else
        unset CC CXX
        # ${MACHINE}-linux-gnu covers the Debian/Ubuntu multiarch layout on
        # whatever the native architecture is (x86_64-linux-gnu,
        # aarch64-linux-gnu, ...); /usr/lib64 covers Fedora-style hosts.
        # Harmless if a given path doesn't exist — pkg-config just skips it.
        export PKG_CONFIG_PATH="/usr/lib64/pkgconfig:/usr/lib/${MACHINE}-linux-gnu/pkgconfig:/usr/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    fi

    log_info "Configuring the ${bits}-bit build..."
    meson setup "${builddir}" --prefix "${PREFIX}" --libdir "${libdir}" \
        --buildtype=release "${opts[@]}"

    log_info "Compiling the ${bits}-bit build..."
    ninja -C "${builddir}"

    log_info "Installing (staged) the ${bits}-bit build..."
    DESTDIR="${STAGE_DIR}" ninja -C "${builddir}" install

    unset CC CXX PKG_CONFIG_PATH
    cd - >/dev/null
}

merge_stage_into_prefix() {
    log_info "Merging into ${PREFIX} (requires privileges)..."
    as_root mkdir -p "${STATE_DIR}"
    as_root rsync -a "${STAGE_DIR}${PREFIX}/" "${PREFIX}/"

    (cd "${STAGE_DIR}${PREFIX}" && find . -type f -o -type l) \
        | sed "s|^\.|${PREFIX}|" | as_root tee "${MANIFEST_FILE}" >/dev/null
    echo "${BATOCERA_VERSION}" | as_root tee "${VERSION_FILE}" >/dev/null
}

fix_wrapper_and_symlinks() {
    local libbase="${PREFIX}/lib/mangohud"
    local bin="${PREFIX}/bin/mangohud"
    log_info "Fixing the mangohud wrapper and creating the \$LIB symlinks..."
    
    if [[ -f "${bin}" ]]; then
        # Use single quotes so bash doesn't mangle the backslashes.
        # \\* matches zero or more literal backslashes before $LIB,
        # covering both "\$LIB" (meson's default) and bare "$LIB".
        as_root sed -i 's|/usr/local/\\*\$LIB|/usr/local/lib/mangohud/\\$LIB|g' "${bin}"
    fi
    as_root mkdir -p "${libbase}/tls"
    ln_safe() { [[ -e "$2" || -L "$2" ]] || as_root ln -sv "$1" "$2"; }
    
    # $PLATFORM-token aliases for the native build
    ln_safe lib64 "${libbase}/${MACHINE}"
    ln_safe lib64 "${libbase}/${MACHINE}-linux-gnu"
    ln_safe .     "${libbase}/lib64/${MACHINE}"
    ln_safe .     "${libbase}/lib64/${MACHINE}-linux-gnu"
    
    if [[ "${MACHINE}" == "x86_64" ]]; then
        # x86_64 biarch setup
        ln_safe lib32 "${libbase}/i686"
        ln_safe lib32 "${libbase}/i386-linux-gnu"
        ln_safe lib32 "${libbase}/i686-linux-gnu"
        ln_safe ../lib32 "${libbase}/tls/i686"
        ln_safe ../lib64 "${libbase}/tls/x86_64"
        ln_safe lib32 "${libbase}/lib"
        ln_safe ../tls "${libbase}/lib/tls"
    else
        # Single-arch host (aarch64, etc.): $LIB expands to "lib"
        ln_safe lib64 "${libbase}/lib"
    fi
    
    echo "${libbase}/lib64" | as_root tee /etc/ld.so.conf.d/mangohud.conf >/dev/null
    [[ "${MACHINE}" == "x86_64" ]] && echo "${libbase}/lib32" | as_root tee -a /etc/ld.so.conf.d/mangohud.conf >/dev/null
    as_root ldconfig
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

do_install() {
    remove_existing_install
    rm -rf "${WORKDIR}"
    mkdir -p "${WORKDIR}"

    fetch_batocera_recipe
    install_build_deps
    fetch_and_patch_source

    build_arch 64 "${SRC_DIR}/build/meson64" "lib/mangohud/lib64"
    if [[ "${MACHINE}" == "x86_64" ]]; then
        build_arch 32 "${SRC_DIR}/build/meson32" "lib/mangohud/lib32"
    else
        log_info "Host has no 32-bit companion build on this architecture (${MACHINE}); building 64-bit only."
    fi

    merge_stage_into_prefix
    fix_wrapper_and_symlinks

    rm -rf "${WORKDIR}"
    log_ok "MangoHud ${BATOCERA_VERSION} installed into ${PREFIX}."
}

do_uninstall() {
    uninstall_from_source_manifest
    as_root rm -f /etc/ld.so.conf.d/mangohud.conf
    as_root ldconfig || true
    log_ok "MangoHud uninstalled."
}

usage() {
    echo "Usage: $(basename "${BASH_SOURCE[0]}") -s | -u"
    echo "  -s   build and install MangoHud from source (Batocera's recipe)"
    echo "  -u   uninstall the install done by this script"
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

case "$1" in
    "-s")
        do_install
        ;;
    "-u")
        do_uninstall
        ;;
    *)
        usage
        exit 1
        ;;
esac