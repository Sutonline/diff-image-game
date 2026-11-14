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
    launch_calibration_hud,
    list_wechat_windows,
    kill_existing_overlays,
)
from diff_game.config import (
    load_viewport_config,
    clear_viewport_config,
    get_viewport_config_path,
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
    parser.add_argument(
        "--fixed",
        "-f",
        action="store_true",
        help="锁定微信小程序默认标准窗口 (353×690 pt) 固定红框位置，跳过动态检测",
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
    use_fixed = args.fixed
    solve_and_display_hud(
        window=window,
        click_through=not args.no_click_through,
        timeout=args.timeout,
        diff_threshold=args.threshold,
        min_area=args.min_area,
        max_marks=curr_max_marks,
        use_fixed_wechat=use_fixed,
    )

    # 3. Interactive loop
    print("\n" + "-" * 60)
    print("🎮 快捷控制：")
    print("   👉 每次玩新关卡：直接按 [回车] 键即刻识别并圈出！")
    print("   👉 切换写死框位：输入 f 并按回车，锁定默认小程序标准窗口红框 (353×690 pt)")
    print("   👉 恢复动态识别：输入 a 并按回车，恢复全自动算法自适应检测")
    print("   👉 退出辅助系统：输入 q 并按回车")
    print("-" * 60)

    while True:
        try:
            mode_desc = "固定写死框" if use_fixed else "动态算法"
            prompt = f"\n👉 [当前模式: {mode_desc}] 按 [回车] 识别关卡 (f 切换写死框, a 切换自适应, q 退出) > "
            user_input = input(prompt).strip().lower()
            if user_input in ("q", "quit", "exit"):
                kill_existing_overlays()
                print("👋 已退出辅助系统，游戏愉快！")
                break

            curr_window = detect_game_window() or window

            if user_input in ("f", "fixed"):
                use_fixed = True
                print("🔒 已切换为：默认标准窗口写死红框模式 (353×690 pt)")
            elif user_input in ("a", "auto"):
                use_fixed = False
                print("🔍 已切换为：全自动算法自适应识别红框模式")

            solve_and_display_hud(
                window=curr_window,
                click_through=not args.no_click_through,
                timeout=args.timeout,
                diff_threshold=args.threshold,
                min_area=args.min_area,
                max_marks=curr_max_marks,
                use_fixed_wechat=use_fixed,
            )
        except (KeyboardInterrupt, EOFError):
            kill_existing_overlays()
            print("\n👋 已退出辅助系统。")
            break


if __name__ == "__main__":
    main()
