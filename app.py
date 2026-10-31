from __future__ import annotations

import ctypes
import datetime
import gc
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, Property, QPropertyAnimation, QRect, QRectF, QSize,
    Qt, QThread, QTimer, QUrl, Signal,
)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QMenu, QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from fastcut import DEFAULT_SETTINGS, defaults, media, theme
from fastcut.clipmodel import Clip
from fastcut.settings_dialog import CloseDialog, SettingsDialog
from fastcut.timeline import Timeline
from fastcut.widgets import (
    DropZone, ElidedLabel, Orb, Panel, Toast, VideoView, fmt_ms, fmt_size, media_icon,
)

APP_NAME = "Fastcut"
EXPANDED_W, EXPANDED_H = 468, 648
ORB_SIZE = 84
ORB_SIZES = {"s": 68, "m": 84, "l": 100}
MARGIN = 16
SINGLETON = "fastcut-single-instance-v1"
if getattr(sys, "frozen", False):
    APP_FILE = Path(sys.executable).resolve()
else:
    APP_FILE = Path(__file__).resolve()
APP_DIR = APP_FILE.parent
LOG_DIR = APP_DIR / "logs"
SETTINGS_FILE = APP_DIR / "settings.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "Fastcut"


def autostart_command() -> str:
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    if quiet.exists():
        exe = quiet
    return f'"{exe}" "{APP_FILE}"'


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
        return True
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def set_log_dir(path: str) -> None:
    global LOG_DIR
    LOG_DIR = Path(path) if path else APP_DIR / "logs"


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged = dict(DEFAULT_SETTINGS)
            merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
            return merged
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except OSError:
        pass


def apply_decoder_env(mode: str) -> None:

    if mode == "hw":
        os.environ["QT_FFMPEG_DECODING_HW_DEVICE_TYPES"] = "d3d11,dxva2"
    elif mode == "sw":
        os.environ["QT_FFMPEG_DECODING_HW_DEVICE_TYPES"] = ""


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _win32_api():
    kernel32 = ctypes.WinDLL("kernel32.dll")
    psapi = ctypes.WinDLL("psapi.dll")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
    psapi.EmptyWorkingSet.restype = ctypes.c_int
    return kernel32, psapi


def log_exception(exc_type, exc, tb) -> None:

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_DIR / "error.log", "a", encoding="utf-8") as fh:
            fh.write(f"\n[{stamp}]\n")
            fh.write("".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:
        pass


def working_set_mb() -> float:
    try:
        kernel32, psapi = _win32_api()
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return pmc.WorkingSetSize / 1048576.0
    except Exception:
        pass
    return 0.0


def trim_memory() -> None:

    gc.collect()


def safe_dir(*candidates: str | None) -> str:

    for cand in candidates:
        if not cand:
            continue
        try:
            if os.path.isdir(cand):
                os.stat(cand)
                return cand
        except OSError:
            continue
    for fallback in (os.path.expanduser("~"), os.environ.get("USERPROFILE", ""),
                     os.environ.get("PUBLIC", ""), os.path.expanduser("~")):
        try:
            if fallback and os.path.isdir(fallback):
                return fallback
        except OSError:
            continue
    return os.getcwd()


def parse_time(text: str) -> int | None:
    raw = text.strip().replace("：", ":").replace("，", ".")
    if not raw:
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 1:
            sec = float(parts[0])
        elif len(parts) == 2:
            sec = int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        else:
            return None
    except ValueError:
        return None
    return int(round(max(0.0, sec) * 1000))


class Task(QThread):
    ok = Signal(object)
    err = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.ok.emit(self._fn())
        except Exception as exc:
            self.err.emit(str(exc))


class ProgressTask(QThread):
    progress = Signal(int)
    ok = Signal(object)
    err = Signal(str)
    canceled = Signal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def should_cancel(self) -> bool:
        return self._cancel

    def run(self):
        try:
            result = self._fn(self.progress.emit, self.should_cancel)
            if self._cancel:
                self.canceled.emit()
            else:
                self.ok.emit(result)
        except Exception as exc:
            self.err.emit(str(exc))


class MorphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._start_rect = QRect()
        self._end_rect = QRect()
        self._start_radius = 0.0
        self._end_radius = 0.0

    def setRange(self, start_rect, end_rect, start_radius, end_radius):
        self._start_rect = start_rect
        self._end_rect = end_rect
        self._start_radius = start_radius
        self._end_radius = end_radius

    def getProgress(self):
        return self._progress

    def setProgress(self, v):
        self._progress = v
        x = self._start_rect.x() + (self._end_rect.x() - self._start_rect.x()) * v
        y = self._start_rect.y() + (self._end_rect.y() - self._start_rect.y()) * v
        w = self._start_rect.width() + (self._end_rect.width() - self._start_rect.width()) * v
        h = self._start_rect.height() + (self._end_rect.height() - self._start_rect.height()) * v
        self.setGeometry(int(round(x)), int(round(y)), int(round(w)), int(round(h)))
        self.update()

    progress = Property(float, getProgress, setProgress)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._start_radius + (self._end_radius - self._start_radius) * self._progress
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, QColor("#000000"))
        p.setPen(QPen(QColor("#262626"), 1.0))
        p.drawPath(path)


class HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self._press = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, event):
        self._press = None


class FastcutWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setWindowTitle("Fastcut 快剪")
        self.setWindowIcon(self._make_icon())
        check_png = Path(__file__).resolve().parent / "assets" / "check12.png"
        self.setStyleSheet(theme.build_qss(str(check_png) if check_png.exists() else ""))

        self.expanded = False
        self.src: str | None = None
        self.probe_data: dict | None = None
        self.duration_ms = 0
        self.clips: list[Clip] = []
        self.sel = 0
        self.cur = -1
        self._history: list[list[tuple[int, int]]] = []
        self._redo: list[list[tuple[int, int]]] = []
        self.settings = load_settings()
        self.fps = 30.0
        self._tray: QSystemTrayIcon | None = None
        self._closing = False
        self._quitting = False
        self._tray_hint_shown = False
        self._sprite_path = ""
        self.proxy_path: str | None = None
        self.loaded = False
        self._proxying = False
        self._released = False
        self._resume_pos = 0
        self._worker = None
        self._export_task = None
        self._pending_path: str | None = None


        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.video_item = QGraphicsVideoItem()
        self.player.setVideoOutput(self.video_item)
        self.player.positionChanged.connect(self._on_position)
        self.player.errorOccurred.connect(self._on_player_error)
        self.player.playbackStateChanged.connect(self._on_playback_state)

        self._loop = QTimer(self)
        self._loop.setInterval(33)
        self._loop.timeout.connect(self._enforce_loop)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.orb = Orb()
        self.orb.set_diameter(self._orb_size())
        self.orb.clicked.connect(self.expand)
        self.orb.contextRequested.connect(self._orb_menu)
        root.addWidget(self.orb)

        self.panel = self._build_panel()
        self.panel.installEventFilter(self)
        root.addWidget(self.panel)
        self.panel.hide()

        self._mem_timer = QTimer(self)
        self._mem_timer.setInterval(3000)
        self._mem_timer.timeout.connect(self._update_mem)
        self._mem_timer.start()

        media.set_cache_dir(self.settings.get("cache_dir", ""))
        set_log_dir(self.settings.get("log_dir", ""))
        if self.settings.get("autostart"):
            set_autostart(True)
        media.cleanup_temp()
        self._build_tray()
        self._apply_geometry()
        self._refresh_actions()
        self._update_mem()


    def _make_icon(self) -> QIcon:
        ico = Path(__file__).resolve().parent / "assets" / "icon.ico"
        if ico.exists():
            return QIcon(str(ico))
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor("#7350F0"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 60, 60)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(pm.rect(), Qt.AlignCenter, "✂")
        p.end()
        return QIcon(pm)

    def _build_panel(self) -> Panel:
        panel = Panel()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = HeaderBar(panel)
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 10, 0)
        h.setSpacing(8)
        title = QLabel("Fastcut")
        title.setObjectName("brand")
        self.lbl_mem = QLabel("")
        self.lbl_mem.setObjectName("hint")
        btn_min = QPushButton("—")
        btn_min.setObjectName("iconBtn")
        btn_min.setFixedSize(26, 26)
        btn_min.setCursor(Qt.PointingHandCursor)
        btn_min.setToolTip("收起到悬浮球")
        btn_min.clicked.connect(self.collapse)
        btn_settings = QPushButton("⚙")
        btn_settings.setObjectName("iconBtn")
        btn_settings.setFixedSize(26, 26)
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.setToolTip("设置")
        btn_settings.clicked.connect(self.open_settings)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("closeBtn")
        btn_close.setFixedSize(26, 26)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("关闭（可在设置里改为隐藏到托盘）")
        btn_close.clicked.connect(self._request_close)

        h.addWidget(title)
        h.addStretch(1)
        h.addWidget(self.lbl_mem)
        h.addSpacing(4)
        h.addWidget(btn_settings)
        h.addWidget(btn_min)
        h.addWidget(btn_close)
        lay.addWidget(header)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 2, 16, 14)
        bl.setSpacing(0)

        self.stack = QStackedWidget()
        self.drop = DropZone()
        self.drop.clicked.connect(self.pick_file)
        self.editor = self._build_editor()
        self.stack.addWidget(self.drop)
        self.stack.addWidget(self.editor)
        bl.addWidget(self.stack, 1)
        lay.addWidget(body, 1)

        self.overlay = self._build_overlay(panel)
        self.toast = Toast(panel, reposition=self._layout_overlays)
        return panel

    def _build_editor(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(8)

        stage = QFrame()
        stage.setFixedHeight(232)
        stage.setStyleSheet("QFrame{background:#000000; border:1px solid #1A1A1A;}")
        grid = QGridLayout(stage)
        grid.setContentsMargins(0, 0, 0, 0)
        self.view = VideoView(self.video_item)
        self.view.setAcceptDrops(False)
        self.view.viewport().setAcceptDrops(False)
        grid.addWidget(self.view, 0, 0)

        time_wrap = QWidget()
        time_wrap.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        tw = QVBoxLayout(time_wrap)
        tw.setContentsMargins(9, 9, 9, 9)
        tw.addStretch(1)
        self.lbl_stage_time = QLabel("00:00 / 00:00")
        self.lbl_stage_time.setStyleSheet(
            "color:#B4B4B4; font-size:11px;"
            "background:rgba(0,0,0,0.72); border:1px solid #262626;"
            "border-radius:2px; padding:1px 6px;"
        )
        tw.addWidget(self.lbl_stage_time, 0, Qt.AlignRight)
        grid.addWidget(time_wrap, 0, 0)

        self.btn_play = QPushButton()
        self.btn_play.setObjectName("play")
        self.btn_play.setIcon(QIcon(media_icon("play")))
        self.btn_play.setIconSize(QSize(18, 18))
        self.btn_play.setFixedSize(46, 46)
        self.btn_play.setStyleSheet(
            "QPushButton{background:rgba(0,0,0,0.72);"
            " border:1px solid #444444; border-radius:23px;}"
            "QPushButton:hover{border-color:#FFFFFF;}"
        )
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setToolTip("播放 / 暂停 (空格)")
        self.btn_play.clicked.connect(self.toggle_play)
        grid.addWidget(self.btn_play, 0, 0, Qt.AlignCenter)
        v.addWidget(stage)

        row_name = QHBoxLayout()
        row_name.setSpacing(8)
        self.lbl_name = ElidedLabel("未选择文件")
        self.lbl_name.setObjectName("fileName")
        self.lbl_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_name.setMinimumWidth(70)
        self.btn_reset = QPushButton("还原")
        self.btn_reset.setObjectName("textBtn")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setToolTip("恢复成完整视频，清空所有分割和删除")
        self.btn_reset.clicked.connect(self.restore_all)
        self.btn_open = QPushButton("更换")
        self.btn_open.setObjectName("textBtn")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setToolTip("换一个视频文件")
        self.btn_open.clicked.connect(self.pick_file)
        row_name.addWidget(self.lbl_name, 1)
        row_name.addWidget(self.btn_reset)
        row_name.addWidget(self.btn_open)
        v.addLayout(row_name)

        row_meta = QHBoxLayout()
        row_meta.setSpacing(8)
        self.lbl_meta = QLabel("")
        self.lbl_meta.setObjectName("meta")
        self.lbl_proxy = QLabel("")
        self.lbl_proxy.setObjectName("meta")
        self.lbl_seg = QLabel("")
        self.lbl_seg.setObjectName("meta")
        row_meta.addWidget(self.lbl_meta, 1)
        row_meta.addWidget(self.lbl_seg)
        row_meta.addWidget(self.lbl_proxy)
        v.addLayout(row_meta)

        self.timeline = Timeline()
        self.timeline.setToolTip("单击片段选中 · 拖两端白色手柄调整 · 双击分割")
        self.timeline.seekRequested.connect(self.seek_to)
        self.timeline.clipSelected.connect(self._on_clip_selected)
        self.timeline.moveRequested.connect(self._on_move)
        self.timeline.trimRequested.connect(self._on_trim)
        self.timeline.splitRequested.connect(self.split_at)
        self.timeline.editStarted.connect(self._push_history)
        v.addWidget(self.timeline)

        times = QHBoxLayout()
        times.setSpacing(6)
        lbl_in = QLabel("起点")
        lbl_in.setObjectName("muted")
        self.ed_in = QLineEdit("00:00.00")
        self.ed_in.setObjectName("timeEdit")
        self.ed_in.setFixedWidth(76)
        lbl_out = QLabel("终点")
        lbl_out.setObjectName("muted")
        self.ed_out = QLineEdit("00:00.00")
        self.ed_out.setObjectName("timeEdit")
        self.ed_out.setFixedWidth(76)
        lbl_len = QLabel("时长")
        lbl_len.setObjectName("muted")
        self.lbl_len = QLabel("00:00.00")
        self.lbl_len.setStyleSheet("color:#FFFFFF; font-size:13px; font-weight:500;")
        self.ed_in.editingFinished.connect(self._on_edit_in)
        self.ed_out.editingFinished.connect(self._on_edit_out)
        times.addWidget(lbl_in)
        times.addWidget(self.ed_in)
        times.addSpacing(4)
        times.addWidget(lbl_out)
        times.addWidget(self.ed_out)
        times.addStretch(1)
        times.addWidget(lbl_len)
        times.addWidget(self.lbl_len)
        v.addLayout(times)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.btn_split = QPushButton("✂ 分割")
        self.btn_split.setToolTip("在播放位置把当前段切成两段（S 键 / 双击时间轴）")
        self.btn_del = QPushButton("删除")
        self.btn_del.setToolTip("删除选中片段，原位置留空，其他片段可以拖进来（Delete）")
        self.btn_ripple = QPushButton("波纹删除")
        self.btn_ripple.setToolTip("删除选中片段，后面的片段整体前移填补空隙（Shift+Delete）")
        self.btn_closegap = QPushButton("闭合空隙")
        self.btn_closegap.setToolTip("把所有空白位置去掉，片段依次靠拢")
        self.btn_undo = QPushButton("撤销")
        self.btn_undo.setToolTip("撤销上一次分割 / 删除 / 拖动（Ctrl+Z）")
        self.btn_redo = QPushButton("重做")
        self.btn_redo.setToolTip("重做被撤销的操作（Ctrl+Y）")
        for b in (self.btn_split, self.btn_del, self.btn_ripple,
                  self.btn_closegap, self.btn_undo, self.btn_redo):
            b.setObjectName("textBtn")
            b.setCursor(Qt.PointingHandCursor)
            tools.addWidget(b)
        tools.addStretch(1)
        self.btn_split.clicked.connect(self.split_at_playhead)
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_ripple.clicked.connect(self.ripple_delete)
        self.btn_closegap.clicked.connect(self.close_gaps)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        v.addLayout(tools)

        opts = QHBoxLayout()
        opts.setSpacing(8)
        self.chk_accurate = QCheckBox("精确剪辑")
        self.chk_accurate.setChecked(True)
        self.chk_accurate.setToolTip(
            "开启：逐帧精确切割（重新编码，画质几乎无损）\n"
            "关闭：直接复制流，秒级完成，但起点会对齐到最近的关键帧"
        )
        self.cmb_volume = QComboBox()
        for label, val in (("静音", 0.0), ("30%", 0.3), ("60%", 0.6), ("100%", 1.0)):
            self.cmb_volume.addItem(label, val)
        self.cmb_volume.setCurrentIndex(3)
        self.cmb_volume.setToolTip("音量：预览与导出同步生效")
        self.cmb_volume.currentIndexChanged.connect(self._on_volume_changed)

        self.cmb_speed = QComboBox()
        for label, val in (("0.5×", 0.5), ("0.75×", 0.75), ("1×", 1.0),
                           ("1.25×", 1.25), ("1.5×", 1.5), ("2×", 2.0)):
            self.cmb_speed.addItem(label, val)
        self.cmb_speed.setCurrentIndex(2)
        self.cmb_speed.currentIndexChanged.connect(self._on_speed_changed)

        self.chk_mirror = QCheckBox("镜像")
        self.chk_mirror.setToolTip("水平翻转画面")
        self.chk_mirror.toggled.connect(self._on_transform_changed)

        lbl_vol = QLabel("音量")
        lbl_vol.setObjectName("muted")
        lbl_speed = QLabel("速度")
        lbl_speed.setObjectName("muted")
        opts.addWidget(self.chk_accurate)
        opts.addStretch(1)
        opts.addWidget(lbl_vol)
        opts.addWidget(self.cmb_volume)
        opts.addWidget(lbl_speed)
        opts.addWidget(self.cmb_speed)
        opts.addWidget(self.chk_mirror)
        v.addLayout(opts)

        opts2 = QHBoxLayout()
        opts2.setSpacing(8)
        lbl_rot = QLabel("旋转")
        lbl_rot.setObjectName("muted")
        self.cmb_rotate = QComboBox()
        for label, val in (("0°", 0), ("90°", 90), ("180°", 180), ("270°", 270)):
            self.cmb_rotate.addItem(label, val)
        self.cmb_rotate.currentIndexChanged.connect(self._on_transform_changed)
        lbl_dec = QLabel("解码")
        lbl_dec.setObjectName("muted")
        self.cmb_decoder = QComboBox()
        for label, val in (("自动", "auto"), ("硬解", "hw"), ("软解", "sw")):
            self.cmb_decoder.addItem(label, val)
        idx = self.cmb_decoder.findData(self.settings.get("decoder", "auto"))
        self.cmb_decoder.setCurrentIndex(max(0, idx))
        self.cmb_decoder.setToolTip(
            "预览解码方式：硬解省 CPU，软解兼容性最好\n"
            "切换后需重启生效；硬解若出现黑屏/卡顿请切回自动或软解"
        )
        self.cmb_decoder.currentIndexChanged.connect(self._on_decoder_changed)
        opts2.addWidget(lbl_rot)
        opts2.addWidget(self.cmb_rotate)
        opts2.addStretch(1)
        opts2.addWidget(lbl_dec)
        opts2.addWidget(self.cmb_decoder)
        v.addLayout(opts2)

        self.btn_export = QPushButton("导出并另存为…")
        self.btn_export.setObjectName("primary")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export)
        v.addWidget(self.btn_export)
        return w

    def _build_overlay(self, parent) -> QWidget:
        ov = QWidget(parent)
        ov.setStyleSheet("background: rgba(8,8,12,0.86);")
        ov.hide()
        lay = QVBoxLayout(ov)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.addStretch(1)

        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:#111111; border:1px solid #262626; border-radius:6px;}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(10)
        self.ov_title = QLabel("正在导出…")
        self.ov_title.setStyleSheet("font-size:13px; font-weight:700;")
        self.ov_sub = QLabel("请稍候")
        self.ov_sub.setObjectName("hint")
        self.ov_bar = QProgressBar()
        self.ov_bar.setRange(0, 100)
        self.ov_bar.setValue(0)
        self.ov_bar.setTextVisible(False)
        self.ov_bar.setFixedHeight(6)
        self.ov_cancel = QPushButton("取消")
        self.ov_cancel.setObjectName("ghost")
        self.ov_cancel.setCursor(Qt.PointingHandCursor)
        self.ov_cancel.setFixedWidth(72)
        self.ov_cancel.clicked.connect(self._cancel_task)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.ov_cancel)
        cl.addWidget(self.ov_title)
        cl.addWidget(self.ov_sub)
        cl.addWidget(self.ov_bar)
        cl.addLayout(row)
        lay.addWidget(card)
        lay.addStretch(1)
        return ov


    def _apply_geometry(self) -> None:
        scr = self.screen() or QGuiApplication.primaryScreen()
        area = scr.availableGeometry()
        size = self._orb_size()
        w, h = (EXPANDED_W, EXPANDED_H) if self.expanded else (size, size)
        corner = self.settings.get("orb_corner", "tr")
        x = area.x() + (MARGIN if corner in ("tl", "bl")
                        else area.width() - w - MARGIN)
        y = area.y() + (MARGIN if corner in ("tr", "tl")
                        else area.height() - h - MARGIN)
        self.setGeometry(QRect(x, y, w, h))

    def _morph_orb_rect(self) -> QRect:
        size = self._orb_size()
        corner = self.settings.get("orb_corner", "tr")
        w, h = self.width(), self.height()
        if corner == "tl":
            return QRect(0, 0, size, size)
        if corner == "tr":
            return QRect(w - size, 0, size, size)
        if corner == "bl":
            return QRect(0, h - size, size, size)
        return QRect(w - size, h - size, size, size)

    def eventFilter(self, obj, event):
        if obj is self.panel and event.type() == QEvent.Resize:
            self._layout_overlays()
        return super().eventFilter(obj, event)

    def _layout_overlays(self) -> None:
        w, h = self.panel.width(), self.panel.height()
        if w <= 0 or h <= 0:
            return
        self.overlay.setGeometry(0, 0, w, h)
        tw = min(w - 32, 380)
        self.toast.setFixedWidth(tw)
        self.toast.move((w - tw) // 2, 54)

    def _fade(self, widget: QWidget, start: float, end: float, msec: int, on_done=None):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(msec)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if on_done is not None:
            anim.finished.connect(on_done)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def expand(self) -> None:
        if self.expanded:
            return
        self.expanded = True
        self.orb.hide()
        self.panel.show()
        self._apply_geometry()
        self.raise_()
        self.activateWindow()

        panel_opacity = QGraphicsOpacityEffect(self.panel)
        self.panel.setGraphicsEffect(panel_opacity)
        panel_opacity.setOpacity(0.0)

        morph = MorphWidget(self)
        morph.setRange(self._morph_orb_rect(), QRect(0, 0, self.width(), self.height()),
                       self._orb_size() / 2.0, 0.0)
        morph.setProgress(0.0)
        morph.show()
        morph.raise_()

        anim = QPropertyAnimation(morph, b"progress", self)
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        QTimer.singleShot(210, lambda: self._fade(self.panel, 0.0, 1.0, 140))

        def on_done():
            morph.deleteLater()
            self.panel.setGraphicsEffect(None)
            self._layout_overlays()
            if self._released and self.loaded and self.src:
                self._released = False
                self.player.setSource(QUrl.fromLocalFile(self.proxy_path or self.src))
                QTimer.singleShot(140, lambda: self.player.setPosition(self._resume_pos))

        anim.finished.connect(on_done)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def collapse(self) -> None:
        if not self.expanded:
            return
        self._resume_pos = self.player.position()
        self._stop_playback()
        self.expanded = False
        self._fade(self.panel, 1.0, 0.0, 200, self._start_collapse_morph)

    def _start_collapse_morph(self) -> None:
        self.panel.hide()
        morph = MorphWidget(self)
        morph.setRange(QRect(0, 0, self.width(), self.height()), self._morph_orb_rect(),
                       0.0, self._orb_size() / 2.0)
        morph.setProgress(0.0)
        morph.show()
        morph.raise_()

        anim = QPropertyAnimation(morph, b"progress", self)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InCubic)

        def on_done():
            morph.deleteLater()
            self.orb.show()
            self._apply_geometry()
            QTimer.singleShot(700, self._release_decoder)

        anim.finished.connect(on_done)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def _release_decoder(self) -> None:

        if self.expanded or not self.loaded:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            return
        self.player.setSource(QUrl())
        self._released = True
        trim_memory()
        self._update_mem()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._tray is not None:
            self._tray.hide()
        self._stop_playback()
        if self._export_task is not None and self._export_task.isRunning():
            self._export_task.cancel()
            self._export_task.wait(1500)
        QApplication.quit()

    def _orb_menu(self) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#111111; color:#FFFFFF; border:1px solid #262626; padding:4px;}"
            "QMenu::item{padding:6px 18px;}"
            "QMenu::item:selected{background:#2A2A2A;}"
        )
        act_open = menu.addAction("展开面板")
        act_pick = menu.addAction("打开视频…")
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        chosen = menu.exec(self.orb.mapToGlobal(self.orb.rect().bottomLeft()))
        if chosen == act_open:
            self.expand()
        elif chosen == act_pick:
            self.expand()
            self.pick_file()
        elif chosen == act_quit:
            self.quit_app()


    def pick_file(self) -> None:
        start_dir = safe_dir(
            os.path.dirname(self.src) if self.src else None,
            os.path.expanduser("~"),
            os.path.join(os.path.expanduser("~"), "Videos"),
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", start_dir,
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.flv *.ts *.wmv *.mpg *.mpeg);;所有文件 (*.*)",
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            self.toast.show_message("文件不存在或无法访问")
            return
        if not media.is_video(path):
            self.toast.show_message("只支持视频文件：MP4 / MOV / MKV / AVI / WEBM / TS 等")
            return

        self._stop_playback()
        self.player.setSource(QUrl())
        self.src = path
        self.proxy_path = None
        self.loaded = False
        self._released = False
        self._resume_pos = 0
        self.probe_data = None
        self.duration_ms = 0
        self.clips = []
        self.sel = 0
        self.cur = -1
        self._history.clear()
        self._redo.clear()
        self._pending_path = path

        self.stack.setCurrentWidget(self.editor)
        self.lbl_name.setText(Path(path).name)
        self.lbl_name.setToolTip(path)
        self.lbl_stage_time.setText("解析中…")
        self.lbl_meta.setText("")
        self.lbl_proxy.setText("")
        self.timeline.set_source(0)
        self.timeline.set_clips([])
        self.timeline._sprite = None
        self.btn_export.setEnabled(False)
        self.btn_play.setEnabled(False)
        self._set_edits(0, 0)
        self._refresh_actions()
        self._layout_overlays()

        def job():
            info = media.probe(path)
            thumbs = media.thumbnails(path, info["duration"])
            return {"probe": info, "thumbs": thumbs, "path": path}

        self._worker = Task(job, self)
        self._worker.ok.connect(self._on_probe_ok)
        self._worker.err.connect(self._on_probe_err)
        self._worker.start()

    def _on_probe_ok(self, data: dict) -> None:
        if data.get("path") != self.src:
            return
        info = data["probe"]
        self.probe_data = info
        self.duration_ms = int(info["duration"] * 1000)
        self.clips = [Clip(0, 0, self.duration_ms)]
        self.sel = 0
        self.cur = 0
        self._history.clear()
        self._redo.clear()
        self.loaded = True

        self.fps = float(info.get("fps") or 30.0) or 30.0
        res = f"{info['width']}×{info['height']}" if info["width"] else "未知分辨率"
        self._source_meta = (f"{fmt_ms(self.duration_ms, False)} · {res} · "
                             f"{fmt_size(info['size'])}")
        self.lbl_meta.setText(self._source_meta)
        self.lbl_stage_time.setText(f"00:00 / {fmt_ms(self.duration_ms, False)}")

        thumbs = data["thumbs"]
        self._sprite_path = thumbs["sprite"]
        if os.path.exists(thumbs["sprite"]) and self.settings.get("timeline_thumbs", True):
            self.timeline.set_sprite(thumbs["sprite"])
        self.timeline.set_source(self.duration_ms)
        self.timeline.set_clips(self.clips, 0)
        self._set_edits(0, self.duration_ms)
        self._refresh_actions()
        self.btn_export.setEnabled(True)
        self.btn_play.setEnabled(True)

        self.player.setSource(QUrl.fromLocalFile(self.src))
        self.player.pause()

    def _on_probe_err(self, msg: str) -> None:
        self.lbl_stage_time.setText("无法解析")
        self.toast.show_message(f"打不开这个文件：{msg}")

    def _on_player_error(self, error, msg: str) -> None:
        if not self.src or self.proxy_path or self._proxying:
            return
        self._proxying = True
        self._build_proxy()

    def _build_proxy(self) -> None:
        if self._export_task is not None and self._export_task.isRunning():
            return
        src = self.src
        dst = str(media.ensure_temp() / f"proxy_{os.getpid()}_{Path(src).stem[:24]}.mp4")

        def job(progress, should_cancel):
            args = media.build_proxy_args(src, dst)
            ok, canceled, err = media.run_ffmpeg(args, self.duration_ms / 1000 or 1, progress, should_cancel)
            if not ok:
                raise RuntimeError(err or "转码失败")
            return dst

        task = ProgressTask(job, self)
        self._export_task = task
        task.progress.connect(lambda p: self.lbl_stage_time.setText(f"生成预览代理 {p}%"))
        task.ok.connect(self._on_proxy_ok)
        task.err.connect(self._on_proxy_err)
        task.start()

    def _on_proxy_ok(self, path: str) -> None:
        self._proxying = False
        self.proxy_path = path
        self.lbl_proxy.setText("代理预览")
        self.player.setSource(QUrl.fromLocalFile(path))
        self.lbl_stage_time.setText("代理预览")
        self.toast.show_message("原格式无法直接解码，已生成预览代理（导出仍使用原片）")
        trim_memory()

    def _on_proxy_err(self, msg: str) -> None:
        self._proxying = False
        self.toast.show_message(f"预览转码失败：{msg}")
        self._layout_overlays()


    def _stop_playback(self) -> None:
        self._loop.stop()
        try:
            self.player.pause()
        except RuntimeError:
            pass

    def toggle_play(self) -> None:
        if not self.loaded or not self.clips:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._stop_playback()
            return
        t = self.timeline.pos_ms
        idx = self._clip_at(t)
        if idx < 0:
            self.seek_to(self._normalize(t))
        else:
            clip = self.clips[idx]
            if t >= clip.out_pos - 40:
                self.seek_to(self.clips[(idx + 1) % len(self.clips)].pos)
            else:
                self.cur = idx
                self.player.setPosition(clip.start + (t - clip.pos))
        self.player.play()
        self._loop.start()

    def _on_playback_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.btn_play.setIcon(QIcon(media_icon("pause" if playing else "play")))
        if not playing:
            self._loop.stop()

    def _enforce_loop(self) -> None:

        if self.player.playbackState() != QMediaPlayer.PlayingState or not self.clips:
            return
        if not (0 <= self.cur < len(self.clips)):
            self.cur = 0
        clip = self.clips[self.cur]
        src = self.player.position()
        if src >= clip.end - 30:
            if not self.settings.get("loop_playback", True) and self.cur == len(self.clips) - 1:
                self._stop_playback()
                self.timeline.set_position(clip.out_pos)
                return
            nxt = (self.cur + 1) % len(self.clips)
            self.cur = nxt
            self.player.setPosition(self.clips[nxt].start)
            self.timeline.set_position(self.clips[nxt].pos)

    def _on_position(self, ms: int) -> None:
        if not self.loaded:
            return
        if not (0 <= self.cur < len(self.clips)):
            self.timeline.set_position(0)
            return
        clip = self.clips[self.cur]
        t = clip.pos + (ms - clip.start)
        self.timeline.set_position(t)
        self.lbl_stage_time.setText(
            f"{fmt_ms(t, False)} / {fmt_ms(self._project_ms(), False)}"
        )

    def seek_to(self, t: int) -> None:

        if not self.loaded or not self.clips:
            return
        t = max(0, min(int(t), self._project_ms()))
        t = self._normalize(t)
        idx = self._clip_at(t)
        if idx < 0:
            return
        clip = self.clips[idx]
        self.cur = idx
        self.player.setPosition(clip.start + (t - clip.pos))
        self.timeline.set_position(t)


    def _clip_at(self, t: int) -> int:
        for i, c in enumerate(self.clips):
            if c.pos <= t < c.out_pos:
                return i
        return -1

    def _project_ms(self) -> int:
        return max([c.out_pos for c in self.clips], default=0)

    def _total_ms(self) -> int:
        return sum(c.length for c in self.clips)

    def _sel_clip(self):
        if 0 <= self.sel < len(self.clips):
            return self.clips[self.sel]
        return None

    def _prev_out(self, idx: int) -> int:
        return self.clips[idx - 1].out_pos if idx > 0 else 0

    def _next_pos(self, idx: int) -> int:
        if idx + 1 < len(self.clips):
            return self.clips[idx + 1].pos
        return max(self.duration_ms, self.clips[idx].out_pos)

    def _normalize(self, t: int) -> int:

        if not self.clips:
            return t
        if self._clip_at(t) >= 0:
            return t
        for c in self.clips:
            if c.pos >= t:
                return c.pos
        return self.clips[0].pos

    def _has_gap(self) -> bool:
        cursor = 0
        for c in self.clips:
            if c.pos > cursor:
                return True
            cursor = max(cursor, c.out_pos)
        return False

    def _push_history(self) -> None:
        snap = [c.as_tuple() for c in self.clips]
        if self._history and self._history[-1] == snap:
            return
        self._history.append(snap)
        if len(self._history) > 40:
            self._history.pop(0)
        self._redo.clear()

    def _restore(self, snap) -> None:
        self.clips = [Clip.from_tuple(t) for t in snap]

    def _sync_clips(self) -> None:
        self.clips.sort(key=lambda c: c.pos)
        self.sel = max(0, min(self.sel, len(self.clips) - 1))
        self.timeline.set_clips(self.clips, self.sel)
        clip = self._sel_clip()
        if clip:
            self._set_edits(clip.start, clip.end)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        multi = len(self.clips) > 1
        gap = self._has_gap()
        edited = multi or gap or (bool(self.clips) and self.clips[0].start > 0)
        self.btn_split.setEnabled(bool(self.loaded) and bool(self.clips))
        self.btn_del.setEnabled(bool(self.loaded) and multi)
        self.btn_ripple.setEnabled(bool(self.loaded) and multi)
        self.btn_closegap.setEnabled(bool(self.loaded) and gap)
        self.btn_undo.setEnabled(bool(self._history))
        self.btn_redo.setEnabled(bool(self._redo))
        self.btn_reset.setEnabled(bool(self.loaded) and edited)
        if self.loaded and self.clips:
            self.lbl_seg.setText(f"第 {self.sel + 1} / {len(self.clips)} 段")


        forced_by_multi = multi
        forced_by_speed = abs(self._speed() - 1.0) > 0.001
        forced_by_transform = self._rotate() != 0 or self.chk_mirror.isChecked()
        forced_by_volume = abs(self._volume() - 1.0) > 0.001
        forced = (forced_by_multi or forced_by_speed
                  or forced_by_transform or forced_by_volume)
        self.chk_accurate.setEnabled(not forced)
        if forced:
            self.chk_accurate.setChecked(True)
        if forced_by_multi:
            reason = "多段拼接需要重新编码，已自动开启"
        elif forced_by_speed:
            reason = "变速必须重新编码，已自动开启"
        elif forced_by_transform:
            reason = "旋转 / 镜像必须重新编码，已自动开启"
        elif forced_by_volume:
            reason = "调整音量必须重新编码，已自动开启"
        else:
            reason = ("开启：逐帧精确切割（重新编码，画质几乎无损）\n"
                      "关闭：直接复制流，秒级完成，但起点会对齐到最近的关键帧")
        self.chk_accurate.setToolTip(reason)

        if self.loaded:
            base = getattr(self, "_source_meta", "")
            if edited:
                self.lbl_meta.setText(
                    f"{base}   ·   {len(self.clips)} 段 / 成片 "
                    f"{fmt_ms(self._total_ms(), False)}"
                )
            else:
                self.lbl_meta.setText(base)

    def _on_clip_selected(self, idx: int) -> None:
        self.sel = max(0, min(idx, len(self.clips) - 1))
        self.timeline.select(self.sel)
        clip = self._sel_clip()
        if clip:
            self._set_edits(clip.start, clip.end)
        self._refresh_actions()

    def _on_move(self, idx: int, new_pos: int) -> None:
        if not (0 <= idx < len(self.clips)):
            return
        clip = self.clips[idx]
        lo = self._prev_out(idx)
        hi = max(lo, self._next_pos(idx) - clip.length)
        new_pos = max(lo, min(int(new_pos), hi))
        if new_pos != clip.pos:
            clip.pos = new_pos
            self._sync_clips()

    def _on_trim(self, idx: int, edge: str, t: int) -> None:
        if not (0 <= idx < len(self.clips)):
            return
        clip = self.clips[idx]
        if edge == "start":
            lo = self._prev_out(idx)
            new_pos = max(lo, min(int(t), clip.out_pos - 100))
            delta = new_pos - clip.pos
            new_start = max(0, min(clip.end - 100, clip.start + delta))
            clip.pos = new_pos
            clip.start = new_start
        else:
            limit = self.duration_ms
            if idx + 1 < len(self.clips):
                limit = min(limit, clip.end + max(0, self.clips[idx + 1].pos - clip.out_pos))
            new_end = max(clip.start + 100, min(int(t) - clip.pos + clip.start, limit))
            clip.end = new_end
        self._sync_clips()

    def split_at_playhead(self) -> None:
        self.split_at(self.timeline.pos_ms)

    def split_at(self, t: int) -> None:
        if not self.loaded or not self.clips:
            return
        idx = self._clip_at(t)
        if idx < 0:
            self.toast.show_message("空位上没有片段，无法分割")
            return
        clip = self.clips[idx]
        offset = t - clip.pos
        if offset < 100 or clip.length - offset < 100:
            self.toast.show_message("离边缘太近了，换个位置分割")
            return
        self._push_history()
        left = Clip(clip.pos, clip.start, clip.start + offset)
        right = Clip(t, clip.start + offset, clip.end)
        self.clips[idx:idx + 1] = [left, right]
        self.sel = idx + 1
        self._sync_clips()
        self.seek_to(t)

    def delete_selected(self) -> None:

        if not self.loaded or len(self.clips) <= 1:
            self.toast.show_message("至少要保留一个片段")
            return
        self._push_history()
        idx = self.sel
        self.clips.pop(idx)
        self.sel = min(idx, len(self.clips) - 1)
        self._sync_clips()
        self.seek_to(self.clips[self.sel].pos)
        self.toast.show_message("已删除，原位置留空；可用「闭合空隙」去掉空白", msec=3200)

    def ripple_delete(self) -> None:

        if not self.loaded or len(self.clips) <= 1:
            self.toast.show_message("至少要保留一个片段")
            return
        self._push_history()
        idx = self.sel
        removed = self.clips.pop(idx)
        for c in self.clips:
            if c.pos >= removed.out_pos:
                c.pos -= removed.length
        self.sel = min(idx, len(self.clips) - 1)
        self._sync_clips()
        self.seek_to(self.clips[self.sel].pos)
        self.toast.show_message("已波纹删除，后面的片段已前移")

    def close_gaps(self) -> None:
        if not self.loaded or not self._has_gap():
            self.toast.show_message("当前没有空隙")
            return
        self._push_history()
        cursor = 0
        for c in sorted(self.clips, key=lambda x: x.pos):
            c.pos = cursor
            cursor += c.length
        self._sync_clips()
        self.seek_to(self.clips[0].pos)
        self.toast.show_message("已闭合所有空隙")

    def undo(self) -> None:
        if not self._history:
            return
        self._redo.append([c.as_tuple() for c in self.clips])
        self._restore(self._history.pop())
        self.sel = max(0, min(self.sel, len(self.clips) - 1))
        self._sync_clips()
        clip = self._sel_clip()
        if clip:
            self.seek_to(clip.pos)
        self.toast.show_message("已撤销")

    def redo(self) -> None:
        if not self._redo:
            return
        self._history.append([c.as_tuple() for c in self.clips])
        self._restore(self._redo.pop())
        self.sel = max(0, min(self.sel, len(self.clips) - 1))
        self._sync_clips()
        clip = self._sel_clip()
        if clip:
            self.seek_to(clip.pos)
        self.toast.show_message("已重做")

    def restore_all(self) -> None:
        if not self.loaded:
            return
        self._push_history()
        self.clips = [Clip(0, 0, self.duration_ms)]
        self.sel = 0
        self._sync_clips()
        self.seek_to(0)


    def _set_edits(self, in_ms: int, out_ms: int, update_edits: bool = True) -> None:
        if update_edits:
            self.ed_in.setText(fmt_ms(in_ms))
            self.ed_out.setText(fmt_ms(out_ms))
        self.lbl_len.setText(fmt_ms(max(0, out_ms - in_ms)))

    def _on_edit_in(self) -> None:
        clip = self._sel_clip()
        if not clip:
            return
        ms = parse_time(self.ed_in.text())
        if ms is None:
            self._set_edits(clip.start, clip.end)
            return
        self._push_history()
        clip.start = max(0, min(ms, clip.end - 100))
        self._sync_clips()
        self.seek_to(clip.pos)

    def _on_edit_out(self) -> None:
        clip = self._sel_clip()
        if not clip:
            return
        ms = parse_time(self.ed_out.text())
        if ms is None:
            self._set_edits(clip.start, clip.end)
            return
        self._push_history()
        limit = self.duration_ms
        if self.sel + 1 < len(self.clips):
            limit = min(limit, clip.start + max(0, self.clips[self.sel + 1].pos - clip.pos))
        clip.end = max(clip.start + 100, min(ms, limit))
        self._sync_clips()

    def set_in_from_position(self) -> None:
        clip = self._sel_clip()
        if not clip or not self.loaded:
            return
        offset = max(0, self.timeline.pos_ms - clip.pos)
        if offset < 100:
            return
        self._push_history()
        clip.start = min(clip.end - 100, clip.start + offset)
        clip.pos += offset
        self._sync_clips()

    def set_out_from_position(self) -> None:
        clip = self._sel_clip()
        if not clip or not self.loaded:
            return
        offset = max(0, self.timeline.pos_ms - clip.pos)
        if offset < 100:
            return
        self._push_history()
        clip.end = min(self.duration_ms, clip.start + offset)
        self._sync_clips()

    def _on_speed_changed(self) -> None:
        self._refresh_actions()

    def _on_volume_changed(self) -> None:
        self.audio.setVolume(min(1.0, max(0.0, self._volume())))
        self._refresh_actions()

    def _on_transform_changed(self) -> None:
        self.view.apply_transform(self._rotate(), self.chk_mirror.isChecked())
        self._refresh_actions()

    def _on_decoder_changed(self) -> None:
        mode = self.cmb_decoder.currentData()
        self.settings["decoder"] = mode
        save_settings(self.settings)
        label = self.cmb_decoder.currentText()
        self.toast.show_message(
            f"解码方式已切换为「{label}」，重启后生效",
            action=self._restart_app,
            action_text="立即重启",
            msec=8000,
        )

    def _restart_app(self) -> None:
        try:
            if getattr(self, "_server", None) is not None:
                self._server.close()
            QLocalServer.removeServer(SINGLETON)
        except (RuntimeError, OSError):
            pass
        try:
            subprocess.Popen(
                [sys.executable, str(APP_FILE)],
                cwd=str(APP_DIR),
                creationflags=0x00000008 | 0x00000200,
            )
        except OSError:
            pass
        QApplication.quit()

    def _volume(self) -> float:
        val = self.cmb_volume.currentData()
        return float(val) if val is not None else 1.0

    def _rotate(self) -> int:
        val = self.cmb_rotate.currentData()
        return int(val) if val is not None else 0

    def _speed(self) -> float:
        val = self.cmb_speed.currentData()
        return float(val) if val else 1.0


    def export(self) -> None:
        if not self.loaded or not self.src:
            return
        if not self.clips:
            return
        if self._total_ms() < 100:
            self.toast.show_message("剩下的内容太短了，至少 0.1 秒")
            return

        speed = self._speed()
        segs = [(c.start, c.end) for c in sorted(self.clips, key=lambda c: c.pos)]
        single = len(segs) == 1
        rotate = self._rotate()
        mirror = self.chk_mirror.isChecked()
        volume = self._volume()
        mute = volume <= 0.0

        accurate = media.needs_reencode(
            segs, accurate=self.chk_accurate.isChecked(), speed=speed,
            rotate=rotate, mirror=mirror, volume=volume,
        )
        src = self.src
        stem = Path(src).stem
        ext = Path(src).suffix.lower()
        if accurate:
            fmt = self.settings.get("export_format", "same")
            if fmt in ("mp4", "mkv"):
                out_ext = f".{fmt}"
            else:
                out_ext = ext if ext in {".mp4", ".mov", ".m4v", ".mkv"} else ".mp4"
        else:
            out_ext = ext
        mode = self.settings.get("export_dir_mode", "source")
        target_dir = Path(src).parent
        if mode == "last":
            saved = self.settings.get("export_dir", "")
            if saved and os.path.isdir(saved):
                target_dir = Path(saved)
        default_path = str(target_dir / f"{stem}_剪辑{out_ext}")

        filters = "视频文件 (*.mp4 *.mov *.mkv)" if accurate else f"视频文件 (*{out_ext});;所有文件 (*.*)"
        if not os.path.isdir(os.path.dirname(default_path)):
            default_path = os.path.join(
                safe_dir(os.path.expanduser("~")), f"{stem}_剪辑{out_ext}"
            )
        out, _ = QFileDialog.getSaveFileName(self, "另存为", default_path, filters)
        if not out:
            return
        if not os.path.splitext(out)[1]:
            out += out_ext
        if os.path.abspath(out) == os.path.abspath(src):
            self.toast.show_message("不能覆盖源文件，请换个文件名")
            return

        start = segs[0][0] / 1000
        end = segs[-1][1] / 1000
        note = ""
        if not accurate:
            snapped = media.find_keyframe(src, start)
            if snapped < start - 0.02:
                note = f"起点已对齐关键帧 {fmt_ms(int(snapped * 1000), False)}"
                start = snapped
            segs = [(start, end)]
        dur = max(0.05, sum(b - a for a, b in segs) / 1000)
        if not single:
            note = f"{len(segs)} 段已拼接" + ("，" + note if note else "")
        has_audio = bool(self.probe_data and self.probe_data.get("has_audio"))

        self.ov_title.setText("正在导出…")
        self.ov_sub.setText(
            f"{len(segs)} 段 · 共 {fmt_ms(int(dur * 1000))}"
            if not single else
            f"{fmt_ms(self.clips[0].start)} → {fmt_ms(self.clips[0].end)} · "
            f"{fmt_ms(self.clips[0].length)}"
        )
        self._export_note = note
        self.ov_bar.setValue(0)
        self.ov_cancel.setText("取消")
        self.overlay.setGeometry(0, 0, self.panel.width(), self.panel.height())
        self.overlay.show()
        self.overlay.raise_()

        crf = {"high": 18, "normal": 20, "small": 23}.get(
            self.settings.get("export_quality", "normal"), 20)

        def job(progress, should_cancel):
            if accurate:
                args = media.build_concat_args(
                    src, out, segs, mute=mute, speed=speed, has_audio=has_audio,
                    rotate=rotate, mirror=mirror, volume=volume, crf=crf,
                )
                total = dur / max(speed, 0.01)
            else:
                args = media.build_export_args(
                    src, out, start, dur,
                    accurate=False, mute=mute, speed=speed, has_audio=has_audio,
                )
                total = dur
            ok, canceled, err = media.run_ffmpeg(args, total, progress, should_cancel)
            if canceled:
                return None
            if not ok:
                raise RuntimeError(err)
            return out

        task = ProgressTask(job, self)
        self._export_task = task
        task.progress.connect(self.ov_bar.setValue)
        task.ok.connect(self._on_export_ok)
        task.err.connect(self._on_export_err)
        task.canceled.connect(self._on_export_canceled)
        task.start()

    def _on_export_ok(self, out: str) -> None:
        self.overlay.hide()
        self.btn_export.setEnabled(True)
        trim_memory()
        folder = os.path.dirname(out)
        self.settings["export_dir"] = os.path.dirname(out)
        save_settings(self.settings)
        if self.settings.get("open_folder_after", False):
            try:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(out)])
            except OSError:
                pass
        msg = f"已保存：{Path(out).name}"
        if getattr(self, "_export_note", ""):
            msg += f"（{self._export_note}）"
        self.toast.show_message(
            msg,
            action=lambda: subprocess.Popen(["explorer", "/select,", os.path.normpath(out)]),
            msec=6000,
        )
        self._layout_overlays()

    def _on_export_err(self, msg: str) -> None:
        self.overlay.hide()
        self.btn_export.setEnabled(True)
        first = [l for l in msg.splitlines() if l.strip()]
        self.toast.show_message("导出失败：" + (first[-1][:90] if first else "未知错误"), msec=7000)
        self._layout_overlays()

    def _on_export_canceled(self) -> None:
        self.overlay.hide()
        self.btn_export.setEnabled(True)
        self.toast.show_message("已取消导出")
        self._layout_overlays()

    def _cancel_task(self) -> None:
        if self._export_task is not None and self._export_task.isRunning():
            self._export_task.cancel()
            self.ov_cancel.setEnabled(False)
            self.ov_title.setText("正在取消…")


    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and media.is_video(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_file(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def keyPressEvent(self, event):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Space:
            self.toggle_play()
        elif key == Qt.Key_I:
            self.set_in_from_position()
        elif key == Qt.Key_O:
            self.set_out_from_position()
        elif key == Qt.Key_S:
            self.split_at_playhead()
        elif key == Qt.Key_Delete:
            if event.modifiers() & Qt.ShiftModifier:
                self.ripple_delete()
            else:
                self.delete_selected()
        elif key == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            if event.modifiers() & Qt.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif key == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            self.redo()
        elif key in (Qt.Key_Left, Qt.Key_Right):
            step = 1000 if event.modifiers() & Qt.ShiftModifier else max(1, int(1000 / self.fps))
            self.seek_to(self.player.position() + (step if key == Qt.Key_Right else -step))
        elif key == Qt.Key_Escape:
            self.collapse()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self._request_close()


    def _qss(self) -> str:
        check = APP_DIR / "assets" / "check12.png"
        return theme.build_qss(str(check) if check.exists() else "")

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self._qss(), working_set_mb(), self,
                             autostart_active=autostart_enabled())
        if dlg.exec() != 1 or not dlg.result_settings:
            return
        old_decoder = self.settings.get("decoder", "auto")
        old_autostart = bool(self.settings.get("autostart"))
        self.settings.update(dlg.result_settings)
        save_settings(self.settings)
        self._apply_settings()
        if bool(self.settings.get("autostart")) != old_autostart:
            if bool(self.settings.get("autostart")):
                ok = autostart_enabled()
                self.toast.show_message(
                    "已开启开机自启，下次登录 Windows 会自动运行" if ok
                    else "开机自启写入失败，可能被安全软件拦截", msec=5000)
            else:
                self.toast.show_message("已关闭开机自启")
        if self.settings.get("decoder", "auto") != old_decoder:
            self.toast.show_message(
                "解码方式已修改，重启后生效",
                action=self._restart_app,
                action_text="立即重启",
                msec=9000,
            )
        else:
            self.toast.show_message("设置已保存")

    def _orb_size(self) -> int:
        return ORB_SIZES.get(self.settings.get("orb_size", "m"), ORB_SIZE)

    def _apply_settings(self) -> None:
        media.set_cache_dir(self.settings.get("cache_dir", ""))
        set_log_dir(self.settings.get("log_dir", ""))
        self.orb.set_diameter(self._orb_size())
        self._apply_geometry()

        idx = self.cmb_decoder.findData(self.settings.get("decoder", "auto"))
        if idx >= 0 and idx != self.cmb_decoder.currentIndex():
            self.cmb_decoder.blockSignals(True)
            self.cmb_decoder.setCurrentIndex(idx)
            self.cmb_decoder.blockSignals(False)

        if self.settings.get("timeline_thumbs", True):
            if self._sprite_path:
                self.timeline.set_sprite(self._sprite_path)
        else:
            self.timeline.clear_sprite()

        self._apply_autostart()

    def _apply_autostart(self) -> bool:
        return set_autostart(bool(self.settings.get("autostart", False)))

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("Fastcut 快剪 · Developed by VMO")
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#111111; color:#FFFFFF; border:1px solid #262626; padding:4px;}"
            "QMenu::item{padding:6px 18px;}"
            "QMenu::item:selected{background:#2A2A2A;}"
        )
        act_show = menu.addAction("显示悬浮球")
        act_settings = menu.addAction("设置…")
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_show.triggered.connect(self._show_window)
        act_settings.triggered.connect(self._show_window)
        act_settings.triggered.connect(self.open_settings)
        act_quit.triggered.connect(self.quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        self._tray = tray

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    def _summon(self) -> None:

        self._show_window()
        self.expand()

    def _show_window(self) -> None:
        if self._tray is not None:
            self._tray.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self) -> None:
        if self._tray is None:
            self._build_tray()
        if self._tray is None:
            self.quit_app()
            return
        self._stop_playback()
        self.hide()
        self._tray.show()
        if not self._tray_hint_shown:
            self._tray.showMessage(
                "Fastcut 已隐藏到任务栏",
                "双击托盘图标可以恢复悬浮球",
                QSystemTrayIcon.Information, 4000,
            )
            self._tray_hint_shown = True

    def _request_close(self) -> None:
        if self._closing or self._quitting:
            return
        self._closing = True
        try:
            self._do_request_close()
        finally:
            self._closing = False

    def _do_request_close(self) -> None:
        action = self.settings.get("close_action", "ask")
        if action == "tray":
            self.hide_to_tray()
            return
        if action == "quit":
            self.quit_app()
            return
        dlg = CloseDialog(self._qss(), self)
        if dlg.exec() != 1 or not dlg.choice:
            return
        if dlg.remember:
            self.settings["close_action"] = dlg.choice
            save_settings(self.settings)
        if dlg.choice == "tray":
            self.hide_to_tray()
        else:
            self.quit_app()

    def _update_mem(self) -> None:
        mb = working_set_mb()
        self.lbl_mem.setText(f"内存 {mb:.0f} MB" if mb else "")
        self.lbl_mem.setToolTip("当前进程工作集内存，Fastcut 全程保持低占用")


def main() -> int:
    sys.excepthook = log_exception
    try:
        return _run()
    except Exception:
        log_exception(*sys.exc_info())
        try:
            from PySide6.QtWidgets import QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None, "Fastcut 启动失败",
                "启动时出错，详细信息已写入：\n"
                f"{LOG_DIR / 'error.log'}\n\n"
                + "".join(traceback.format_exception(*sys.exc_info()))[-800:],
            )
        except Exception:
            pass
        return 1


def _run() -> int:
    apply_decoder_env(load_settings().get("decoder", "auto"))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    app.setQuitOnLastWindowClosed(False)


    probe = QLocalSocket()
    probe.connectToServer(SINGLETON)
    if probe.waitForConnected(150):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(200)
        return 0

    QLocalServer.removeServer(SINGLETON)
    win = FastcutWindow()
    server = QLocalServer()
    server.listen(SINGLETON)

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(win._summon)
            conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_new_connection)
    win._server = server

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
