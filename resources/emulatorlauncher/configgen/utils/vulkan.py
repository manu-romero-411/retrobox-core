from __future__ import annotations

from ctypes import CDLL
from ctypes.util import find_library
import glob
import logging
import subprocess
from pathlib import Path
from typing import Final

from configgen.retrobox_paths import SYSTEM_SCRIPTS, USERDATA

_logger: Final = logging.getLogger(__name__)

_BATOCERA_VULKAN: Final =  f"{SYSTEM_SCRIPTS}/batocera-vulkan"

def is_available() -> bool:
    """Checks if this system/GPU has Vulkan capabilities.
    TODO: Make a better check on systems with dual graphics. My main PC only has 1 GPU
    """
    # 1. Filtro rápido: ¿Está el loader en el sistema?
    lib_path = find_library("vulkan")
    if not lib_path:
        return False

    # 2. Comprobación real: ¿Se puede cargar y responde a la API básica?
    try:
        vulkan_lib = CDLL(lib_path)
        # vkCreateInstance es el punto de entrada obligatorio de cualquier app Vulkan
        if hasattr(vulkan_lib, "vkCreateInstance"):
            return True
    except Exception:
        pass

    # 3. Fallback estático: Buscar manifiestos ICD (Drivers de proveedores)
    # Usamos glob para evitar bucles anidados con os.listdir
    icd_patterns = [
        "/usr/share/vulkan/icd.d/*.json",
        "/etc/vulkan/icd.d/*.json",
        "/usr/local/share/vulkan/icd.d/*.json"
    ]
    
    for pattern in icd_patterns:
        if glob.glob(pattern):
            return True

    return False

def has_discrete_gpu() -> bool:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'hasDiscrete'], text=True).strip() == 'true'
    except subprocess.CalledProcessError:
        _logger.exception('Error checking for discrete GPU.')

    return False

def get_discrete_gpu_index() -> str | None:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'discreteIndex'], text=True).strip() or None
    except subprocess.CalledProcessError:
        _logger.exception('Error getting discrete GPU index')

    return None

def get_discrete_gpu_name() -> str | None:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'discreteName'], text=True).strip() or None
    except subprocess.CalledProcessError:
        _logger.exception('Error getting discrete GPU Name')

    return None

def get_default_gpu_name() -> str | None:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'defaultName'], text=True).strip() or None
    except subprocess.CalledProcessError:
        _logger.exception('Error getting default GPU Name')

    return None

def get_discrete_gpu_uuid() -> str | None:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'discreteUUID'], text=True).strip() or None
    except subprocess.CalledProcessError:
        _logger.exception('Error getting discrete GPU UUID')

    return None

def get_version() -> str:
    try:
        return subprocess.check_output([_BATOCERA_VULKAN, 'vulkanVersion'], text=True).strip()
    except subprocess.CalledProcessError:
        _logger.exception('Error checking for Vulkan version.')

    return ''
