"""
Persistent Viewport Configuration Manager for Diff Image Game.
Stores and loads user-calibrated panel boundaries so they persist across game rounds.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

CONFIG_FILE_NAME = ".diff_game_viewport.json"


def get_viewport_config_path() -> Path:
    """Returns persistent viewport config path in user home or current directory."""
    home_path = Path.home() / CONFIG_FILE_NAME
    local_path = Path.cwd() / CONFIG_FILE_NAME
    if local_path.exists():
        return local_path
    return home_path


def load_viewport_config() -> Optional[Dict[str, Any]]:
    """Loads saved viewport bounding boxes if they exist."""
    path = get_viewport_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "refBox" in data and "tgtBox" in data:
                    return data
        except Exception:
            pass
    return None


def save_viewport_config(ref_box: Dict[str, float], tgt_box: Dict[str, float], scale: float = 2.0) -> Path:
    """Saves user-calibrated viewport coordinates."""
    path = get_viewport_config_path()
    data = {
        "scale": float(scale),
        "refBox": {
            "x": round(float(ref_box["x"]), 1),
            "y": round(float(ref_box["y"]), 1),
            "width": round(float(ref_box["width"]), 1),
            "height": round(float(ref_box["height"]), 1),
        },
        "tgtBox": {
            "x": round(float(tgt_box["x"]), 1),
            "y": round(float(tgt_box["y"]), 1),
            "width": round(float(tgt_box["width"]), 1),
            "height": round(float(tgt_box["height"]), 1),
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def clear_viewport_config() -> bool:
    """Deletes saved calibration config, reverting to auto-detection."""
    path = get_viewport_config_path()
    if path.exists():
        try:
            os.remove(path)
            return True
        except Exception:
            return False
    return False
