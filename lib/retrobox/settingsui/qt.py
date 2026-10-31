"""The Qt binding: PySide6 if installed, else PyQt6.

Both expose the same Qt 6 API for what this UI uses; only the signal class
is named differently. Everything else imports Qt from here.

Raises:
    ImportError: If neither binding is installed.
"""

# pylint: disable=unused-import,no-name-in-module,import-error

from __future__ import annotations

from typing import Final

try:
    from PySide6.QtCore import QObject, QSize, Qt, QTimer
    from PySide6.QtCore import Signal
    from PySide6.QtGui import (
        QFont,
        QFontMetrics,
        QGuiApplication,
        QIcon,
        QKeySequence,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    BINDING: Final = "PySide6"
except ImportError:
    from PyQt6.QtCore import QObject, QSize, Qt, QTimer  # type: ignore[no-redef]
    from PyQt6.QtCore import pyqtSignal as Signal  # type: ignore[no-redef]
    from PyQt6.QtGui import (  # type: ignore[no-redef]
        QFont,
        QFontMetrics,
        QGuiApplication,
        QIcon,
        QKeySequence,
        QShortcut,
    )
    from PyQt6.QtWidgets import (  # type: ignore[no-redef]
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    BINDING = "PyQt6"  # type: ignore[misc]
