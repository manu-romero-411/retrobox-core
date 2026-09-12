#!/usr/bin/env bash
# setup/utils/mangohud.sh — build & install MangoHud from source, following
# the exact version/patch set Batocera ships for it, installed under its
# own private prefix ($RETROBOX_ROOTDIR/resources/mangohud) instead of
# /usr/local: this build carries retrobox's own bezel-support patches on
# top of Batocera's, and it must never shadow (or be shadowed by) whatever
# MangoHud the user may already have installed system-wide for other
# purposes. On x86_64 this builds dual 32+64 bit OpenGL/Vulkan support,
# same as Batocera; on any other host (aarch64 and friends) there's no
# 32-bit companion build, so it's 64-bit only. The 32-bit pass on x86_64
# can also be skipped explicitly with -n (see usage below).
#
# Invoked by setup/setup.sh's setup_util() as:
#   bash setup/utils/mangohud.sh -s        (source build — the only option
#                                            this installer has)
#   bash setup/utils/mangohud.sh -s -n     (source build, 64-bit only, even
#                                            on x86_64)
#   bash setup/utils/mangohud.sh -u        (uninstall)
#
# i.e. via `retrobox.sh --setup-util mangohud`.
#
# What -s does:
#   1. Removes any previous from-source install done by THIS script under
#      its own prefix (never touches a system-wide dnf/apt/manual install —
#      that one is left alone on purpose).
#   2. Downloads package/batocera/utils/mangohud/mangohud.mk from the
#      batocera.linux repo to read which tag Batocera builds, and downloads
#      every patch in that same folder.
#   3. Clones MangoHud at that tag (with submodules) and applies the patches.
#   4. Builds it for the native architecture, plus a second 32-bit pass via
#      gcc -m32 when the host is x86_64 (unless -n was given), with
#      --prefix "${PREFIX}", mirroring Batocera's meson options.
#   5. Installs the tree(s) under "${PREFIX}/lib/mangohud/{lib64,lib32}",
#      fixes the `mangohud` wrapper and recreates the $LIB/$PLATFORM
#      compatibility symlinks used by the project's own upstream build.sh
#      (only the x86_64 32-bit-companion ones are architecture-specific;
#      other 64-bit-only hosts — real ones, or x86_64 run with -n — get a
#      smaller, generic set — see fix_wrapper_and_symlinks below). Since
#      the prefix is private, none of this touches the system-wide loader
#      cache (no /etc/ld.so.conf.d entry, no ldconfig run).
#
#      NOTE on $LIB: MangoHud's bin/mangohud.in wrapper template never
#      bakes a resolved lib path — it hardcodes the literal string "$LIB"
#      into LD_PRELOAD/LD_LIBRARY_PATH and relies on ld.so's own dynamic
#      string token substitution to turn it into "lib64"/"lib32" at exec
#      time. That substitution does not reliably happen for every launcher
#      (e.g. apps launched through a bundled/portable interpreter such as
#      sharun, which needs SHARUN_ALLOW_LD_PRELOAD=1 just to attempt
#      preloading at all, and known to mishandle $LIB regardless of host
#      arch — see flightlessmango/MangoHud#665 for the same failure on
#      plain aarch64 too). Since retrobox only ever wraps 64-bit emulator
#      binaries, $LIB's runtime bitness-selection is never actually needed
#      here, so fix_wrapper_and_symlinks() hardcodes the real 64-bit dir
#      directly into the installed wrapper instead of trusting ld.so to
#      expand $LIB — this fixes OpenGL/LD_PRELOAD hooking (e.g. Dolphin)
#      unconditionally, on any host arch. Vulkan was never affected by
#      this, since its implicit-layer JSON is resolved by the Vulkan
#      loader via dlopen(), a different code path that does expand $LIB
#      correctly, and stays relative to the manifest file's own location
#      regardless of which prefix it's installed under.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=../lib/log.sh
source "${SCRIPT_DIR}/../lib/log.sh"

# setup/utils/mangohud.sh -> setup/utils -> setup -> retrobox root.
# Honors an already-exported RETROBOX_ROOTDIR (same convention used by
# runtime.paths on the Python side) instead of always deriving it from
# this script's own location.
RETROBOX_ROOTDIR="${RETROBOX_ROOTDIR:-$(cd "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd -P)}"

