__version__ = "1.2.0"


DEFAULT_SETTINGS = {
    "decoder": "auto",
    "close_action": "ask",
    "autostart": False,
    "orb_corner": "tr",
    "orb_size": "m",
    "loop_playback": True,
    "timeline_thumbs": True,
    "export_quality": "normal",
    "export_format": "same",
    "export_dir_mode": "source",
    "export_dir": "",
    "open_folder_after": False,
    "cache_dir": "",
    "log_dir": "",
}


def defaults() -> dict:
    return dict(DEFAULT_SETTINGS)
