BG_TOP = "#000000"
BG_BOTTOM = "#000000"
CARD = "#111111"
BORDER = "#262626"
TEXT = "#FFFFFF"
MUTED = "#B4B4B4"
ACCENT = "#C6F24E"
ACCENT2 = "#C6F24E"
DANGER = "#E5484D"

QSS = """
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    outline: none;
}
QLabel { color: #FFFFFF; font-size: 13px; background: transparent; }
QLabel#muted { color: #B4B4B4; font-size: 11px; }
QLabel#hint { color: #949494; font-size: 11px; }
QLabel#brand { font-size: 15px; font-weight: 600; color: #FFFFFF; }
QLabel#brandTag { color: #949494; font-size: 11px; }
QLabel#fileName { font-size: 13px; font-weight: 500; color: #FFFFFF; }
QLabel#meta { color: #949494; font-size: 11px; }
QLabel#sectionTitle { color: #949494; font-size: 12px; padding: 2px 0 6px 0; }
QLabel#fieldLabel { color: #949494; font-size: 11px; }

QPushButton {
    border: none; outline: none; color: #FFFFFF;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    background: transparent;
}

QPushButton#primary {
    background: #FFFFFF; color: #000000;
    border-radius: 18px; padding: 0 18px;
    font-size: 13px; font-weight: 600;
}
QPushButton#primary:hover { background: #E6E6E6; }
QPushButton#primary:pressed { background: #CCCCCC; }
QPushButton#primary:disabled { background: #1A1A1A; color: #5C5C5C; }

QPushButton#ghost {
    background: transparent; color: #B4B4B4;
    border: 1px solid #262626; border-radius: 6px;
    padding: 5px 10px; font-size: 12px;
}
QPushButton#ghost:hover { color: #FFFFFF; border-color: #444444; }
QPushButton#ghost:pressed { background: #111111; }
QPushButton#ghost:disabled { color: #4A4A4A; border-color: #1A1A1A; }

QPushButton#textBtn {
    background: transparent; color: #B4B4B4;
    padding: 4px 6px; font-size: 12px; border-radius: 4px;
}
QPushButton#textBtn:hover { color: #FFFFFF; }
QPushButton#textBtn:pressed { color: #CCCCCC; }
QPushButton#textBtn:disabled { color: #454545; }

QPushButton#iconBtn {
    background: transparent; color: #949494;
    border-radius: 4px; font-size: 13px;
}
QPushButton#iconBtn:hover { color: #FFFFFF; background: #1A1A1A; }

QPushButton#closeBtn {
    background: transparent; color: #949494;
    border-radius: 4px; font-size: 13px;
}
QPushButton#closeBtn:hover { color: #FFFFFF; background: #2A2A2A; }

QPushButton#mini {
    background: transparent; color: #949494;
    border: 1px solid #262626; border-radius: 4px;
    font-size: 11px; padding: 0 6px;
}
QPushButton#mini:hover { color: #FFFFFF; border-color: #444444; }
QPushButton#mini:disabled { color: #454545; border-color: #1A1A1A; }

QPushButton#play {
    background: #000000; color: #FFFFFF;
    border: 1px solid #444444; border-radius: 23px;
}
QPushButton#play:hover { border-color: #FFFFFF; }

QPushButton#navBtn {
    text-align: left; padding: 7px 2px; border-radius: 0;
    color: #B4B4B4; font-size: 13px; background: transparent;
    border: none;
}
QPushButton#navBtn:hover { color: #FFFFFF; }
QPushButton#navBtn:checked { color: #FFFFFF; font-weight: 600; }

QLineEdit#timeEdit {
    background: transparent; border: none;
    border-bottom: 1px solid #333333; border-radius: 0;
    padding: 2px 0 3px 0; color: #FFFFFF;
    font-size: 13px; selection-background-color: #C6F24E;
    selection-color: #000000;
}
QLineEdit#timeEdit:focus { border-bottom: 1px solid #FFFFFF; }

QLineEdit#pathEdit {
    background: #111111; border: 1px solid #262626; border-radius: 4px;
    padding: 6px 8px; color: #FFFFFF; font-size: 12px;
}
QLineEdit#pathEdit:focus { border-color: #444444; }
QLineEdit#pathEdit:disabled { color: #5C5C5C; background: #0A0A0A; border-color: #1A1A1A; }

QCheckBox { color: #B4B4B4; font-size: 12px; spacing: 7px; }
QCheckBox#checkRow { color: #FFFFFF; font-size: 13px; spacing: 8px; }
QCheckBox::indicator {
    width: 14px; height: 14px; border-radius: 2px;
    border: 1px solid #444444; background: #000000;
}
QCheckBox::indicator:hover { border-color: #B4B4B4; }
QCheckBox::indicator:checked {
    background: #FFFFFF; border: 1px solid #FFFFFF; image: url("@CHECK@");
}
QCheckBox::indicator:checked:disabled { background: #444444; border-color: #444444; }
QCheckBox:disabled { color: #5C5C5C; }

QComboBox {
    background: #111111; border: 1px solid #262626; border-radius: 4px;
    padding: 4px 8px; color: #FFFFFF; font-size: 12px; min-width: 56px;
}
QComboBox:hover { border-color: #444444; }
QComboBox::drop-down { border: none; width: 14px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: #111111; border: 1px solid #262626; color: #FFFFFF;
    selection-background-color: #2A2A2A; selection-color: #FFFFFF;
    outline: none; padding: 2px;
}

QProgressBar {
    background: #1A1A1A; border: none; border-radius: 0;
    height: 4px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: #C6F24E; }

QFrame#sep { background: #1A1A1A; border: none; }

QToolTip {
    background: #111111; color: #FFFFFF; border: 1px solid #262626;
    padding: 4px 6px; border-radius: 0; font-size: 11px;
}
"""


def build_qss(check_icon: str = "") -> str:
    return QSS.replace("@CHECK@", check_icon.replace("\\", "/"))
