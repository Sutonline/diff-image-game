import cv2
import numpy as np
import pytest
from diff_game.engine import split_game_sheet


def test_split_game_sheet_horizontal_auto():
    # A wide image (800x400), should split horizontally into left (reference) and right (target)
    img = np.zeros((400, 800, 3), dtype=np.uint8)
    img[:, :400] = 100  # Left panel
    img[:, 400:] = 200  # Right panel

    ref, tgt, mode = split_game_sheet(img, split_mode="auto")
    assert mode == "horizontal"
    assert ref.shape == (400, 400, 3)
    assert tgt.shape == (400, 400, 3)
    assert np.all(ref == 100)
    assert np.all(tgt == 200)


def test_split_game_sheet_vertical_auto():
    # A tall image (400x800), should split vertically into top (reference) and bottom (target)
    img = np.zeros((800, 400, 3), dtype=np.uint8)
    img[:400, :] = 50   # Top panel
    img[400:, :] = 150  # Bottom panel

    ref, tgt, mode = split_game_sheet(img, split_mode="auto")
    assert mode == "vertical"
    assert ref.shape == (400, 400, 3)
    assert tgt.shape == (400, 400, 3)
    assert np.all(ref == 50)
    assert np.all(tgt == 150)


def test_split_game_sheet_manual_override():
    # A square image (400x400) forced to horizontal
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    ref, tgt, mode = split_game_sheet(img, split_mode="horizontal")
    assert mode == "horizontal"
    assert ref.shape == (400, 200, 3)
    assert tgt.shape == (400, 200, 3)


def test_detect_differences_identical():
    from diff_game.engine import detect_differences
    panel = np.ones((200, 200, 3), dtype=np.uint8) * 128
    diffs = detect_differences(panel, panel)
    assert len(diffs) == 0


def test_detect_differences_single_anomaly():
    from diff_game.engine import detect_differences
    ref = np.ones((200, 200, 3), dtype=np.uint8) * 128
    tgt = ref.copy()
    # Draw a prominent white rectangle on target at (50, 50) of size 30x30 (area 900)
    cv2.rectangle(tgt, (50, 50), (80, 80), (255, 255, 255), -1)

    diffs = detect_differences(ref, tgt, diff_threshold=25, min_area=50)
    assert len(diffs) == 1
    d = diffs[0]
    # Check center is near (65, 65)
    assert abs(d.center_x - 65) <= 5
    assert abs(d.center_y - 65) <= 5
    assert d.area >= 800


def test_detect_differences_filters_noise():
    from diff_game.engine import detect_differences
    ref = np.ones((600, 600, 3), dtype=np.uint8) * 128
    tgt = ref.copy()
    # Draw a 2x2 tiny noise speck (area 4 in normalized 600px space)
    tgt[50:52, 50:52] = 255

    diffs = detect_differences(ref, tgt, diff_threshold=25, min_area=30)
    assert len(diffs) == 0


def test_compare_game_sheet_end_to_end():
    from diff_game.engine import compare_game_sheet
    # 400x200 composite (horizontal)
    composite = np.ones((200, 400, 3), dtype=np.uint8) * 128
    # Add difference on right panel (x=300, y=100)
    cv2.circle(composite, (300, 100), 15, (0, 0, 255), -1)

    result, annotated = compare_game_sheet(composite, split_mode="auto", min_area=50)
    assert result.difference_count == 1
    assert annotated.shape == composite.shape
    # Check that red circles were drawn on both left panel and right panel
    # Left panel (x=100, y=100) should now have red annotations
    # Red is (0, 0, 255) in BGR
    assert np.any(annotated[:, :200, 2] > 200)
    assert np.any(annotated[:, 200:, 2] > 200)


def test_merge_overlapping_circles_single_balloon():
    from diff_game.models import DifferenceMark
    from diff_game.engine import merge_overlapping_circles

    # Two overlapping difference marks (e.g. top and bottom of hot air balloon)
    m1 = DifferenceMark(
        id=1,
        center_x=1027,
        center_y=246,
        radius=50,
        bounding_box=(977, 196, 100, 100),
        area=1200.0,
    )
    m2 = DifferenceMark(
        id=2,
        center_x=1122,
        center_y=304,
        radius=62,
        bounding_box=(1060, 242, 124, 124),
        area=5000.0,
    )
    # Distance is ~111.3, r1 + r2 = 112 -> they overlap
    merged = merge_overlapping_circles([m1, m2], buffer_ratio=1.0)
    assert len(merged) == 1
    m = merged[0]
    assert m.id == 1
    # Bounding circle must encompass both original centers + radii
    d1 = np.hypot(m.center_x - m1.center_x, m.center_y - m1.center_y)
    d2 = np.hypot(m.center_x - m2.center_x, m.center_y - m2.center_y)
    assert d1 + m1.radius <= m.radius + 1
    assert d2 + m2.radius <= m.radius + 1