MANGOHUD_GIT_URL="https://github.com/flightlessmango/MangoHud.git"
BATOCERA_PKG_DIR="package/batocera/utils/mangohud"
BATOCERA_MK_RAW_URL="https://raw.githubusercontent.com/batocera-linux/batocera.linux/master/${BATOCERA_PKG_DIR}/mangohud.mk"
BATOCERA_API_DIR_URL="https://api.github.com/repos/batocera-linux/batocera.linux/contents/${BATOCERA_PKG_DIR}"

# Private prefix: must match runtime.paths._configgen.MANGOHUD_PREFIX_DIR
# on the Python side, so emulatorlauncher.py finds what we build here.
PREFIX="${RETROBOX_ROOTDIR}/resources/mangohud"
STATE_DIR="${PREFIX}/share/retrobox"
MANIFEST_FILE="${STATE_DIR}/mangohud.manifest"
VERSION_FILE="${STATE_DIR}/mangohud.version"

WORKDIR="${TMPDIR:-/tmp}/retrobox-mangohud-build"
SRC_DIR="${WORKDIR}/MangoHud"
PATCH_DIR="${WORKDIR}/patches"
STAGE_DIR="${WORKDIR}/stage"

# Retrobox's own patches (background_image/image support, etc.), kept by
# hand in the repo — not downloaded from anywhere. Generated with
# `git format-patch` against a clean MangoHud tag and applied AFTER
# Batocera's own (see apply_patches_from_dir in fetch_and_patch_source).
LOCAL_PATCH_DIR="${SCRIPT_DIR}/mangohud-patches"

MACHINE="$(uname -m)"

# Set by argument parsing at the bottom of the script. When 1, the 32-bit
# (i386) build pass is skipped even on an x86_64 host.
SKIP_32BIT=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# True (0) when a 32-bit companion build should actually happen: only on
# x86_64 hosts, and only when the caller hasn't opted out with -n.
want_32bit() {
    [[ "${MACHINE}" == "x86_64" && "${SKIP_32BIT}" -eq 0 ]]
}

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
# Remove any previous retrobox-private MangoHud installation
#
# This ONLY ever touches "${PREFIX}" (retrobox's own private install,
# tracked via MANIFEST_FILE). A system-wide MangoHud installed via
# dnf/apt, or a manual install elsewhere under /usr, is intentionally
# left untouched — that's a separate install for the user's other apps
# and retrobox has no business removing it.
# ---------------------------------------------------------------------------

uninstall_from_source_manifest() {
    [[ -f "${MANIFEST_FILE}" ]] || { log_info "No install manifest to undo."; return 0; }
    log_info "Removing files listed in ${MANIFEST_FILE}..."
    tac "${MANIFEST_FILE}" | while IFS= read -r path; do
        [[ -e "${path}" || -L "${path}" ]] || continue
        rm -f "${path}" 2>/dev/null || rmdir "${path}" 2>/dev/null || true
    done
    rm -f "${MANIFEST_FILE}" "${VERSION_FILE}"
}

remove_existing_install() {
    if [[ -f "${MANIFEST_FILE}" ]]; then
        log_warn "A previous retrobox-private install was detected — cleaning it up before rebuilding."
        uninstall_from_source_manifest
    else
        log_info "No previous retrobox-private MangoHud installation found."
    fi
}

# ---------------------------------------------------------------------------
# Batocera's recipe: version + patches
# ---------------------------------------------------------------------------

