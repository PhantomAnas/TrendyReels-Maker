"""iOS-flavoured dark glass theme: translucent cards over a wallpaper, pill buttons."""

ACCENT = "#0a84ff"      # iOS blue
GREEN = "#30d158"
RED = "#ff453a"
ORANGE = "#ff9f0a"
TEXT = "#f5f5f7"
MUTED = "rgba(245,245,247,0.62)"
FAINT = "rgba(245,245,247,0.38)"
GLASS = "rgba(255,255,255,0.09)"
GLASS_STRONG = "rgba(255,255,255,0.14)"
GLASS_BORDER = "rgba(255,255,255,0.16)"
FIELD = "rgba(0,0,0,0.28)"
FIELD_BORDER = "rgba(255,255,255,0.10)"

FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, SF Pro Text, Helvetica Neue, Arial"

STYLESHEET = f"""
* {{ font-family: {FONT_FAMILY}; }}
QWidget {{ color: {TEXT}; font-size: 13px; background: transparent; }}
QMainWindow, QDialog {{ background: #0e0f16; }}
QToolTip {{ background: #1c1d26; color: {TEXT}; border: 1px solid {GLASS_BORDER}; padding: 6px 8px; border-radius: 8px; }}

/* Glass cards */
QFrame#Card {{
    background: {GLASS};
    border: 1px solid {GLASS_BORDER};
    border-radius: 22px;
}}
QLabel#CardTitle {{ font-size: 15px; font-weight: 600; letter-spacing: 0.2px; }}
QLabel#Hint {{ color: {MUTED}; font-size: 12px; }}
QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
QLabel#Big {{ font-size: 24px; font-weight: 700; }}
QLabel#Title {{ font-size: 26px; font-weight: 700; letter-spacing: -0.3px; }}
QLabel#Warn {{ color: {ORANGE}; font-size: 12px; }}

/* Pill buttons */
QPushButton {{
    background: {GLASS_STRONG};
    border: 1px solid {GLASS_BORDER};
    border-radius: 19px;
    padding: 8px 18px;
    min-height: 22px;
    font-weight: 600;
}}
QPushButton:hover {{ background: rgba(255,255,255,0.22); }}
QPushButton:pressed {{ background: rgba(255,255,255,0.30); }}
QPushButton:disabled {{ color: {FAINT}; background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.08); }}
QPushButton#Primary {{ background: {ACCENT}; border-color: rgba(255,255,255,0.25); color: white; }}
QPushButton#Primary:hover {{ background: #2f96ff; }}
QPushButton#Primary:pressed {{ background: #0870d8; }}
QPushButton#Primary:disabled {{ background: rgba(10,132,255,0.35); color: rgba(255,255,255,0.55); }}
QPushButton#Go {{ background: {GREEN}; border-color: rgba(255,255,255,0.25); color: #06230f; font-size: 15px; padding: 12px 28px; border-radius: 24px; }}
QPushButton#Go:hover {{ background: #4ade80; }}
QPushButton#Go:disabled {{ background: rgba(48,209,88,0.30); color: rgba(255,255,255,0.5); }}
QPushButton#Danger {{ background: rgba(255,69,58,0.85); border-color: rgba(255,255,255,0.22); color: white; }}
QPushButton#Danger:hover {{ background: {RED}; }}
QPushButton#Danger:disabled {{ background: rgba(255,69,58,0.25); color: rgba(255,255,255,0.45); }}
QPushButton#Round {{ border-radius: 18px; padding: 0; min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px; }}
QPushButton#Seg {{ border-radius: 15px; padding: 5px 14px; min-height: 18px; font-weight: 500; background: transparent; border: none; }}
QPushButton#Seg:checked {{ background: rgba(255,255,255,0.20); font-weight: 600; }}
QFrame#SegGroup {{ background: rgba(0,0,0,0.25); border: 1px solid {FIELD_BORDER}; border-radius: 18px; }}
QPushButton#Swatch {{ border-radius: 12px; padding: 4px 12px; min-height: 18px; font-weight: 500; }}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit#Editor {{
    background: {FIELD};
    border: 1px solid {FIELD_BORDER};
    border-radius: 12px;
    padding: 7px 12px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit#Editor {{ font-size: 13px; color: {TEXT}; font-family: {FONT_FAMILY}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit#Editor:focus {{ border: 1px solid {ACCENT}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent;
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: #1b1c26; border: 1px solid {GLASS_BORDER}; border-radius: 10px;
    selection-background-color: {ACCENT}; padding: 4px; outline: none;
}}

/* Sliders */
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.18); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: white; width: 18px; height: 18px; margin: -7px 0; border-radius: 9px;
    border: 1px solid rgba(0,0,0,0.25);
}}

/* iOS style switches (QCheckBox) */
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 40px; height: 22px; border-radius: 11px; background: rgba(120,120,128,0.45); }}
QCheckBox::indicator:checked {{ background: {GREEN}; }}
QCheckBox::indicator:disabled {{ background: rgba(120,120,128,0.2); }}

/* Lists */
QListWidget {{
    background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: 16px; padding: 8px;
    outline: none;
}}
QListWidget::item {{ border-radius: 10px; padding: 6px; color: {MUTED}; }}
QListWidget::item:selected {{ background: rgba(10,132,255,0.35); color: white; }}
QListWidget::item:hover {{ background: rgba(255,255,255,0.08); }}

/* Progress */
QProgressBar {{ background: rgba(255,255,255,0.12); border: none; border-radius: 5px; height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {GREEN}; border-radius: 5px; }}

/* Log */
QPlainTextEdit {{
    background: rgba(0,0,0,0.35); border: 1px solid {FIELD_BORDER}; border-radius: 14px; padding: 8px;
    font-family: Cascadia Mono, Consolas, monospace; font-size: 12px; color: {MUTED};
}}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.25); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.4); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.25); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QMenu {{ background: #1b1c26; border: 1px solid {GLASS_BORDER}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 8px; }}
QMenu::item:selected {{ background: rgba(255,255,255,0.12); }}
QMessageBox {{ background: #15161f; }}
QMessageBox QLabel {{ font-size: 13px; }}
"""
