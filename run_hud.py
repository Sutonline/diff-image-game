#!/usr/bin/env python3
"""
Spot The Difference - WeChat Mini Program In-Place Transparent HUD Runner.
一键微信小游戏原位找茬辅助工具（原生透明覆盖层 · 点击穿透）
"""

import sys
import argparse
import diff_game.hud as hud_state
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
        default=18,
        help="LAB 色差敏感度阈值（默认 18）",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=12,
        help="最小连通像素过滤噪点（归一化 600px 宽下默认 12 px²）",
    )
    parser.add_argument(
        "--max-marks",
        type=int,
        default=0,
        help="差异数量上限（默认 0 表示全量自动检出，不人为截断）",
    )
    parser.add_argument(
        "--extra-marks",
        "-e",
        type=int,
        default=0,
        help="差异数量相对增减偏移（例如 +5 或 -2）",
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
    curr_extra_marks = args.extra_marks
    use_fixed = args.fixed
    skipped = []  # candidates the game did not accept, in reference-panel coords
    solve_and_display_hud(
        window=window,
        click_through=not args.no_click_through,
        timeout=args.timeout,
        diff_threshold=args.threshold,
        min_area=args.min_area,
        max_marks=curr_max_marks,
        extra_marks=curr_extra_marks,
        use_fixed_wechat=use_fixed,
    )

    # 3. Interactive loop
    print("\n" + "-" * 60)
    print("🎮 快捷控制：")
    print("   👉 每次玩新关卡：直接按 [回车] 键即刻识别并圈出！")
    print("   👉 增加识别差异：输入 +5 (或 +N) 并回车，在原标记数量基础上追加识别重试")
    print("   👉 减少识别差异：输入 -5 (或 -N) 并回车，剔除置信度较低的微小差异")
    print("   👉 指定目标数量：输入具体数字如 20 并回车，强制提取 Top 20 差异")
    print("   👉 重置增减数量：输入 r 或 0 并回车，重置为标准默认识别")
    print("   👉 切换写死框位：输入 f 并回车，锁定默认小程序标准窗口红框 (353×690 pt)")
    print("   👉 恢复动态识别：输入 a 并回车，恢复全自动算法自适应检测")
    print("   👉 红圈不被游戏认可：输入 n 并回车，跳过当前红圈、换下一个候选（可连续使用）")
    print("   👉 退出辅助系统：输入 q 并回车")
    print("-" * 60)

    while True:
        try:
            mode_desc = "固定写死框" if use_fixed else "动态算法"
            extra_desc = f", 增量: {curr_extra_marks:+d}" if curr_extra_marks != 0 else ""
            max_desc = f", 指定目标: {curr_max_marks}" if curr_max_marks > 0 else ""
            skip_desc = f", 已跳过: {len(skipped)}" if skipped else ""
            prompt = f"\n👉 [{mode_desc}{extra_desc}{max_desc}{skip_desc}] 回车识别 (n 换一个, +5/-5 调数量, r 重置, q 退出) > "
            user_input = input(prompt).strip().lower()
            if user_input in ("q", "quit", "exit"):
                kill_existing_overlays()
                print("👋 已退出辅助系统，游戏愉快！")
                break

            curr_window = detect_game_window() or window
            if user_input not in ("n", "next"):
                skipped = []

            if user_input in ("f", "fixed"):
                use_fixed = True
                print("🔒 已切换为：默认标准窗口写死红框模式 (353×690 pt)")
            elif user_input in ("a", "auto"):
                use_fixed = False
                print("🔍 已切换为：全自动算法自适应识别红框模式")
            elif user_input.startswith("+"):
                suffix = user_input[1:].strip()
                delta = int(suffix) if suffix.isdigit() else 5
                curr_extra_marks += delta
                print(f"📈 增加差异识别数量: +{delta} (当前累计增量: {curr_extra_marks:+d})")
            elif user_input.startswith("-"):
                suffix = user_input[1:].strip()
                delta = int(suffix) if suffix.isdigit() else 5
                curr_extra_marks -= delta
                print(f"📉 减少差异识别数量: -{delta} (当前累计增量: {curr_extra_marks:+d})")
            elif user_input in ("n", "next"):
                if len(hud_state.LAST_SHOWN_MARKS) > 3:
                    print("ℹ️ 当前红圈较多，无法判断是哪一个不被认可。请先把红圈都点一遍，再按回车进入第二轮（只显示剩余差异）后使用 n")
                    continue
                if hud_state.LAST_SHOWN_MARKS:
                    skipped.extend(hud_state.LAST_SHOWN_MARKS)
                    print(f"⏭️  已跳过 {len(hud_state.LAST_SHOWN_MARKS)} 个不被认可的红圈，寻找下一个候选 (本关累计跳过 {len(skipped)} 个)")
                else:
                    print("ℹ️ 当前没有可跳过的红圈")
            elif user_input in ("r", "reset", "0"):
                curr_extra_marks = 0
                curr_max_marks = 0
                print("🔄 已重置差异数量限制 (恢复默认/自动读取?号)")
            elif user_input.isdigit():
                curr_max_marks = int(user_input)
                curr_extra_marks = 0
                print(f"🎯 已指定本关目标差异数量: {curr_max_marks}")

            solve_and_display_hud(
                window=curr_window,
                click_through=not args.no_click_through,
                timeout=args.timeout,
                diff_threshold=args.threshold,
                min_area=args.min_area,
                max_marks=curr_max_marks,
                extra_marks=curr_extra_marks,
                use_fixed_wechat=use_fixed,
                skip_circles=skipped or None,
            )
        except (KeyboardInterrupt, EOFError):
            kill_existing_overlays()
            print("\n👋 已退出辅助系统。")
            break


if __name__ == "__main__":
    main()
