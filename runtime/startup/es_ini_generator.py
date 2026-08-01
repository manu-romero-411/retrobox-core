"""module for handling emulationstation.ini generation
"""
import logging
from pathlib import Path

from configgen.generators.libretro.libretroPaths import (
    _RETROARCH_AUDIO_FILTERS,
    _RETROARCH_VIDEO_FILTERS
)

from runtime.retrobox_paths import (
    _DECORATIONS_DIR,
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    _SHADERS_DIR,
    ES_INI_CFG,
    ES_INI_TMP,
    LOGS,
    SAVES,
    SCREENSHOTS,
    USERDATA
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

_logger = logging.getLogger(__name__)


INI_CONTENT = f"""
# ROOT AND LOGS
root={USERDATA}
log={LOGS}

# SAVES
saves={SAVES}

# SCREENSHOTS
screenshots={SCREENSHOTS}

# THEMES (GET MORE AT THEME DOWNLOADER)
themes={USERDATA}/frontend/themes

# BACKGROUND MUSIC FOR MENUS
music={USERDATA}/frontend/music

# DECORATIONS/BEZELS
decorations={_DECORATIONS_DIR}

# RETROARCH SHADERS
shaders={_SHADERS_DIR}/configs

# RETROARCH VIDEO FILTERS
videofilters={_RETROARCH_VIDEO_FILTERS}

# RETROARCH AUDIO FILTERS
audiofilters={_RETROARCH_AUDIO_FILTERS}

# RETROACHIEVEMENT SOUNDS
retroachievementsounds={USERDATA}/frontend/retroachievements-sounds

# PAD-TO-KEYBOARD (gamepadly) MAPPINGS
system.padtokey={_GAMEPADLY_PROFILES}
padtokey={_GAMEPADLY_USER_PROFILES}

# TIMEZONES
timezones=/usr/share/zoneinfo
"""

def generate_emulationstation_ini(target: Path = ES_INI_TMP):
    """
    Generates emulationstation.ini for directory mappings to some retrobox resources.
    """

    _logger.info("Begin generating %s", target)

    if target.exists():
        target.unlink()

    try:
        target.write_text(INI_CONTENT, encoding="utf-8")
        _logger.info("Successfully generated: %s", target)
    except OSError as e:
        _logger.error("Couldn't write %s: %s", target, e)
        raise

    if target != ES_INI_CFG:
        try:
            ES_INI_CFG.symlink_to(ES_INI_TMP)
            _logger.info("Successfully linked: %s", ES_INI_CFG)
        except FileNotFoundError:
            _logger.error(
                "Can't create symlink in %s",
                ES_INI_CFG.parent
            )
            raise
        except OSError as e:
            _logger.error("Failed to link %s -> %s: %s", ES_INI_CFG, ES_INI_TMP, e)
            raise
    _logger.info("=========")
