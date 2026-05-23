# retrobox-core

A proof-of-concept port of the [batocera](https://github.com/batocera-linux/batocera.linux) backend stack to a standard Linux desktop (Debian / KDE Plasma / Wayland), using `batocera-configgen` as a base.

The goal is to have a batocera/Retrobat-like experience if paired with a compiled [batocera-emulationstation](https://github.com/batocera-linux/batocera-emulationstation) frontend, featuring automatic emulator configuration, bezels, shaders, controller mapping — without having to reboot to other OS.

---

## Motivation

Batocera is excellent as a dedicated gaming system, but it needs to be booted as a whole OS. A few years ago, I discovered Retrobat, but it is Windows-only (there are some ways to run it on Linux with Wine/Lutris, but not all emulators work). RetroDeck, EmuDeck and ES-DE doesn't have all the goodies Retrobat and Batocera have, such as auto gamepad config (the most important thing for me).

This project brings the parts that matter most to a desktop Linux installation:

- `batocera-configgen` writing emulator configs automatically on game launch
- Bezels work in Vulkan-powered emulators via a patched MangoHud build (the same approach batocera uses)
- Shader support via RetroArch's slang pipeline
- Adapted ontroller autoconfiguration for RetroArch, Flycast, Dolphin, PCSX2, PPSSPP, Cemu, Ryujinx and Eden. More to come.

---

## Architecture

```
EmulationStation
    └── on game launch → emulatorlauncher.sh
            ├── sync_settings.py   (es_settings.cfg → temporal batocera.conf in /tmp)
            └── configgen          (writes emulator configs, launches game)
                    ├── batocera-resolution  (stub → kscreen-doctor)
                    ├── batocera-vulkan      (stub → vulkaninfo)
                    ├── hotkeygen            (stub, no-op)
                    └── batocera-mouse       (stub, no-op)
```

This repo can be cloned and used everywhere. Paths have been adapted to replace `/userdata` hierarchy. The `retrobox.sh` adapts paths if the directory is moved.

---

## Key changes vs upstream batocera-configgen

### Path remapping (`batoceraPaths.py`)

All `/userdata` paths are redirected to XDG-compliant locations:

| batocera | here |
|---|---|
| `/userdata` | `.` |
| `/userdata/system` | no equivalent |
| `/userdata/system/configs` | `./emuconfigs` |
| `/userdata/bios` | `./bios` |
| `/userdata/saves` | `./saves` |
| `/userdata/roms` | `./roms` |
| `/var/run/*` | `/tmp/batocera-run/*` |
| `/usr/share/batocera` | `./resources` |

### Stubs for batocera-only binaries

batocera ships several system-specific binaries that don't exist on a standard Linux install. Replacements:

- **`batocera-resolution`** — reimplemented in bash using `kscreen-doctor` (KDE Wayland)
- **`batocera-vulkan`** — reimplemented using `vulkaninfo`
- **`hotkeygen`** — no-op stub (hotkey context switching is batocera-daemon-specific)
- **`batocera-mouse`** — no-op stub

### ES settings sync

We reads emulator settings from `retrobox.conf` (key=value). EmulationStation on a standard install writes to `es_settings.cfg` (XML). A small Python script (`resources/emulatorlauncher/configgen/sync_settings.py`) translates between them before each game launch.

### RetroArch paths

RetroArch uses `~/.config/retroarch`. The configgen is adapted accordingly, including core options path, info files, and the `input_overlay` path for bezels.

### Controller handling: evdev → SDL

All `evdev/` references in `dolphinControllers.py` are replaced with `SDL/`, and hat input formatting is corrected for SDL. I have also improved handling of third-party "Pro Controller" gamepads.

### libretroConfig bezel fix

A missing call to `bezelsUtil.getBezelInfos()` in the `else` branch of `writeBezelConfig()` caused bezels to silently fail. Fixed.

### renderConfig None guard

`system.renderconfig` could be `None` when no `rendering-defaults.yml` is found. Added a fallback `or {}` to prevent `TypeError` on shader lookup.

### Hotkeys rewrite (`libretroControllers.py`)

The upstream hotkey writer used raw `.id` values and hardcoded `_btn` suffixes. Rewritten to use `getConfigValue()` and a type-aware helper (`_hotkey_save`) that emits `_axis` for analog triggers and `_btn` for buttons and hats.

The other emulators (with the exception of eden) don't use gamepad shortcuts and rely on AntiMicroX for basic things like exiting.

### Emulators of a well-known Nvidia Tegra X1 powered console (Eden, Ryujinx)

Generators adapted from a third-party batocera package. Paths converted to this environment standard, AppImage-specific HOME handling resolved.

---

## Setup

1. Clone this repo
2. Install EmulationStation (build from [batocera-emulationstation](https://github.com/batocera-linux/batocera-emulationstation)) and put the executable and its resources in `./emulationstation`.
2. Install [MangoHud](https://github.com/flightlessmango/Mangohud) from source and apply [batocera](https://github.com/batocera-linux/batocera.linux/tree/master/package/batocera/utils/mangohud) patches before building.
3. Install dependences:

**On Debian (and maybe Ubuntu):**

```bash
sudo apt-get install \
libfreeimage3 libsdl2-2.0-0 libsdl2-mixer-2.0-0 libvlc5 \
p7zip-full jq \
python3-pyudev python3-pip python3-venv python3-sdl2 \
python3-yaml python3-qrcode python3-pil python3-evdev \
libice6 libsm6 libxtst6 libxi6 inotify-tools antimicro
```

**On Fedora:**

```bash
# coming soon
```

**Python dependencies for use in `venv`:***

```bash
source /path/to/venv/bin/activate
pip install --no-user pyudev pysdl2 PyYAML lxml evdev requests qrcode[pil]
```

---

## Directory layout

```
.
├── retrobox.sh            # main executable
├── bios/                  # BIOS files
├── saves/                 # save states and SRAM
├── screenshots/
├── decorations/           # bezels
├── shaders/               # user shader overrides
├── roms                   # roms dir
└── resources/
    ├── emulatorlauncher/  # all configgen scripts
    ├── shaders/           # system shaders (slang/glsl packs)
    ├── datainit/
    │   └── decorations/   # default bezels
    └── configgen/
        └── data/          # gamesbuttonsdb.xml etc.
```

---

## License

This project is a derivative of [batocera-configgen](https://github.com/batocera-linux/batocera.linux/tree/master/package/batocera/core/batocera-configgen), part of the `batocera.linux` project which is licensed under the GPLv2 License.

All modifications are also released under GPLv2. See [LICENSE](LICENSE).