fetch_batocera_recipe() {
    mkdir -p "${PATCH_DIR}"

    log_info "Downloading mangohud.mk from batocera.linux..."
    curl -fsSL "${BATOCERA_MK_RAW_URL}" -o "${WORKDIR}/mangohud.mk"

    BATOCERA_VERSION="$(sed -n 's/^MANGOHUD_VERSION\s*=\s*//p' "${WORKDIR}/mangohud.mk" | tr -d '[:space:]')"
    #BATOCERA_VERSION="v0.7.2"
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

# Applies, in order, every file in a patch directory on top of ${SRC_DIR}.
# Used both for Batocera's official patches (downloaded at runtime into
# ${PATCH_DIR}) and for retrobox's own (versioned under ${LOCAL_PATCH_DIR}).
#
# First tries a plain `git apply` (fast, works with both flat diffs and
# `git format-patch`'s mbox header), then `git apply --3way` (rebuilds
# context from the base blobs when the patch carries "index" lines — our
# own format-patch-generated patches; a no-op for Batocera's flat diffs,
# but harmless), and finally `patch --fuzz=3` as a last-resort safety net.
# If Batocera bumps its MangoHud version and a patch stops applying
# cleanly, this buys more margin before failing outright — but it's not
# foolproof: a warning here always deserves a manual review before trusting
# the build.
apply_patches_from_dir() {
    local dir="$1" label="$2"
    shopt -s nullglob
    local patches=("${dir}"/*)
    shopt -u nullglob
    if [[ "${#patches[@]}" -eq 0 ]]; then
        log_warn "No ${label} patches to apply."
        return 0
    fi
    for p in "${patches[@]}"; do
        log_info "Applying patch (${label}): $(basename "${p}")"
        git apply --whitespace=nowarn -p1 "${p}" 2>/dev/null \
            || git apply --whitespace=nowarn -p1 --3way "${p}" 2>/dev/null \
            || patch -p1 --forward --fuzz=3 < "${p}" \
            || log_warn "Patch $(basename "${p}") (${label}) could not be applied -- review it by hand against the current MangoHud."
    done
}

fetch_and_patch_source() {
    rm -rf "${SRC_DIR}"

    if [[ "${BATOCERA_VERSION}" =~ ^[0-9a-fA-F]{40}$ ]]; then
        # Batocera doesn't always pin a release tag (v0.8.4 etc.);
        # sometimes MANGOHUD_VERSION is a bare commit hash (e.g.
        # "Version: Commits from Jun 15, 2024" -> a 40-char SHA in
        # mangohud.mk). A SHA is neither a branch nor a tag, so `git
        # clone --branch` can't resolve it -- not with "tag/" in front
        # (that ref doesn't exist) nor bare (not a branch either).
        # GitHub does allow fetching an arbitrary reachable commit by its
        # SHA (uploadpack.allowReachableSHA1InWant), so in this case we
        # fetch that commit directly instead of cloning by ref.
        log_info "Cloning MangoHud at commit ${BATOCERA_VERSION}..."
        mkdir -p "${SRC_DIR}"
        git -C "${SRC_DIR}" init --quiet
        git -C "${SRC_DIR}" remote add origin "${MANGOHUD_GIT_URL}"
        git -C "${SRC_DIR}" fetch --quiet --depth 1 origin "${BATOCERA_VERSION}"
        git -C "${SRC_DIR}" checkout --quiet FETCH_HEAD
        git -C "${SRC_DIR}" submodule update --init --recursive --depth 1
    else
        # This is a real tag (e.g. "v0.8.4"). --branch resolves tags
        # just like branches -- without "tag/" in front, since that ref
        # doesn't exist in the MangoHud repo.
        log_info "Cloning MangoHud (${BATOCERA_VERSION})..."
        git clone --quiet --recurse-submodules --depth 1 \
            "${MANGOHUD_GIT_URL}" "${SRC_DIR}"
    fi

    cd "${SRC_DIR}"
    apply_patches_from_dir "${PATCH_DIR}" "batocera"
    apply_patches_from_dir "${LOCAL_PATCH_DIR}" "retrobox"
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
            # companions to an x86_64 install, and are only needed when a
            # 32-bit build is actually going to happen (skipped with -n).
            if want_32bit; then
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
                        libvulkan-dev libcurl4-openssl-dev
                        libyaml-cpp-dev libwayland-egl-backend-dev)
            local -a all_deps=("${deps[@]}")

            # Same reasoning as the dnf branch: the i386 foreign-arch
            # packages are only needed to build MangoHud's 32-bit
            # companion, which only happens on x86_64 hosts and only when
            # that pass hasn't been skipped with -n.
            if want_32bit; then
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
                              libgl1-mesa-dev:i386 libvulkan-dev:i386)
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
            log_warn "Unrecognized package manager; install meson, ninja, glslang, dbus/json/wayland/x11/drm/vulkan (dev) manually for your architecture (plus the 32-bit multilib variants too, if this is an x86_64 host and you didn't pass -n)."
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
    log_info "Merging into ${PREFIX}..."
    mkdir -p "${STATE_DIR}"
    rsync -a "${STAGE_DIR}${PREFIX}/" "${PREFIX}/"

    (cd "${STAGE_DIR}${PREFIX}" && find . -type f -o -type l) \
        | sed "s|^\.|${PREFIX}|" > "${MANIFEST_FILE}"
    echo "${BATOCERA_VERSION}" > "${VERSION_FILE}"
}

fix_wrapper_and_symlinks() {
    local libbase="${PREFIX}/lib/mangohud"
    local bin="${PREFIX}/bin/mangohud"
    log_info "Fixing the mangohud wrapper and creating the \$LIB symlinks..."

    if [[ -f "${bin}" ]]; then
        # Build the search/replace strings by concatenating the (possibly
        # user-supplied) PREFIX with a literal, single-quoted suffix, so
        # bash never tries to expand "\$LIB" itself.
        # \\* matches zero or more literal backslashes before $LIB,
        # covering both "\$LIB" (meson's default) and bare "$LIB".
        local search_pattern replace_pattern
        search_pattern="${PREFIX}"'/\\*\$LIB'
        replace_pattern="${PREFIX}"'/lib/mangohud/\\$LIB'
        sed -i "s|${search_pattern}|${replace_pattern}|g" "${bin}"

        # MangoHud's bin/mangohud.in wrapper hardcodes the literal string
        # "$LIB" into LD_PRELOAD/LD_LIBRARY_PATH and expects ld.so to
        # expand it to "lib64"/"lib32" at exec time based on the target
        # process's ELF class. That expansion doesn't reliably happen for
        # every launcher (e.g. apps run through a bundled/portable
        # interpreter like sharun, which needs SHARUN_ALLOW_LD_PRELOAD=1
        # just to attempt preloading at all — and the same "$LIB isn't
        # populated" failure is independently reported on plain aarch64,
        # see flightlessmango/MangoHud#665), breaking OpenGL/LD_PRELOAD
        # hooking while Vulkan (resolved via dlopen() in the Vulkan
        # loader, a different code path) keeps working.
        #
        # retrobox only ever wraps 64-bit emulator binaries, so $LIB's
        # runtime bitness-selection is never actually needed here —
        # hardcode the real 64-bit dir directly into the installed
        # wrapper instead of trusting ld.so to expand $LIB, on any host
        # architecture.
        sed -i 's|\\*\$LIB|lib64|g' "${bin}"
    fi
    mkdir -p "${libbase}/tls"
    ln_safe() { [[ -e "$2" || -L "$2" ]] || ln -sv "$1" "$2"; }

    # $PLATFORM-token aliases for the native build
    ln_safe lib64 "${libbase}/${MACHINE}"
    ln_safe lib64 "${libbase}/${MACHINE}-linux-gnu"
    ln_safe .     "${libbase}/lib64/${MACHINE}"
    ln_safe .     "${libbase}/lib64/${MACHINE}-linux-gnu"

    if want_32bit; then
        # x86_64 biarch setup (a real 32-bit build was actually produced)
        ln_safe lib32 "${libbase}/i686"
        ln_safe lib32 "${libbase}/i386-linux-gnu"
        ln_safe lib32 "${libbase}/i686-linux-gnu"
        ln_safe ../lib32 "${libbase}/tls/i686"
        ln_safe ../lib64 "${libbase}/tls/x86_64"
        ln_safe lib32 "${libbase}/lib"
        ln_safe ../tls "${libbase}/lib/tls"
    else
        # Single-arch host (aarch64, etc.), or x86_64 run with -n: there's
        # no lib32 tree on disk, so $LIB must resolve to lib64 instead —
        # pointing "lib" at a nonexistent lib32 here is what produced the
        # dangling "No such file or directory" symlink failure when the
        # 32-bit pass was skipped/missing.
        ln_safe lib64 "${libbase}/lib"
    fi

    # Deliberately no /etc/ld.so.conf.d entry and no ldconfig run here:
    # ${PREFIX} is a private prefix, not meant to be visible to the
    # system-wide dynamic linker. The wrapper above already has the real
    # lib64 path baked in for OpenGL/LD_PRELOAD, and the Vulkan implicit
    # layer JSON resolves its library relative to its own location, so
    # neither needs the system loader to know about this prefix.
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

    if want_32bit; then
        build_arch 32 "${SRC_DIR}/build/meson32" "lib/mangohud/lib32"
    else
        log_info "Skipping the 32-bit (i386) build."
    fi

    merge_stage_into_prefix
    fix_wrapper_and_symlinks

    #rm -rf "${WORKDIR}"
    log_ok "MangoHud ${BATOCERA_VERSION} installed into ${PREFIX}."
}

do_uninstall() {
    uninstall_from_source_manifest
    log_ok "MangoHud uninstalled from ${PREFIX}."
}

usage() {
    echo "Usage: $(basename "${BASH_SOURCE[0]}") -s [-n] | -u"
    echo "  -s   build and install MangoHud from source (Batocera's recipe)"
    echo "       into retrobox's private prefix (${PREFIX})"
    echo "  -n   (with -s) skip the 32-bit (i386) build, even on x86_64"
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