"""Core options of the libretro cores, driven by the feature YAML files.

A feature of ``libretro_<core>.yaml`` controls RetroArch core options when it
has one of these keys (the generator of es_features.cfg ignores them)::

    core_option: melonds_screen_layout       # the choice is written as it is
    core_options:                            # or each choice sets some options
      2x: {melonds_render_mode: opengl, melonds_opengl_resolution: "2"}

A game that leaves the feature unset (or on ``auto``) gets the core default:
the options the feature manages are removed from the core options file, so a
value picked for another game never leaks into this one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from runtime.paths import EMU_FEATURES_DIR

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from ...config import SystemConfig
    from ...settings.unixSettings import UnixSettings

_logger = logging.getLogger(__name__)

# the values a feature has when the user did not choose: the core default is used
_DEFAULT_VALUES = ("", "auto")
_CORE_OPTION_KEY = "core_option"
_CORE_OPTIONS_KEY = "core_options"


@dataclass(frozen=True)
class CoreFeature:
    """A feature that sets core options.

    Attributes:
        feature: The name of the feature (its key in the game configuration).
        option: The option that takes the chosen value as it is, if any.
        choices: The options each choice sets, when a choice sets several.
    """

    feature: str
    option: str | None = None
    choices: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @property
    def managed_options(self) -> set[str]:
        """Every option this feature may write."""
        options = {self.option} if self.option else set()
        for choice_options in self.choices.values():
            options.update(choice_options)
        return options

    def options_for(self, selected: str | None) -> dict[str, str]:
        """Return the options to write for the selected choice.

        Args:
            selected: The value of the feature in the game, None if unset.

        Returns:
            The options to write; empty when the core default must be used.
        """
        if selected is None or selected in _DEFAULT_VALUES:
            return {}
        if self.option:
            return {self.option: selected}
        return dict(self.choices.get(selected, {}))


def _iter_items(data: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """Yield every feature item of a YAML file."""
    for group in (data.get("groups") or {}).values():
        for items in (group.get("submenus") or {}).values():
            yield from items or []
        yield from group.get("items") or []


def parse_core_features(data: Mapping[str, Any]) -> list[CoreFeature]:
    """Collect the features of a YAML file that set core options."""
    features = []
    for item in _iter_items(data):
        name = str(item["value"])
        if option := item.get(_CORE_OPTION_KEY):
            features.append(CoreFeature(name, option=str(option)))
        elif choices := item.get(_CORE_OPTIONS_KEY):
            features.append(
                CoreFeature(
                    name,
                    choices={
                        str(choice): {str(key): str(value) for key, value in options.items()}
                        for choice, options in choices.items()
                    },
                )
            )
    return features


def _core_yaml_path(core: str, features_dir: Path) -> Path | None:
    """Find the YAML file of a core: the file name may use "-" where the core uses "_"."""
    for stem in (core, core.replace("_", "-")):
        candidate = features_dir / f"libretro_{stem}.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_core_features(core: str, features_dir: Path = EMU_FEATURES_DIR) -> list[CoreFeature]:
    """Load the core option features of a core, or an empty list if it has none."""
    path = _core_yaml_path(core, features_dir)
    if path is None:
        return []
    try:
        with path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return parse_core_features(data)
    except (OSError, yaml.YAMLError, KeyError, AttributeError, TypeError) as err:
        # best effort: a broken feature file must never prevent the game from starting
        _logger.error("Unable to read the core options of %s: %s", path, err)
        return []


def apply_core_features(
    core_settings: UnixSettings, config: SystemConfig, features: list[CoreFeature]
) -> None:
    """Write (or remove) the core options of the features for the current game.

    Args:
        core_settings: The core options file, updated in place.
        config: The configuration of the running game.
        features: The core option features of the core.
    """
    for feature in features:
        selected = config.get(feature.feature)
        wanted = feature.options_for(None if selected is config.MISSING else str(selected))
        for option in feature.managed_options - wanted.keys():
            core_settings.remove(option)
        for option, value in wanted.items():
            core_settings.save(option, f'"{value}"')
