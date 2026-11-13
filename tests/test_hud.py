import json
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from diff_game.hud import (
    detect_game_window,
    ensure_overlay_binary,
    list_wechat_windows,
)


def test_detect_game_window_priority():
    mock_windows = [
        {"name": "Weixin", "owner": "WeChat", "aspectRatio": 0.65, "width": 1000, "height": 650},
        {"name": "眼力大侦探", "owner": "WeChat", "aspectRatio": 1.93, "width": 410, "height": 793},
        {"name": "微信读书", "owner": "微信读书", "aspectRatio": 0.8, "width": 800, "height": 640},
    ]
    with patch("diff_game.hud.list_wechat_windows", return_value=mock_windows):
        best = detect_game_window()
        assert best is not None
        assert best["name"] == "眼力大侦探"
        assert best["width"] == 410


def test_detect_game_window_fallback():
    mock_windows = [
        {"name": "Weixin", "owner": "WeChat", "aspectRatio": 1.8, "width": 400, "height": 720},
    ]
    with patch("diff_game.hud.list_wechat_windows", return_value=mock_windows):
        best = detect_game_window()
        assert best is not None
        assert best["aspectRatio"] == 1.8


def test_detect_game_window_none():
    with patch("diff_game.hud.list_wechat_windows", return_value=[]):
        best = detect_game_window()
        assert best is None


def test_ensure_overlay_binary():
    bin_path = ensure_overlay_binary()
    assert bin_path.exists()
    assert bin_path.is_file()
