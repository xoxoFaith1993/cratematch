import json
import os


def data_dir():
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CrateMatch")
    os.makedirs(d, exist_ok=True)
    return d


def _settings_file():
    return os.path.join(data_dir(), "settings.json")


def load_settings():
    try:
        with open(_settings_file(), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    tmp = _settings_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _settings_file())
