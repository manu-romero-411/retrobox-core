"""Edit an ini file in place, keeping everything a person wrote in it.

configparser can read retrobox.ini but would drop its comments, blank lines
and order when writing it back. IniDocument changes only the lines of the
keys it is told to set or remove, and keeps every other line as it was.

Names follow the rules of retrobox.paths: the sections ``core``, ``paths``
and ``environ`` match in any case (``[PATHS]`` is ``[paths]``), and so do the
keys of ``core`` and ``paths``; anything else matches exactly.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from retrobox.paths._base import _CASE_INSENSITIVE_SECTIONS, _KNOWN_SECTIONS

_SECTION_RE: Final = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
_KEY_RE: Final = re.compile(r"^(?P<key>[^\s#;=:][^=:]*?)\s*[=:]\s*(?P<value>.*)$")
_COMMENT_PREFIXES: Final = ("#", ";")


def _section_id(name: str) -> str:
    name = name.strip()
    return name.lower() if name.lower() in _KNOWN_SECTIONS else name


def _key_id(section: str, key: str) -> str:
    return key.lower() if section in _CASE_INSENSITIVE_SECTIONS else key


@dataclass(slots=True)
class _Entry:
    """A ``key = value`` line (plus its continuation lines)."""

    section: str
    key: str
    value: str
    first: int  # index of its line
    count: int = 1  # lines it spans


@dataclass(slots=True)
class IniDocument:
    """The lines of an ini file, with the positions of its sections and keys."""

    lines: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ io
    @classmethod
    def read(cls, path: Path) -> IniDocument:
        """The document of ``path`` (empty if it doesn't exist)."""
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls()
        return cls(text.splitlines())

    def text(self) -> str:
        """The whole file."""
        return "\n".join(self.lines) + "\n" if self.lines else ""

    def write(self, path: Path) -> None:
        """Save to ``path`` atomically (a crash never leaves half a file)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.text())
            if path.exists():
                os.chmod(tmp, path.stat().st_mode & 0o7777)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # --------------------------------------------------------------- parse
    def _scan(self) -> tuple[dict[str, tuple[int, int]], list[_Entry]]:
        """Sections ({id: (header line, last line)}) and entries, in order."""
        sections: dict[str, tuple[int, int]] = {}
        entries: list[_Entry] = []
        current: str | None = None
        last_entry: _Entry | None = None
        for index, line in enumerate(self.lines):
            stripped = line.strip()
            header = _SECTION_RE.match(line)
            if header:
                current = _section_id(header.group("name"))
                start = sections.get(current, (index, index))[0]
                sections[current] = (start, index)
                last_entry = None
                continue
            if current is not None:
                sections[current] = (sections[current][0], index)
            if not stripped or stripped.startswith(_COMMENT_PREFIXES):
                last_entry = None
                continue
            if line[:1].isspace() and last_entry is not None:
                last_entry.count += 1  # continuation of a multi-line value
                continue
            match = _KEY_RE.match(line)
            if match is None or current is None:
                last_entry = None
                continue
            last_entry = _Entry(
                current, _key_id(current, match.group("key").strip()),
                match.group("value").strip(), index,
            )
            entries.append(last_entry)
        return sections, entries

    def _entries(self, section: str, key: str) -> list[_Entry]:
        section = _section_id(section)
        key = _key_id(section, key)
        return [e for e in self._scan()[1] if e.section == section and e.key == key]

    # ---------------------------------------------------------------- read
    def get(self, section: str, key: str) -> str | None:
        """The value of ``key`` (the last one, as configparser), or None."""
        entries = self._entries(section, key)
        return entries[-1].value if entries else None

    def items(self, section: str) -> dict[str, str]:
        """Every key of ``section`` with its value."""
        section = _section_id(section)
        return {e.key: e.value for e in self._scan()[1] if e.section == section}

    # --------------------------------------------------------------- write
    def set(self, section: str, key: str, value: str) -> None:
        """Set ``key`` to ``value`` (a single line), adding it if needed."""
        if "\n" in value or "\r" in value:
            raise ValueError(f"{section}.{key}: values must fit in one line")
        section_id = _section_id(section)
        key_id = _key_id(section_id, key)
        line = f"{key_id} = {value}" if value else f"{key_id} ="
        entries = self._entries(section_id, key_id)
        if entries:
            for extra in reversed(entries[1:]):  # duplicates would break configparser
                del self.lines[extra.first:extra.first + extra.count]
            first = entries[0]
            self.lines[first.first:first.first + first.count] = [line]
            return

        sections = self._scan()[0]
        if section_id in sections:
            end = sections[section_id][1]
            while end > sections[section_id][0] and not self.lines[end].strip():
                end -= 1  # keep the blank line(s) before the next section
            self.lines.insert(end + 1, line)
            return
        if self.lines and self.lines[-1].strip():
            self.lines.append("")
        self.lines.extend([f"[{section_id}]", line])

    def remove(self, section: str, key: str) -> None:
        """Remove ``key``; then its section too, if nothing but its header is left."""
        section_id = _section_id(section)
        for entry in reversed(self._entries(section_id, key)):
            del self.lines[entry.first:entry.first + entry.count]
        sections = self._scan()[0]
        if section_id not in sections:
            return
        start, end = sections[section_id]
        if all(not line.strip() for line in self.lines[start + 1:end + 1]):
            del self.lines[start:end + 1]
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
