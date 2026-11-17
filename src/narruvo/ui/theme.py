import os
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPixmap

STYLESHEET = """
QWidget { background: #141b1a; color: #e5eee9; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog { background: #141b1a; }
QFrame#sidebar { background: #192320; border-right: 1px solid #293630; }
QFrame#panel, QFrame#playback { background: #1d2925; border: 1px solid #304139; border-radius: 14px; }
QFrame#playback { background: #1b2722; }
QLabel { background: transparent; }
QWidget#playerGroup { background: transparent; }
QLabel#muted { color: #9eafa5; }
QLabel#eyebrow { color: #8cae9a; font-size: 11px; font-weight: 600; }
QLabel#title { font-size: 23px; font-weight: 600; }
QLabel#brand { font-size: 22px; font-weight: 600; }
QLabel#hero { font-size: 30px; font-weight: 600; }
QPushButton, QToolButton { background: #25362d; border: 1px solid #3b5143; border-radius: 8px; padding: 8px 13px; }
QPushButton:hover, QToolButton:hover { background: #344c3d; border-color: #6b947a; }
QPushButton:pressed, QToolButton:pressed { background: #46694f; }
QPushButton:checked { background: #345140; border-color: #739980; }
QPushButton:disabled, QToolButton:disabled { color: #6b7e72; background: #202b25; border-color: #2a3930; }
QPushButton#accent { background: #9cceae; color: #12291a; border: 0; font-weight: 600; }
QPushButton#accent:hover { background: #b3e1c2; }
QPushButton#accent:disabled { background: #3a5645; color: #849c8b; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #17211c; border: 1px solid #3b5143; border-radius: 7px; padding: 7px; selection-background-color: #45634f; }
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView { background: #1d2925; selection-background-color: #3b5b47; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { padding: 13px 10px; border-radius: 7px; margin: 3px 0; }
QListWidget::item:selected { background: #334d3b; }
QListWidget::item:hover { background: #263c2e; }
QPlainTextEdit { background: #18221e; border: 1px solid #304139; border-radius: 10px; padding: 14px; font-size: 15px; }
QScrollArea { background: #101613; border: 1px solid #304139; border-radius: 10px; }
QScrollBar:vertical { background: #17221b; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #496351; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSlider::groove:horizontal { background: #3b4d41; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #9cceae; border-radius: 2px; }
QSlider::handle:horizontal { background: #b2dcc1; width: 12px; margin: -5px 0; border-radius: 6px; }
QProgressBar { background: #17221b; border: 1px solid #3b5143; border-radius: 6px; text-align: center; min-height: 19px; }
QProgressBar::chunk { background: #527d5e; border-radius: 5px; }
QSplitter::handle { background: #25362d; width: 5px; }
QToolTip { background: #293e30; color: #e5eee9; border: 1px solid #698770; padding: 6px; }
QMenu { background: #203026; border: 1px solid #45634f; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #45634f; }
"""


def leaf_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64, size / 64)
    painter.setPen(QColor("#a8d5b8"))
    painter.setBrush(QColor("#9cceae"))
    shape = QPainterPath()
    shape.moveTo(17, 48)
    shape.cubicTo(2, 22, 34, 10, 54, 10)
    shape.cubicTo(57, 36, 37, 57, 17, 48)
    painter.drawPath(shape)
    painter.setPen(QColor("#234532"))
    painter.drawLine(12, 55, 43, 23)
    painter.end()
    return QIcon(pixmap)


def apply_theme(app) -> None:
    # The offscreen Qt plugin does not discover Windows fonts automatically.
    font_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("segoeui.ttf", "seguisb.ttf"):
        path = font_directory / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

