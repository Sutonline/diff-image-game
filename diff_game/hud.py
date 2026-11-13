"""
Native macOS HUD Overlay Module for Spot-The-Difference WeChat Mini Programs.

Finds the WeChat Mini Program game window on screen, captures the viewport,
computes non-overlapping difference marks using the OpenCV engine,
and projects a native transparent floating overlay directly over the game window.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import cv2
import numpy as np

from diff_game.engine import compare_game_sheet

OVERLAY_SWIFT_SOURCE = Path(__file__).parent / "overlay.swift"
OVERLAY_BIN_PATH = Path(__file__).parent / "overlay_bin"


def ensure_overlay_binary() -> Path:
    """Ensures the native Swift overlay binary exists."""
    if not OVERLAY_BIN_PATH.exists():
        print("🔨 编译原生 macOS 透明悬浮窗组件 (Swift)...")
        res = subprocess.run(
            ["swiftc", "-O", str(OVERLAY_SWIFT_SOURCE), "-o", str(OVERLAY_BIN_PATH)],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"编译 Swift 悬浮窗组件失败:\n{res.stderr}")
    return OVERLAY_BIN_PATH


FIND_WINDOWS_BIN = Path(__file__).parent / "find_windows"
FIND_WINDOWS_SRC = Path(__file__).parent / "find_windows.c"


def ensure_find_windows_binary() -> Path:
    """Ensures native C window finder binary exists."""
    if not FIND_WINDOWS_BIN.exists() and FIND_WINDOWS_SRC.exists():
        subprocess.run(
            ["clang", "-O2", "-framework", "CoreGraphics", "-framework", "CoreFoundation", str(FIND_WINDOWS_SRC), "-o", str(FIND_WINDOWS_BIN)],
            capture_output=True,
        )
    return FIND_WINDOWS_BIN


def list_wechat_windows() -> List[Dict[str, Any]]:
    """
    Queries on-screen windows via native CoreGraphics binary and returns WeChat candidates.
    """
    bin_path = ensure_find_windows_binary()
    if bin_path.exists():
        res = subprocess.run([str(bin_path)], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            try:
                return json.loads(res.stdout.strip())
            except Exception:
                pass
    return []


def detect_game_window() -> Optional[Dict[str, Any]]:
    """
    Identifies the best matching WeChat Mini Program game window based on aspect ratio and title.
    """
    windows = list_wechat_windows()
    if not windows:
        return None

    # Priority 1: Window whose name contains game keywords or is not standard 'Weixin' / '微信'
    for w in windows:
        name = w.get("name", "")
        aspect = w.get("aspectRatio", 0)
        if aspect > 1.2 and name and name not in ("Weixin", "微信"):
            return w

    # Priority 2: Any WeChat window with vertical phone aspect ratio (> 1.2)
    for w in windows:
        if w.get("aspectRatio", 0) > 1.2:
            return w

    # Fallback to the first WeChat window
    return windows[0]


def capture_window_rect(x: int, y: int, width: int, height: int, output_path: str = "/tmp/hud_game_capture.png") -> str:
    """Captures a specific screen rectangle at high speed via native CoreGraphics."""
    bin_path = ensure_find_windows_binary()
    cmd = [str(bin_path), "--capture", str(x), str(y), str(width), str(height), output_path]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not os.path.exists(output_path):
        # Fallback to screencapture if needed
        cmd_fallback = ["screencapture", "-x", f"-R{x},{y},{width},{height}", output_path]
        subprocess.run(cmd_fallback, capture_output=True)
    if not os.path.exists(output_path):
        raise RuntimeError(f"屏幕截取失败: 无法生成截图文件 {output_path}")
    return output_path


def kill_existing_overlays() -> None:
    """Kills any active overlay_bin processes to avoid zombie or duplicate floating windows."""
    try:
        subprocess.run(["killall", "overlay_bin"], capture_output=True)
    except Exception:
        pass


def solve_and_display_hud(
    window: Dict[str, Any],
    click_through: bool = True,
    timeout: float = 15.0,
    diff_threshold: int = 24,
    min_area: int = 100,
    max_marks: int = 10,
) -> int:
    """
    Captures game window, solves spot-the-difference, and displays native overlay.
    Returns the number of detected differences.
    """
    # Always kill previous overlay window before capturing to prevent capturing old overlay marks
    kill_existing_overlays()

    bin_path = ensure_overlay_binary()

    x = int(window["x"])
    y = int(window["y"])
    width = int(window["width"])
    height = int(window["height"])

    print(f"📸 捕获微信小游戏窗口: [{window.get('name', '小程序')}] ({width}×{height} at X={x}, Y={y})...")
    capture_path = "/tmp/hud_game_capture.png"
    capture_window_rect(x, y, width, height, capture_path)

    img = cv2.imread(capture_path)
    if img is None:
        raise ValueError("无法解析截取的游戏画面")

    img_h, img_w = img.shape[:2]
    # Retina displays produce 2x image pixels relative to screen points
    scale_factor = img_w / float(width) if width > 0 else 1.0

    print(f"⚡ OpenCV 算法比对中 (画面像素: {img_w}×{img_h}, Retina倍率: {scale_factor:.1f}x)...")
    result, _ = compare_game_sheet(
        img,
        diff_threshold=diff_threshold,
        min_area=min_area,
        max_differences=max_marks if max_marks > 0 else None,
    )

    diff_count = len(result.differences)
    if max_marks > 0 and diff_count == max_marks:
        print(f"🎯 检出差异: {diff_count} 处 (按显著度优选 Top {max_marks}，耗时: {result.execution_time_ms} ms)")
    else:
        print(f"🎯 检出差异: {diff_count} 处 (耗时: {result.execution_time_ms} ms)")

    if diff_count == 0:
        print("💡 未检出差异（可能处于主菜单/结算界面或无明显色差）")
        return 0

    # Format differences for native overlay
    marks_data = []
    for d in result.differences:
        mark_dict = {
            "id": d.id,
            "radius": float(d.radius),
            "refX": float(d.global_ref_center[0]) if d.global_ref_center else None,
            "refY": float(d.global_ref_center[1]) if d.global_ref_center else None,
            "tgtX": float(d.global_tgt_center[0]) if d.global_tgt_center else None,
            "tgtY": float(d.global_tgt_center[1]) if d.global_tgt_center else None,
        }
        marks_data.append(mark_dict)

    config_data = {
        "bounds": {
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height),
        },
        "scale": float(scale_factor),
        "clickThrough": click_through,
        "timeout": float(timeout),
        "differenceCount": diff_count,
        "differences": marks_data,
    }

    config_path = "/tmp/hud_overlay_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)

    print("✨ 已在微信小游戏窗口上方投射原位透明红圈！")
    print("   👉 提示：已开启【点击穿透】，可直接点击红圈对应的游戏内容；按 ESC 或点击顶部横条可关闭。")

    # Run native overlay
    subprocess.Popen([str(bin_path), config_path])
    return diff_count
