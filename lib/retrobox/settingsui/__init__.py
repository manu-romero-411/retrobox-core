"""Qt window to edit the user's retrobox.ini (``retrobox --settings``).

All the logic is in ``retrobox.settings`` (what can be set, the values, the
file); this package only shows it:

* ``qt``: the binding, PySide6 or PyQt6.
* ``i18n``: the texts, from ``i18n/<language>.yaml``.
* ``editors``: the row of each setting, and the table of free variables.
* ``window``: the pages, the navigation and the buttons.
* ``launch``: starting Retrobox after saving.
"""
