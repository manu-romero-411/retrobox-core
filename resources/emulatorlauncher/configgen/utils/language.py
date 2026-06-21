
import locale
import os

def _detect_language() -> str:
    """
    Detecta el idioma del sistema sin depender de scripts de Batocera.
    Orden de prioridad: LANGUAGE > LC_ALL > LANG > locale.getlocale() > 'en_US'
    Devuelve una cadena tipo 'es_ES', 'en_US', etc.
    """
    for var in ("LANGUAGE", "LC_ALL", "LANG"):
        val = os.environ.get(var, "").strip()
        if val and val != "C" and val != "POSIX":
            # LANGUAGE puede ser "es_ES:en_US:…" — tomamos el primero
            lang = val.split(":")[0]
            # Quitamos sufijo de encoding si lo trae (.UTF-8, etc.)
            lang = lang.split(".")[0]
            if len(lang) >= 2:
                return lang
    # Fallback: locale del sistema
    try:
        code, _ = locale.getlocale()
        if code:
            return code
    except Exception:
        pass
    return "en_US"