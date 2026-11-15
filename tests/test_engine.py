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
    ref = np.ones((200, 200, 3), dtype=np.uint8) * 128
    tgt = ref.copy()
    # Draw a 2x2 tiny noise speck (area 4)
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


def test_spot_difference_on_real_mobile_screenshot():
    from pathlib import Path
    from diff_game.engine import compare_game_sheet

    demo_img_path = Path(__file__).parent.parent / "assets" / "demo_original.jpg"
    if not demo_img_path.exists():
        pytest.skip("Repository demo fixture assets/demo_original.jpg not found")

    img = cv2.imread(str(demo_img_path))
    result, annotated = compare_game_sheet(img)
    # Detects non-overlapping differences on test2 demo screenshot
    assert 14 <= result.difference_count <= 35
    assert 14 <= len(result.differences) <= 35

    # Strict non-overlapping rule: no two circles can overlap
    for i in range(len(result.differences)):
        for j in range(i + 1, len(result.differences)):
            d1 = result.differences[i]
            d2 = result.differences[j]
            dist = np.hypot(d1.center_x - d2.center_x, d1.center_y - d2.center_y)
            assert dist >= (d1.radius + d2.radius), f"Circles {d1.id} and {d2.id} overlap!"

    # Verify both panels were annotated
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