# (path, total badge slots, marks expected on this capture)
# Captures taken mid-level show the game's green rings around already-found differences;
# those are skipped, so only the remaining '?' slots get marks.
SCREENSHOT_CASES = [
    ("assets/demo_original.jpg", 20, 20),
    # Desktop WeChat window capture; panels are offset by a sub-pixel amount after window scaling. 4 found.
    ("tests/fixtures/lv60_window.png", 20, 16),
    # 19 found; the one left is a faint dark speaker on a dark wall. Ceiling light streaks must not count.
    ("tests/fixtures/lv64_window.png", 20, 1),
]


@pytest.mark.parametrize("rel_path,expected_count,expected_marks", SCREENSHOT_CASES)
def test_spot_difference_on_real_mobile_screenshot(rel_path, expected_count, expected_marks):
    from pathlib import Path
    from diff_game.engine import compare_game_sheet, detect_target_differences_count

    img_path = Path(__file__).parent.parent / rel_path
    if not img_path.exists():
        pytest.skip(f"Repository fixture {rel_path} not found")

    img = cv2.imread(str(img_path))
    assert detect_target_differences_count(img) == expected_count

    result, annotated = compare_game_sheet(img)
    assert result.target_badge_count == expected_count
    assert result.difference_count == expected_marks
    assert len(result.differences) == expected_marks
    assert [d.id for d in result.differences] == list(range(1, expected_marks + 1))
    assert annotated.shape == img.shape


def test_compare_game_sheet_max_differences_limit():
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    demo_img_path = Path(__file__).parent.parent / "assets" / "demo_original.jpg"
    if not demo_img_path.exists():
        pytest.skip("Repository demo fixture assets/demo_original.jpg not found")

    img = cv2.imread(str(demo_img_path))
    result, _ = compare_game_sheet(img, max_differences=10)
    assert result.difference_count == 10
    assert len(result.differences) == 10
    # Verified IDs are sequential 1..10
    assert [d.id for d in result.differences] == list(range(1, 11))


def test_detect_differences_empty_panel_safety():
    from diff_game.engine import detect_differences
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert detect_differences(empty, empty) == []
    assert detect_differences(None, None) == []


def test_compare_game_sheet_invalid_custom_boxes():
    from diff_game.engine import compare_game_sheet
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    # 0-sized boxes
    result, _ = compare_game_sheet(img, custom_boxes=((0, 0, 0, 0), (0, 0, 0, 0)))
    assert result.difference_count == 0
    assert result.differences == []


def test_detect_viewports_fixed_wechat():
    from diff_game.engine import detect_viewports
    # Standard WeChat mini program window resolution (706 x 1380)
    fake_screen = np.zeros((1380, 706, 3), dtype=np.uint8)
    ref_b, tgt_b, mode = detect_viewports(fake_screen, use_fixed_wechat=True)
    assert mode == "vertical"
    assert ref_b[0] == int(706 * 0.038)
    assert ref_b[2] == int(706 * 0.924)
    assert ref_b[3] == int(1380 * 0.321)
    assert tgt_b[1] == int(1380 * 0.559)


def test_align_panels_content_different_widths():
    from diff_game.engine import align_panels_content

    # Create synthetic panel with width 300 and target panel with width 290 (10px difference)
    ref = np.ones((200, 300, 3), dtype=np.uint8) * 100
    tgt = np.ones((200, 290, 3), dtype=np.uint8) * 100

    # Draw identical pattern in center of both
    cv2.rectangle(ref, (100, 50), (180, 150), (255, 0, 0), -1)
    cv2.rectangle(tgt, (95, 50), (175, 150), (255, 0, 0), -1)

    aligned_ref, aligned_tgt, ref_offset, tgt_offset = align_panels_content(ref, tgt)
    assert aligned_ref.shape == aligned_tgt.shape
    assert aligned_ref.shape[1] > 250


