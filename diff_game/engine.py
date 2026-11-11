from typing import Tuple, List
import time
import cv2
import numpy as np
from diff_game.models import DifferenceMark, DiffResult


def split_game_sheet(image: np.ndarray, split_mode: str = "auto") -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Splits a composite game sheet into (reference_panel, target_panel, effective_mode).
    - If horizontal: reference is left, target is right.
    - If vertical: reference is top, target is bottom.
    """
    height, width = image.shape[:2]

    if split_mode == "auto":
        effective_mode = "horizontal" if width > height else "vertical"
    elif split_mode in ("horizontal", "vertical"):
        effective_mode = split_mode
    else:
        raise ValueError(f"Unsupported split mode: {split_mode}")

    if effective_mode == "horizontal":
        mid = width // 2
        ref = image[:, :mid].copy()
        tgt = image[:, mid:mid * 2].copy()
    else:
        mid = height // 2
        ref = image[:mid, :].copy()
        tgt = image[mid:mid * 2, :].copy()

    # Align shapes if there is 1-pixel rounding difference
    min_h = min(ref.shape[0], tgt.shape[0])
    min_w = min(ref.shape[1], tgt.shape[1])
    ref = ref[:min_h, :min_w]
    tgt = tgt[:min_h, :min_w]

    return ref, tgt, effective_mode


def detect_differences(
    ref_panel: np.ndarray,
    tgt_panel: np.ndarray,
    diff_threshold: int = 25,
    min_area: int = 40,
    blur_radius: int = 3,
) -> List[DifferenceMark]:
    """
    Lightweight classical CV difference detection pipeline:
    1. Grayscale conversion.
    2. Gaussian smoothing to filter high-frequency compression noise.
    3. Absolute difference.
    4. Thresholding to create binary mask.
    5. Morphological closing/dilation to unify fragmented difference spots.
    6. Contour finding & minimum enclosing circle bounding.
    """
    # 1. Grayscale
    if len(ref_panel.shape) == 3 and ref_panel.shape[2] == 3:
        gray_ref = cv2.cvtColor(ref_panel, cv2.COLOR_BGR2GRAY)
        gray_tgt = cv2.cvtColor(tgt_panel, cv2.COLOR_BGR2GRAY)
    else:
        gray_ref = ref_panel.copy()
        gray_tgt = tgt_panel.copy()

    # 2. Gaussian Blur (ensure odd kernel size >= 3)
    ksize = max(3, blur_radius * 2 + 1 if blur_radius % 2 == 0 else blur_radius)
    blurred_ref = cv2.GaussianBlur(gray_ref, (ksize, ksize), 0)
    blurred_tgt = cv2.GaussianBlur(gray_tgt, (ksize, ksize), 0)

    # 3. Absolute Difference
    diff = cv2.absdiff(blurred_ref, blurred_tgt)

    # 4. Binary Threshold
    _, thresh = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)

    # 5. Morphological filtering:
    # First open to remove tiny isolated noise specks (< 3x3)
    open_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, open_k)

    # Then close and slightly dilate to unify fragmented difference spots
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, close_k)
    dilated = cv2.dilate(closed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)

    # 6. Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    marks: List[DifferenceMark] = []
    mark_id = 1

    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area:
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        x, y, w, h = cv2.boundingRect(cnt)

        # Apply slight padding to radius for comfortable visualization
        padded_radius = max(int(radius) + 6, 12)

        marks.append(
            DifferenceMark(
                id=mark_id,
                center_x=int(cx),
                center_y=int(cy),
                radius=padded_radius,
                bounding_box=(int(x), int(y), int(w), int(h)),
                area=area,
            )
        )
        mark_id += 1

    # Sort marks top-to-bottom, left-to-right
    marks.sort(key=lambda m: (m.center_y, m.center_x))
    # Re-index nicely
    for idx, m in enumerate(marks, start=1):
        m.id = idx

    return marks


def annotate_game_sheet(
    image: np.ndarray,
    split_mode: str,
    differences: List[DifferenceMark],
) -> np.ndarray:
    """
    Renders symmetric red difference marks on both Reference and Target panels.
    """
    annotated = image.copy()
    height, width = image.shape[:2]

    if split_mode == "horizontal":
        offset_x = width // 2
        offset_y = 0
    else:
        offset_x = 0
        offset_y = height // 2

    # Draw divider line (seam) for visual clarity
    line_color = (0, 200, 255)  # Gold/amber divider
    if split_mode == "horizontal":
        cv2.line(annotated, (offset_x, 0), (offset_x, height), line_color, 2)
    else:
        cv2.line(annotated, (0, offset_y), (width, offset_y), line_color, 2)

    # Red color in BGR: (0, 0, 240)
    red_color = (0, 0, 240)
    thickness = 3

    for mark in differences:
        # Reference panel (left or top)
        pt_ref = (mark.center_x, mark.center_y)
        cv2.circle(annotated, pt_ref, mark.radius, red_color, thickness)
        cv2.putText(
            annotated,
            str(mark.id),
            (mark.center_x - 6, mark.center_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            red_color,
            2,
        )

        # Target panel (right or bottom)
        pt_tgt = (mark.center_x + offset_x, mark.center_y + offset_y)
        cv2.circle(annotated, pt_tgt, mark.radius, red_color, thickness)
        cv2.putText(
            annotated,
            str(mark.id),
            (mark.center_x + offset_x - 6, mark.center_y + offset_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            red_color,
            2,
        )

    return annotated


def compare_game_sheet(
    image: np.ndarray,
    split_mode: str = "auto",
    diff_threshold: int = 25,
    min_area: int = 40,
    blur_radius: int = 3,
) -> Tuple[DiffResult, np.ndarray]:
    """
    High-level facade: splits sheet, spots differences, and annotates result.
    """
    start_time = time.perf_counter()

    ref_panel, tgt_panel, effective_mode = split_game_sheet(image, split_mode=split_mode)

    differences = detect_differences(
        ref_panel=ref_panel,
        tgt_panel=tgt_panel,
        diff_threshold=diff_threshold,
        min_area=min_area,
        blur_radius=blur_radius,
    )

    annotated_image = annotate_game_sheet(image, effective_mode, differences)

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    result = DiffResult(
        split_mode=effective_mode,
        difference_count=len(differences),
        differences=differences,
        execution_time_ms=round(duration_ms, 2),
    )

    return result, annotated_image
