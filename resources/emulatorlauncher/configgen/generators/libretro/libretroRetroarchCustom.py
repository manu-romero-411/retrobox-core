from __future__ import annotations

from ...retrobox_paths import BIOS, CHEATS, RECORDINGS, RESOURCES_DIR, SAVES, SCREENSHOTS, mkdir_if_not_exists, USERDATA
from ...settings.unixSettings import UnixSettings
from .libretroPaths import _RETROARCH_CONFIG, _RETROARCH_ROOT, RETROARCH_ASSETS, RETROARCH_CUSTOM, RETROARCH_SHADERS

def generate_retroarch_custom() -> None:
    # retroarchcustom.cfg
    mkdir_if_not_exists(RETROARCH_CUSTOM.parent)

    try:
        retroarch_settings = UnixSettings(RETROARCH_CUSTOM, separator=' ')
    except UnicodeError:
        RETROARCH_CUSTOM.unlink()
        retroarch_settings = UnixSettings(RETROARCH_CUSTOM, separator=' ')

    # Use Interface
    retroarch_settings.save('menu_driver',                       '"ozone"')
    retroarch_settings.save('content_show_favorites',            '"false"')
    retroarch_settings.save('content_show_images',               '"false"')
    retroarch_settings.save('content_show_music',                '"false"')
    retroarch_settings.save('content_show_video',                '"false"')
    retroarch_settings.save('content_show_history',              '"false"')
    retroarch_settings.save('content_show_playlists',            '"false"')
    retroarch_settings.save('content_show_add',                  '"false"')
    retroarch_settings.save('menu_show_load_core',               '"false"')
    retroarch_settings.save('menu_show_load_content',            '"false"')
    retroarch_settings.save('menu_show_online_updater',          '"true"')
    retroarch_settings.save('menu_show_core_updater',            '"true"')

    # Input
    retroarch_settings.save('input_autodetect_enable',           '"false"')
    retroarch_settings.save('input_joypad_driver',               '"udev"')
    retroarch_settings.save('input_player1_analog_dpad_mode',    '"1"')
    retroarch_settings.save('input_player2_analog_dpad_mode',    '"1"')
    retroarch_settings.save('input_player3_analog_dpad_mode',    '"1"')
    retroarch_settings.save('input_player4_analog_dpad_mode',    '"1"')
    retroarch_settings.save('input_enable_hotkey_btn',           '"nul"')
    retroarch_settings.save('input_enable_hotkey',               '"shift"')
    retroarch_settings.save('input_menu_toggle',                 '"f1"')
    retroarch_settings.save('input_exit_emulator',               '"escape"')

    # Video
    retroarch_settings.save('video_aspect_ratio_auto',           '"false"')
    retroarch_settings.save('video_gpu_screenshot',              '"true"')
    retroarch_settings.save('video_shader_enable',               '"false"')
    retroarch_settings.save('aspect_ratio_index',                '"22"')

    # Audio
    retroarch_settings.save('audio_volume',                       '"2.0"')

    # Settings
    retroarch_settings.save('global_core_options',               '"true"')
    retroarch_settings.save('config_save_on_exit',               '"false"')
    retroarch_settings.save('savestate_auto_save',               '"false"')
    retroarch_settings.save('savestate_auto_load',               '"false"')
    retroarch_settings.save('menu_swap_ok_cancel_buttons',       '"true"')

    # Accentuation
    retroarch_settings.save('rgui_extended_ascii',               '"true"')

    # Hide the welcome message in Retroarch
    retroarch_settings.save('rgui_show_start_screen',            '"false"')

    # Enable usage of OSD messages (Text messages not in badge)
    retroarch_settings.save('video_font_enable',                 '"true"')

    # Take a screenshot of the savestate
    retroarch_settings.save('savestate_thumbnail_enable',        '"true"')

    # Allow any RetroPad to control the menu (Only the player 1)
    retroarch_settings.save('all_users_control_menu',            '"false"')

    # Show badges in Retroarch cheevos list
    retroarch_settings.save('cheevos_badges_enable',             '"true"')

    # Disable builtin image viewer (done in ES, and prevents from loading pico-8 .png carts)
    retroarch_settings.save('builtin_imageviewer_enable',        '"false"')

    # Set fps counter interval (in frames)
    retroarch_settings.save('fps_update_interval',               '"30"')

    retroarch_settings.write()

def generate_rarch_custom_paths(retroarch_settings: UnixSettings) -> None:
    # Path Retroarch
    retroarch_settings.save('core_options_path',             f'"{_RETROARCH_CONFIG}/cores/retroarch-core-options.cfg"')
    retroarch_settings.save('assets_directory',              f'"{RETROARCH_ASSETS}"')
    retroarch_settings.save('screenshot_directory',          f'"{SCREENSHOTS}/"')
    retroarch_settings.save('recording_output_directory',    f'"{RECORDINGS}/"')
    retroarch_settings.save('savestate_directory',           f'"{SAVES}/"')
    retroarch_settings.save('savefile_directory',            f'"{SAVES}/"')
    retroarch_settings.save('extraction_directory',          f'"{_RETROARCH_ROOT}/extractions/"')
    retroarch_settings.save('cheat_database_path',           f'"{CHEATS}/cht/"')
    retroarch_settings.save('cheat_settings_path',           f'"{CHEATS}/saves/"')
    retroarch_settings.save('system_directory',              f'"{BIOS}/"')
    retroarch_settings.save('joypad_autoconfig_dir',         f'"{_RETROARCH_CONFIG}/autoconfig/"')
    retroarch_settings.save('video_shader_dir',              f'"{RETROARCH_SHADERS}/"')
    retroarch_settings.save('video_font_path',               '"/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf"')
    retroarch_settings.save('video_filter_dir',              f'"{_RETROARCH_ROOT}/filters/video"')
    retroarch_settings.save('audio_filter_dir',              f'"{_RETROARCH_ROOT}/filters/audio"')
