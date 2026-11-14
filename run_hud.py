#!/usr/bin/env python3
"""
Spot The Difference - WeChat Mini Program In-Place Transparent HUD Runner.
一键微信小游戏原位找茬辅助工具（原生透明覆盖层 · 点击穿透）
"""

import sys
import argparse
from diff_game.hud import (
    detect_game_window,
    solve_and_display_hud,
    list_wechat_windows,
    kill_existing_overlays,
)


def main():
    parser = argparse.ArgumentParser(
        description="找茬游戏电脑微信小程序原位透明辅助层 (HUD)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="红圈覆盖层显示时长（秒），默认 15s 后自动关闭",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=24,
        help="色差敏感度阈值（默认 24）",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=100,
        help="最小连通面积过滤噪点（默认 100 px²）",
    )
    parser.add_argument(
        "--max-marks",
        type=int,
        default=0,
        help="差异数量上限（默认 0 表示全量自动检出，不人为截断）",
    )
    parser.add_argument(
        "--no-click-through",
        action="store_true",
        help="关闭点击穿透（默认开启点击穿透，可直接对着红圈点击游戏）",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🎯 找茬小游戏原位透明 HUD 辅助系统 (macOS Native)")
    print("=" * 60)

    # 1. Detect game window
    window = detect_game_window()
    if not window:
        print("❌ 未检测到正在运行的微信小游戏/小程序窗口！")
        print("\n🔍 扫描到的所有微信相关窗口：")
        windows = list_wechat_windows()
        if not windows:
            print("   (当前没有检测到任何微信窗口，请先打开电脑版微信并进入找茬小游戏)")
        else:
            for i, w in enumerate(windows, 1):
                print(f"   [{i}] 标题: {w.get('name') or '<无标题>'}, 尺寸: {w.get('width')}x{w.get('height')}, 比例: {w.get('aspectRatio'):.2f}")
        sys.exit(1)

    print(f"✅ 成功定位目标窗口: [{window.get('name', '微信小程序')}] (尺寸: {int(window['width'])}×{int(window['height'])})")

    # 2. First solve
    curr_max_marks = args.max_marks
    solve_and_display_hud(
        window=window,
        click_through=not args.no_click_through,
        timeout=args.timeout,
        diff_threshold=args.threshold,
        min_area=args.min_area,
        max_marks=curr_max_marks,
    )

    # 3. Interactive loop
    print("\n" + "-" * 60)
    print("🎮 快捷控制：")
    print("   👉 每次玩新关卡：直接按 [回车] 键即刻自动重新识别并圈出！")
    print("   👉 输入 q 并按回车：退出辅助系统")
    print("-" * 60)

    while True:
        try:
            user_input = input("\n👉 按 [回车] 自动识别下一关 (q 退出) > ").strip().lower()
            if user_input in ("q", "quit", "exit"):
                kill_existing_overlays()
                print("👋 已退出辅助系统，游戏愉快！")
                break

            # Re-detect window position in case user moved the window
            curr_window = detect_game_window() or window
            solve_and_display_hud(
                window=curr_window,
                click_through=not args.no_click_through,
                timeout=args.timeout,
                diff_threshold=args.threshold,
                min_area=args.min_area,
                max_marks=curr_max_marks,
            )
        except (KeyboardInterrupt, EOFError):
            kill_existing_overlays()
            print("\n👋 已退出辅助系统。")
            break


if __name__ == "__main__":
    main()