def test_detect_differences_preserves_fine_accessories():
    from diff_game.engine import detect_differences

    # Create a 200x200 panel
    ref = np.ones((200, 200, 3), dtype=np.uint8) * 120
    tgt = np.ones((200, 200, 3), dtype=np.uint8) * 120

    # Draw a thin watch/bracelet difference (width 25, height 6)
    cv2.rectangle(ref, (80, 97), (105, 103), (40, 40, 220), -1)

    diffs = detect_differences(ref, tgt, diff_threshold=14, min_area=25)
    assert len(diffs) == 1
    d = diffs[0]
    assert 80 <= d.center_x <= 105
    assert 95 <= d.center_y <= 105
    assert d.area >= 25


def test_detect_target_differences_count():
    from diff_game.engine import detect_target_differences_count

    # Non-tall or empty images should return None
    assert detect_target_differences_count(None) is None
    assert detect_target_differences_count(np.zeros((100, 100, 3), dtype=np.uint8)) is None

    # Synthetic tall image (w=700, h=1400) with a horizontal row of 10 circles in the badge strip (y=210..364)
    h, w = 1400, 700
    img = np.ones((h, w, 3), dtype=np.uint8) * 200
    badge_y = int(h * 0.21)  # ~294
    r = 16
    start_x = 100
    spacing = 50
    count = 10
    for i in range(count):
        cx = start_x + i * spacing
        cv2.circle(img, (cx, badge_y), r, (50, 50, 50), 2)
        cv2.putText(img, "?", (cx - 5, badge_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 50), 1)

    detected = detect_target_differences_count(img)
    assert detected == count


def test_compare_game_sheet_with_extra_differences():
    from diff_game.engine import compare_game_sheet

    # Create synthetic image with 2 vertical panels and 10 widely spaced spot differences
    h, w = 600, 300
    sheet = np.ones((h, w, 3), dtype=np.uint8) * 150
    # Add 10 differences in the top panel (y in 20..280, x in 30..270)
    points = [
        (40, 40), (100, 40), (160, 40), (220, 40),
        (40, 100), (100, 100), (160, 100), (220, 100),
        (40, 160), (100, 160)
    ]
    for px, py in points:
        cv2.circle(sheet, (px, py), 6, (0, 0, 255), -1)

    # Base test with max_differences=5
    res_base, _ = compare_game_sheet(sheet, max_differences=5, extra_differences=0)
    assert res_base.difference_count == 5

    # Test +3 extra differences -> 8
    res_plus, _ = compare_game_sheet(sheet, max_differences=5, extra_differences=3)
    assert res_plus.difference_count == 8

    # Test -2 extra differences -> 3
    res_minus, _ = compare_game_sheet(sheet, max_differences=5, extra_differences=-2)
    assert res_minus.difference_count == 3


def test_detect_differences_lowers_threshold_when_under_target():
    from diff_game.engine import detect_differences

    ref = np.ones((600, 600, 3), dtype=np.uint8) * 128
    tgt = ref.copy()
    # Two high-contrast differences and one subtle difference (LAB delta E ~12 < 18)
    cv2.circle(tgt, (150, 150), 15, (255, 255, 255), -1)
    cv2.circle(tgt, (300, 150), 15, (255, 255, 255), -1)
    cv2.circle(tgt, (450, 150), 15, (140, 140, 140), -1)

    # Without target_count, default threshold=18 only finds the 2 strong differences
    diffs_default = detect_differences(ref, tgt, diff_threshold=18)
    assert len(diffs_default) == 2

    # With target_count=3, threshold is lowered automatically to find all 3
    diffs_target = detect_differences(ref, tgt, diff_threshold=18, target_count=3)
    assert len(diffs_target) == 3


def test_lv60_marks_stay_object_sized():
    """Regression: sub-pixel panel offset used to flood the diff map and merge into panel-sized circles."""
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    img_path = Path(__file__).parent / "fixtures" / "lv60_window.png"
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    result, _ = compare_game_sheet(img)
    panel_w = result.ref_box[2]
    assert result.difference_count == 16
    assert all(d.radius <= panel_w * 0.15 for d in result.differences)


def test_lv64_finds_faint_speaker_and_ignores_ceiling_streaks():
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    img_path = Path(__file__).parent / "fixtures" / "lv64_window.png"
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    result, _ = compare_game_sheet(img)
    rx, ry, rw, rh = result.ref_box
    centers = [(d.global_ref_center[0] - rx, d.global_ref_center[1] - ry) for d in result.differences]
    # Speaker to the right of the boy's head (panel coords ~ (485, 205))
    assert any(abs(x - 485) < 30 and abs(y - 205) < 30 for x, y in centers)
    # Nothing on the ceiling light strip (panel y < 60, between the side shelves)
    assert not any(y < 60 and 120 < x < 480 for x, y in centers)


