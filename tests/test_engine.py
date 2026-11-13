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
    # Detects 21 non-overlapping differences on test2 demo screenshot
    assert result.difference_count == 21
    assert len(result.differences) == 21

    # Strict non-overlapping rule: no two circles can overlap
    for i in range(len(result.differences)):
        for j in range(i + 1, len(result.differences)):
            d1 = result.differences[i]
            d2 = result.differences[j]
            dist = np.hypot(d1.center_x - d2.center_x, d1.center_y - d2.center_y)
            assert dist >= (d1.radius + d2.radius), f"Circles {d1.id} and {d2.id} overlap!"

    # Verify both panels were annotated
    assert annotated.shape == img.shape
