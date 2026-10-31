from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .widgets import Panel

APP_DIR = Path(__file__).resolve().parent.parent


class HeaderBar(QWidget):


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._press = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, event):
        self._press = None


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, qss: str, mem_mb: float = 0.0, parent=None,
                 autostart_active: bool = False):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(qss)
        self.setModal(True)
        self.setFixedSize(560, 500)
        self._src = dict(settings)
        self._mem = mem_mb
        self._autostart_active = autostart_active
        self.result_settings: dict | None = None
        self._nav_buttons: list[QPushButton] = []
        self._build()


    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        panel = Panel(radius=8)
        root.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_header())

        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(14, 2, 14, 6)
        bl.setSpacing(12)
        bl.addWidget(self._build_nav())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_general())
        self.stack.addWidget(self._page_playback())
        self.stack.addWidget(self._page_storage())
        self.stack.addWidget(self._page_export())
        self.stack.addWidget(self._page_about())
        bl.addWidget(self.stack, 1)
        lay.addWidget(body, 1)

        lay.addWidget(self._build_footer())
        self._nav_buttons[0].setChecked(True)

    def _build_header(self) -> QWidget:
        header = HeaderBar()
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 0, 12, 0)
        title = QLabel("设置")
        title.setObjectName("brand")
        sub = QLabel("Fastcut 快剪 · Developed by VMOStar")
        sub.setObjectName("hint")
        close = QPushButton("✕")
        close.setObjectName("closeBtn")
        close.setFixedSize(26, 26)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.reject)
        h.addWidget(title)
        h.addSpacing(6)
        h.addWidget(sub)
        h.addStretch(1)
        h.addWidget(close)
        return header

    def _build_nav(self) -> QWidget:
        nav = QWidget()
        nav.setFixedWidth(104)
        v = QVBoxLayout(nav)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(4)
        for i, name in enumerate(("常规", "播放", "存储", "导出", "关于")):
            b = QPushButton(name)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._switch(idx))
            v.addWidget(b)
            self._nav_buttons.append(b)
        v.addStretch(1)
        return nav

    def _switch(self, index: int) -> None:
        for i, b in enumerate(self._nav_buttons):
            b.setChecked(i == index)
        self.stack.setCurrentIndex(index)


    def _row(self, title: str, subtitle: str, control: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 7, 0, 7)
        h.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-size:12px; color:#E4E4F0;")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("hint")
            s.setWordWrap(True)
            col.addWidget(s)
        h.addLayout(col, 1)
        h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        return w

    def _check_row(self, title: str, subtitle: str, checked: bool):

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 7, 0, 7)
        v.setSpacing(2)
        cb = QCheckBox(title)
        cb.setChecked(checked)
        cb.setObjectName("checkRow")
        cb.setCursor(Qt.PointingHandCursor)
        v.addWidget(cb)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            v.addWidget(hint)
        return w, cb

    def _hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color:#949494; font-size:11px;"
            "background:#0A0A0A;"
            "border:1px solid #1A1A1A; border-radius:4px;"
            "padding:8px 10px;"
        )
        return lbl

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setObjectName("sep")
        line.setFixedHeight(1)
        return line

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _combo(self, items, current) -> QComboBox:
        cb = QComboBox()
        cb.setMinimumWidth(132)
        for label, val in items:
            cb.addItem(label, val)
        idx = cb.findData(current)
        cb.setCurrentIndex(max(0, idx))
        return cb

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(2, 6, 6, 6)
        v.setSpacing(2)
        v.addStretch(0)
        return page, v


    def _page_general(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._section("启动"))

        auto_row, self.chk_autostart = self._check_row(
            "开机自动启动",
            "登录 Windows 后自动运行 Fastcut（写入当前用户启动项，无需管理员权限）",
            bool(self._src.get("autostart", False)),
        )
        v.addWidget(auto_row)
        self.lbl_auto_state = QLabel("")
        self.lbl_auto_state.setObjectName("hint")
        self.lbl_auto_state.setStyleSheet("color:#949494; font-size:11px; padding-left:2px;")
        v.addWidget(self.lbl_auto_state)
        self.chk_autostart.toggled.connect(self._sync_auto_state)
        self._sync_auto_state()
        v.addWidget(self._sep())

        v.addWidget(self._section("窗口行为"))
        self.cb_close = self._combo(
            [("每次询问", "ask"), ("隐藏到任务栏托盘", "tray"), ("直接退出", "quit")],
            self._src.get("close_action", "ask"),
        )
        v.addWidget(self._row("关闭面板时", "点右上角 ✕ 之后的动作", self.cb_close))
        v.addWidget(self._sep())

        self.cb_corner = self._combo(
            [("右上角", "tr"), ("右下角", "br"), ("左上角", "tl"), ("左下角", "bl")],
            self._src.get("orb_corner", "tr"),
        )
        v.addWidget(self._row("悬浮球停靠", "启动时悬浮球出现的位置", self.cb_corner))
        v.addWidget(self._sep())

        self.cb_orbsize = self._combo(
            [("小", "s"), ("中", "m"), ("大", "l")],
            self._src.get("orb_size", "m"),
        )
        v.addWidget(self._row("悬浮球大小", "屏幕上那个圆球的直径", self.cb_orbsize))
        v.addSpacing(10)
        v.addWidget(self._hint(
            "提示：悬浮球可以用鼠标直接拖到屏幕任意位置；"
            "双击时间轴可以快速分割，删除后用「闭合空隙」可去掉空白。"
        ))
        v.addStretch(1)
        return page


    def _sync_auto_state(self) -> None:
        wanted = self.chk_autostart.isChecked()
        if wanted == self._autostart_active:
            state = "已启用" if wanted else "未启用"
            self.lbl_auto_state.setText(f"当前状态：{state}")
        else:
            self.lbl_auto_state.setText(
                "保存后生效：" + ("将随 Windows 启动" if wanted else "不再随 Windows 启动")
            )

    def _page_playback(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._section("预览"))

        self.cb_decoder = self._combo(
            [("自动（推荐）", "auto"), ("硬件解码 D3D11", "hw"), ("软件解码", "sw")],
            self._src.get("decoder", "auto"),
        )
        v.addWidget(self._row(
            "解码方式",
            "硬解省 CPU，软解兼容性最好；切换后需要重启生效",
            self.cb_decoder,
        ))
        v.addWidget(self._sep())

        loop_row, self.chk_loop = self._check_row(
            "循环播放",
            "播放到最后一个片段后回到开头；关闭则停在结尾",
            bool(self._src.get("loop_playback", True)),
        )
        v.addWidget(loop_row)
        v.addWidget(self._sep())

        thumb_row, self.chk_thumb = self._check_row(
            "显示时间轴缩略图",
            "关闭后时间轴只显示纯色块，长视频滚动更省内存",
            bool(self._src.get("timeline_thumbs", True)),
        )
        v.addWidget(thumb_row)
        v.addSpacing(10)
        v.addWidget(self._hint(
            "提示：播放时会自动跳过被删除的空位，跨片段连续播放；"
            "空格暂停、← → 逐帧步进。"
        ))
        v.addStretch(1)
        return page


    def _page_storage(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._section("缓存与日志"))

        v.addWidget(self._row(
            "缓存目录",
            "缩略图、预览代理等临时文件的存放位置，可随时清空",
            QLabel(""),
        ))
        self.ed_cache = QLineEdit(self._src.get("cache_dir", ""))
        self.ed_cache.setObjectName("pathEdit")
        self.ed_cache.setPlaceholderText(
            f"默认：{Path(tempfile.gettempdir()) / 'fastcut'}"
        )
        self.ed_cache.textChanged.connect(self._refresh_cache_size)
        b_cache_pick = QPushButton("浏览…")
        b_cache_pick.setObjectName("ghost")
        b_cache_pick.setCursor(Qt.PointingHandCursor)
        b_cache_pick.clicked.connect(lambda: self._pick_dir_into(self.ed_cache))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.ed_cache, 1)
        row.addWidget(b_cache_pick)
        v.addLayout(row)

        self.lbl_cache_size = QLabel("—")
        self.lbl_cache_size.setObjectName("hint")
        b_open_cache = QPushButton("打开")
        b_open_cache.setObjectName("ghost")
        b_open_cache.setCursor(Qt.PointingHandCursor)
        b_open_cache.clicked.connect(lambda: self._open_dir(self._cache_path()))
        b_clear_cache = QPushButton("清空缓存")
        b_clear_cache.setObjectName("ghost")
        b_clear_cache.setCursor(Qt.PointingHandCursor)
        b_clear_cache.clicked.connect(self._clear_cache)
        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        tools_row.addWidget(b_open_cache)
        tools_row.addWidget(b_clear_cache)
        tools_row.addStretch(1)
        tools_row.addWidget(self.lbl_cache_size)
        v.addLayout(tools_row)
        v.addWidget(self._sep())

        v.addWidget(self._row(
            "日志目录",
            "启动失败时的错误堆栈会写在这里",
            QLabel(""),
        ))
        self.ed_log = QLineEdit(self._src.get("log_dir", ""))
        self.ed_log.setObjectName("pathEdit")
        self.ed_log.setPlaceholderText(f"默认：{APP_DIR / 'logs'}")
        b_log_pick = QPushButton("浏览…")
        b_log_pick.setObjectName("ghost")
        b_log_pick.setCursor(Qt.PointingHandCursor)
        b_log_pick.clicked.connect(lambda: self._pick_dir_into(self.ed_log))
        b_log_open = QPushButton("打开")
        b_log_open.setObjectName("ghost")
        b_log_open.setCursor(Qt.PointingHandCursor)
        b_log_open.clicked.connect(lambda: self._open_dir(self._log_path()))
        log_row = QHBoxLayout()
        log_row.setSpacing(6)
        log_row.addWidget(self.ed_log, 1)
        log_row.addWidget(b_log_pick)
        log_row.addWidget(b_log_open)
        v.addLayout(log_row)

        v.addSpacing(10)
        v.addWidget(self._hint(
            "提示：缓存目录默认在系统临时目录，换到空间更大的盘可以避免 C 盘被占满；"
            "留空即使用默认位置。修改后点「保存」生效。"
        ))
        v.addStretch(1)
        self._refresh_cache_size()
        return page

    def _cache_path(self) -> Path:
        raw = self.ed_cache.text().strip()
        return Path(raw) if raw else Path(tempfile.gettempdir()) / "fastcut"

    def _log_path(self) -> Path:
        raw = self.ed_log.text().strip()
        return Path(raw) if raw else APP_DIR / "logs"

    def _pick_dir_into(self, edit: QLineEdit) -> None:
        start = edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", start)
        if path:
            edit.setText(path)

    def _open_dir(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except OSError:
            pass

    def _refresh_cache_size(self) -> None:
        if not hasattr(self, "lbl_cache_size"):
            return
        total = 0
        count = 0
        path = self._cache_path()
        try:
            if path.is_dir():
                for f in path.rglob("*"):
                    if f.is_file():
                        count += 1
                        total += f.stat().st_size
        except OSError:
            pass
        self.lbl_cache_size.setText(
            f"{count} 个文件 · {total / 1048576:.1f} MB" if count else "当前为空"
        )

    def _clear_cache(self) -> None:
        path = self._cache_path()
        removed = 0
        try:
            if path.is_dir():
                for f in path.rglob("*"):
                    if f.is_file():
                        try:
                            f.unlink()
                            removed += 1
                        except OSError:
                            pass
        except OSError:
            pass
        self._refresh_cache_size()
        self.lbl_cache_size.setText(f"已清理 {removed} 个文件")


    def _page_export(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._section("输出"))

        self.cb_quality = self._combo(
            [("高画质（CRF 18）", "high"), ("标准（CRF 20）", "normal"),
             ("小体积（CRF 23）", "small")],
            self._src.get("export_quality", "normal"),
        )
        v.addWidget(self._row("默认画质", "仅影响需要重新编码的导出", self.cb_quality))
        v.addWidget(self._sep())

        self.cb_format = self._combo(
            [("跟随源文件", "same"), ("MP4", "mp4"), ("MKV", "mkv")],
            self._src.get("export_format", "same"),
        )
        v.addWidget(self._row("默认格式", "极速复制模式始终跟随源文件", self.cb_format))
        v.addWidget(self._sep())

        self.cb_dir_mode = self._combo(
            [("源文件同目录", "source"), ("记住上次的目录", "last"), ("每次询问", "ask")],
            self._src.get("export_dir_mode", "source"),
        )
        self.cb_dir_mode.currentIndexChanged.connect(self._sync_dir_enabled)
        v.addWidget(self._row("保存位置", "另存为对话框的默认目录", self.cb_dir_mode))

        self.ed_dir = QLineEdit(self._src.get("export_dir", ""))
        self.ed_dir.setObjectName("pathEdit")
        self.ed_dir.setPlaceholderText("尚未选择目录")
        self.ed_dir.setReadOnly(True)
        self.btn_dir = QPushButton("浏览…")
        self.btn_dir.setObjectName("ghost")
        self.btn_dir.setCursor(Qt.PointingHandCursor)
        self.btn_dir.clicked.connect(self._pick_dir)
        dirrow = QWidget()
        dh = QHBoxLayout(dirrow)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.setSpacing(6)
        dh.addWidget(self.ed_dir, 1)
        dh.addWidget(self.btn_dir)
        v.addWidget(self._row("记住的目录", "", dirrow))
        v.addWidget(self._sep())

        open_row, self.chk_open = self._check_row(
            "导出完成后打开所在文件夹",
            "",
            bool(self._src.get("open_folder_after", False)),
        )
        v.addWidget(open_row)
        v.addSpacing(10)
        v.addWidget(self._hint(
            "提示：多段拼接、旋转、变速、调音量都会重新编码，画质档位只在这时生效；"
            "单段且不改任何效果时会直接复制视频流，秒级完成。"
        ))
        v.addStretch(1)
        self._sync_dir_enabled()
        return page

    def _sync_dir_enabled(self) -> None:
        enabled = self.cb_dir_mode.currentData() == "last"
        self.ed_dir.setEnabled(enabled)
        self.btn_dir.setEnabled(enabled)

    def _pick_dir(self) -> None:
        start = self.ed_dir.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择默认导出目录", start)
        if path:
            self.ed_dir.setText(path)


    def _page_about(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._section("关于"))

        title = QLabel("Fastcut 快剪")
        title.setStyleSheet("font-size:15px; font-weight:700; color:#E9E9F5;")
        v.addWidget(title)
        desc = QLabel("屏幕角落的轻量视频快剪工具\n单进程 Qt + FFmpeg，不依赖浏览器内核")
        desc.setObjectName("hint")
        v.addWidget(desc)
        brand = QLabel("Developed by VMOStar")
        brand.setStyleSheet(
            "color:#FFFFFF; font-size:12px; font-weight:600;"
        )
        v.addWidget(brand)
        v.addSpacing(8)

        from . import __version__
        rows = [
            ("版本", __version__),
            ("当前内存", f"{self._mem:.0f} MB" if self._mem else "—"),
            ("配置目录", str(APP_DIR)),
            ("日志文件", str(Path(self._src.get("log_dir") or (APP_DIR / "logs"))
                            / "error.log")),
        ]
        for k, val in rows:
            v.addWidget(self._row(k, "", QLabel(val)))
            v.addWidget(self._sep())

        btns = QHBoxLayout()
        btns.setSpacing(8)
        b_open = QPushButton("打开配置目录")
        b_open.setObjectName("ghost")
        b_open.setCursor(Qt.PointingHandCursor)
        b_open.clicked.connect(lambda: os.startfile(str(APP_DIR)))
        b_log = QPushButton("查看错误日志")
        b_log.setObjectName("ghost")
        b_log.setCursor(Qt.PointingHandCursor)
        b_log.clicked.connect(self._open_log)
        btns.addWidget(b_open)
        btns.addWidget(b_log)
        btns.addStretch(1)
        v.addLayout(btns)
        v.addStretch(1)
        return page

    def _open_log(self) -> None:
        log = APP_DIR / "logs" / "error.log"
        if log.exists():
            os.startfile(str(log))
        else:
            os.makedirs(str(APP_DIR / "logs"), exist_ok=True)
            os.startfile(str(APP_DIR / "logs"))


    def _build_footer(self) -> QWidget:
        foot = QWidget()
        h = QHBoxLayout(foot)
        h.setContentsMargins(16, 8, 16, 14)
        h.setSpacing(8)
        reset = QPushButton("恢复默认")
        reset.setObjectName("ghost")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.setFixedWidth(96)
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        h.addWidget(reset)
        h.addStretch(1)
        h.addWidget(cancel)
        h.addWidget(save)
        return foot

    def _reset(self) -> None:
        from . import defaults
        self._src = defaults()
        self.cb_close.setCurrentIndex(max(0, self.cb_close.findData(self._src["close_action"])))
        self.cb_corner.setCurrentIndex(max(0, self.cb_corner.findData(self._src["orb_corner"])))
        self.cb_orbsize.setCurrentIndex(max(0, self.cb_orbsize.findData(self._src["orb_size"])))
        self.cb_decoder.setCurrentIndex(max(0, self.cb_decoder.findData(self._src["decoder"])))
        self.cb_quality.setCurrentIndex(max(0, self.cb_quality.findData(self._src["export_quality"])))
        self.cb_format.setCurrentIndex(max(0, self.cb_format.findData(self._src["export_format"])))
        self.cb_dir_mode.setCurrentIndex(max(0, self.cb_dir_mode.findData(self._src["export_dir_mode"])))
        self.chk_autostart.setChecked(self._src["autostart"])
        self.chk_loop.setChecked(self._src["loop_playback"])
        self.chk_thumb.setChecked(self._src["timeline_thumbs"])
        self.chk_open.setChecked(self._src["open_folder_after"])
        self.ed_dir.setText(self._src.get("export_dir", ""))
        self.ed_cache.setText(self._src.get("cache_dir", ""))
        self.ed_log.setText(self._src.get("log_dir", ""))
        self._refresh_cache_size()
        self._sync_dir_enabled()

    def _save(self) -> None:
        self.result_settings = {
            "close_action": self.cb_close.currentData(),
            "autostart": self.chk_autostart.isChecked(),
            "orb_corner": self.cb_corner.currentData(),
            "orb_size": self.cb_orbsize.currentData(),
            "decoder": self.cb_decoder.currentData(),
            "loop_playback": self.chk_loop.isChecked(),
            "timeline_thumbs": self.chk_thumb.isChecked(),
            "export_quality": self.cb_quality.currentData(),
            "export_format": self.cb_format.currentData(),
            "export_dir_mode": self.cb_dir_mode.currentData(),
            "export_dir": self.ed_dir.text().strip(),
            "open_folder_after": self.chk_open.isChecked(),
            "cache_dir": self.ed_cache.text().strip(),
            "log_dir": self.ed_log.text().strip(),
        }
        self.accept()


class CloseDialog(QDialog):


    def __init__(self, qss: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(qss)
        self.setModal(True)
        self.setFixedSize(360, 186)
        self.choice: str | None = None
        self.remember = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = Panel(radius=8)
        root.addWidget(panel)
        v = QVBoxLayout(panel)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)

        title = QLabel("要退出 Fastcut 吗？")
        title.setStyleSheet("font-size:14px; font-weight:700;")
        v.addWidget(title)
        hint = QLabel("隐藏到任务栏托盘后，程序继续在后台运行，双击托盘图标即可恢复。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.chk = QCheckBox("记住我的选择（可在设置里修改）")
        v.addWidget(self.chk)

        row = QHBoxLayout()
        row.setSpacing(8)
        b_cancel = QPushButton("取消")
        b_cancel.setObjectName("ghost")
        b_cancel.clicked.connect(self.reject)
        b_tray = QPushButton("隐藏到托盘")
        b_tray.setObjectName("ghost")
        b_tray.clicked.connect(lambda: self._done("tray"))
        b_quit = QPushButton("退出")
        b_quit.setObjectName("primary")
        b_quit.setFixedWidth(84)
        b_quit.clicked.connect(lambda: self._done("quit"))
        for b in (b_cancel, b_tray, b_quit):
            b.setCursor(Qt.PointingHandCursor)
        row.addWidget(b_cancel)
        row.addStretch(1)
        row.addWidget(b_tray)
        row.addWidget(b_quit)
        v.addStretch(1)
        v.addLayout(row)

    def _done(self, choice: str) -> None:
        self.choice = choice
        self.remember = self.chk.isChecked()
        self.accept()