@pytest.mark.parametrize("rel_path,total,found", [
    ("assets/demo_original.jpg", 20, 0),
    ("tests/fixtures/lv60_window.png", 20, 4),
    ("tests/fixtures/lv64_window.png", 20, 19),
])
def test_badge_status_and_found_rings(rel_path, total, found):
    """Checked badges are counted as found, and exactly that many green rings are detected
    in the artwork (grass, foliage and green clothing must not be mistaken for rings)."""
    from pathlib import Path
    from diff_game.engine import detect_badge_status, detect_found_rings, detect_viewports

    img_path = Path(__file__).parent.parent / rel_path
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    assert detect_badge_status(img) == (total, found)
    (x, y, w, h), _, _ = detect_viewports(img)
    assert len(detect_found_rings(img[y:y + h, x:x + w])) == found


@pytest.mark.parametrize("rel_path", ["tests/fixtures/lv60_window.png", "tests/fixtures/lv64_window.png"])
def test_second_round_never_marks_inside_green_rings(rel_path):
    from pathlib import Path
    from diff_game.engine import compare_game_sheet, detect_found_rings

    img_path = Path(__file__).parent.parent / rel_path
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    result, _ = compare_game_sheet(img)
    rx, ry, rw, rh = result.ref_box
    rings = detect_found_rings(img[ry:ry + rh, rx:rx + rw])
    for d in result.differences:
        px, py = d.global_ref_center[0] - rx, d.global_ref_center[1] - ry
        assert all(np.hypot(px - cx, py - cy) > r for cx, cy, r in rings)


def test_all_found_returns_no_marks():
    """When every badge is checked, nothing is left to mark."""
    from unittest.mock import patch
    from pathlib import Path

    img_path = Path(__file__).parent / "fixtures" / "lv64_window.png"
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    from diff_game import engine
    with patch.object(engine, "detect_badge_status", return_value=(19, 19)):
        result, _ = engine.compare_game_sheet(img)
    assert result.difference_count == 0


def test_fragment_just_outside_found_ring_is_not_a_new_difference():
    """Lv-74: the game's green ring did not fully enclose a found difference; the part sticking
    out just past the ring edge must not be offered as the remaining difference."""
    from diff_game.engine import detect_differences

    ref = np.ones((300, 600, 3), dtype=np.uint8) * 128
    tgt = ref.copy()
    # A tall object change: mostly inside a ring at (150, 160) r=40, with its tip poking out above.
    cv2.rectangle(tgt, (140, 105), (160, 190), (255, 255, 255), -1)
    # A separate, genuine remaining difference far away.
    cv2.circle(tgt, (450, 150), 15, (0, 0, 255), -1)

    marks = detect_differences(ref, tgt, target_count=1, exclude_circles=[(150.0, 160.0, 40.0)])
    assert len(marks) == 1
    assert abs(marks[0].center_x - 450) <= 10 and abs(marks[0].center_y - 150) <= 10


def test_skip_circles_moves_to_next_candidate():
    """'n' in the HUD: a candidate the game rejected is skipped and is never shown again."""
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    img_path = Path(__file__).parent / "fixtures" / "lv64_window.png"
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    first, _ = compare_game_sheet(img)
    assert first.difference_count == 1
    shown = first.differences[0]
    second, _ = compare_game_sheet(img, skip_circles=[(shown.center_x, shown.center_y, shown.radius)])
    for d in second.differences:
        assert np.hypot(d.center_x - shown.center_x, d.center_y - shown.center_y) > shown.radius


def test_lv74_single_character_change_on_couplet():
    """Lv-74, second round (14 of 15 found). The remaining difference is one character on the
    couplet (好男人 -> 坏男人): same ink colour, only the strokes differ, so colour difference misses
    it and the shape-change fallback must find it. The fragment of a found difference poking out
    above the large ring on the left must not be offered.
    (Fixture was captured with the HUD overlay visible; its panel labels were made identical.)"""
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    img_path = Path(__file__).parent / "fixtures" / "lv74_window_hud.png"
    if not img_path.exists():
        pytest.skip("fixture missing")
    img = cv2.imread(str(img_path))
    result, _ = compare_game_sheet(img)
    assert result.target_badge_count == 15
    assert result.found_count == 14
    assert result.difference_count == 1
    d = result.differences[0]
    assert abs(d.center_x - 368) <= 15 and abs(d.center_y - 61) <= 15

