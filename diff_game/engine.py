from typing import Tuple, List, Optional
import time
import cv2
import numpy as np
from diff_game.models import DifferenceMark, DiffResult


def detect_viewports(image: np.ndarray, split_mode: str = "auto") -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], str]:
    """
    Detects the active game viewports (Reference Panel and Target Panel) within a composite image.
    Handles both cropped game sheets and full mobile screenshots (with status/nav bars).
    Returns: (ref_box, tgt_box, effective_mode) where box is (x, y, width, height).
    """
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 and image.shape[2] == 3 else image.copy()

    # 1. Vertical correlation for tall images (common in mobile phone screenshots)
    if split_mode in ("auto", "vertical") and height > width * 1.2:
        template_h = int(height * 0.15)
        template_y = int(height * 0.25)
        crop_w_margin = int(width * 0.1)
        template = gray[template_y:template_y + template_h, crop_w_margin:width - crop_w_margin]

        search_area = gray[int(height * 0.45):int(height * 0.85), crop_w_margin:width - crop_w_margin]
        res = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        # High confidence vertical periodic match indicates mobile dual-panel layout
        if max_val > 0.75:
            delta_y = int(height * 0.45) + max_loc[1] - template_y

            # Detect sharp frame borders using Sobel Y
            sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
            edge_profile = np.mean(sobel_y[:, crop_w_margin:width - crop_w_margin], axis=1)

            search_start = max(0, template_y - int(height * 0.15))
            search_end = min(height, template_y + int(height * 0.05))
            top_y = search_start + int(np.argmax(edge_profile[search_start:search_end]))

            ref_box = (0, int(top_y), width, int(delta_y))
            tgt_box = (0, int(top_y + delta_y), width, int(delta_y))
            return ref_box, tgt_box, "vertical"

    # 2. Horizontal correlation for wide images
    if split_mode in ("auto", "horizontal") and width > height * 1.5:
        template_w = int(width * 0.15)
        template_x = int(width * 0.25)
        crop_h_margin = int(height * 0.1)
        template = gray[crop_h_margin:height - crop_h_margin, template_x:template_x + template_w]

        search_area = gray[crop_h_margin:height - crop_h_margin, int(width * 0.45):int(width * 0.85)]
        res = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val > 0.75:
            delta_x = int(width * 0.45) + max_loc[0] - template_x

            sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3))
            edge_profile = np.mean(sobel_x[crop_h_margin:height - crop_h_margin, :], axis=0)

            search_start = max(0, template_x - int(width * 0.15))
            search_end = min(width, template_x + int(width * 0.05))
            left_x = search_start + int(np.argmax(edge_profile[search_start:search_end]))

            ref_box = (int(left_x), 0, int(delta_x), height)
            tgt_box = (int(left_x + delta_x), 0, int(delta_x), height)
            return ref_box, tgt_box, "horizontal"

    # 3. Standard 50% split fallback for plain game sheets without extraneous UI
    if (split_mode == "auto" and width > height) or split_mode == "horizontal":
        mid = width // 2
        return (0, 0, mid, height), (mid, 0, width - mid, height), "horizontal"
    else:
        mid = height // 2
        return (0, 0, width, mid), (0, mid, width, height - mid), "vertical"


def split_game_sheet(
    image: np.ndarray, split_mode: str = "auto", return_offsets: bool = False
):
    """
    Extracts panels.
    If return_offsets=False (default): returns (ref_panel, tgt_panel, effective_mode).
    If return_offsets=True: returns (ref_panel, tgt_panel, effective_mode, (ref_x, ref_y), (tgt_x, tgt_y)).
    """
    ref_box, tgt_box, effective_mode = detect_viewports(image, split_mode=split_mode)
    rx, ry, rw, rh = ref_box
    tx, ty, tw, th = tgt_box

    ref = image[ry:ry + rh, rx:rx + rw].copy()
    tgt = image[ty:ty + th, tx:tx + tw].copy()

    # Align dimensions if 1-pixel rounding difference exists
    min_h = min(ref.shape[0], tgt.shape[0])
    min_w = min(ref.shape[1], tgt.shape[1])
    ref = ref[:min_h, :min_w]
    tgt = tgt[:min_h, :min_w]

    if return_offsets:
        return ref, tgt, effective_mode, (rx, ry), (tx, ty)
    return ref, tgt, effective_mode


def apply_circular_nms(marks: List[DifferenceMark], overlap_threshold: float = 1.0) -> List[DifferenceMark]:
    """
    Non-Maximum Suppression for circular difference marks.
    Merges or eliminates sub-marks that fall within or heavily overlap an already confirmed larger mark.
    """
    if not marks:
        return []

    sorted_marks = sorted(marks, key=lambda m: m.area, reverse=True)
    kept: List[DifferenceMark] = []

    for mark in sorted_marks:
        merged = False
        for k in kept:
            dist = np.hypot(mark.center_x - k.center_x, mark.center_y - k.center_y)
            # If centers are within the radius of either mark, they belong to the same difference spot
            if dist < max(k.radius, mark.radius) * overlap_threshold or dist < (k.radius + mark.radius) * 0.65:
                # Expand the larger circle's radius to encompass the merged feature
                k.radius = max(k.radius, int(dist + mark.radius * 0.7))
                k.area += mark.area
                merged = True
                break
        if not merged:
            kept.append(mark)

    kept.sort(key=lambda m: (m.center_y, m.center_x))
    for idx, m in enumerate(kept, start=1):
        m.id = idx

    return kept


def detect_differences(
    ref_panel: np.ndarray,
    tgt_panel: np.ndarray,
    diff_threshold: int = 25,
    min_area: int = 40,
    blur_radius: int = 3,
    border_margin: int = 0,
) -> List[DifferenceMark]:
    """
    Detects difference marks between two aligned panels with noise filtering and circular NMS.
    """
    panel_h, panel_w = ref_panel.shape[:2]

    # Grayscale
    if len(ref_panel.shape) == 3 and ref_panel.shape[2] == 3:
        gray_ref = cv2.cvtColor(ref_panel, cv2.COLOR_BGR2GRAY)
        gray_tgt = cv2.cvtColor(tgt_panel, cv2.COLOR_BGR2GRAY)
    else:
        gray_ref = ref_panel.copy()
        gray_tgt = tgt_panel.copy()

    # Gaussian Blur (adaptive kernel size)
    ksize = max(3, blur_radius * 2 + 1 if blur_radius % 2 == 0 else blur_radius)
    blurred_ref = cv2.GaussianBlur(gray_ref, (ksize, ksize), 0)
    blurred_tgt = cv2.GaussianBlur(gray_tgt, (ksize, ksize), 0)

    # Absolute Difference
    diff = cv2.absdiff(blurred_ref, blurred_tgt)

    # Exclude border seam if specified
    if border_margin > 0 and panel_h > border_margin * 2 and panel_w > border_margin * 2:
        diff_inner = diff[border_margin:panel_h - border_margin, border_margin:panel_w - border_margin]
    else:
        diff_inner = diff
        border_margin = 0

    # Binary Threshold
    _, thresh = cv2.threshold(diff_inner, diff_threshold, 255, cv2.THRESH_BINARY)

    # Morphological Open (filter high-frequency speckles)
    open_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, open_k)

    # Morphological Close (connect fragments adaptively based on resolution)
    close_kernel_size = 15 if max(panel_h, panel_w) > 600 else 7
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_kernel_size, close_kernel_size))
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, close_k)
    dilated = cv2.dilate(closed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_marks: List[DifferenceMark] = []
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area:
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        padded_radius = max(int(radius) + 6, 12)

        actual_cx = int(cx + border_margin)
        actual_cy = int(cy + border_margin)

        raw_marks.append(
            DifferenceMark(
                id=0,
                center_x=actual_cx,
                center_y=actual_cy,
                radius=padded_radius,
                bounding_box=(
                    max(0, int(actual_cx - radius)),
                    max(0, int(actual_cy - radius)),
                    int(2 * radius),
                    int(2 * radius),
                ),
                area=area,
            )
        )

    # Apply Circular NMS to suppress nested redundant marks
    return apply_circular_nms(raw_marks)


def annotate_game_sheet(
    image: np.ndarray,
    split_mode: str,
    differences: List[DifferenceMark],
    ref_offset: Tuple[int, int] = (0, 0),
    tgt_offset: Tuple[int, int] = (0, 0),
) -> np.ndarray:
    """
    Renders symmetric red difference marks on the original image across both viewports.
    """
    annotated = image.copy()
    rx, ry = ref_offset
    tx, ty = tgt_offset

    red_color = (0, 0, 240)
    thickness = 3 if max(image.shape) < 1500 else 4
    font_scale = 0.6 if max(image.shape) < 1500 else 0.9

    for mark in differences:
        # Reference panel annotation
        pt_ref = (rx + mark.center_x, ry + mark.center_y)
        cv2.circle(annotated, pt_ref, mark.radius, red_color, thickness)
        cv2.putText(
            annotated,
            str(mark.id),
            (pt_ref[0] - 10, pt_ref[1] + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            red_color,
            thickness - 1,
        )

        # Target panel annotation
        pt_tgt = (tx + mark.center_x, ty + mark.center_y)
        cv2.circle(annotated, pt_tgt, mark.radius, red_color, thickness)
        cv2.putText(
            annotated,
            str(mark.id),
            (pt_tgt[0] - 10, pt_tgt[1] + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            red_color,
            thickness - 1,
        )

    return annotated


def compare_game_sheet(
    image: np.ndarray,
    split_mode: str = "auto",
    diff_threshold: int = 22,
    min_area: int = 80,
    blur_radius: int = 3,
) -> Tuple[DiffResult, np.ndarray]:
    """
    Main high-level comparison pipeline:
    1. Detects panel viewports (auto-crops status bars if screenshot).
    2. Compares panels with adaptive morphology and NMS.
    3. Annotates symmetric difference marks.
    """
    start_time = time.perf_counter()

    ref_panel, tgt_panel, effective_mode, ref_offset, tgt_offset = split_game_sheet(
        image, split_mode=split_mode, return_offsets=True
    )

    # If mobile screenshot viewport is detected (offset > 50px), ignore outer 20px frame border
    border_margin = 20 if (ref_offset[1] > 50 or ref_offset[0] > 50) else 0

    differences = detect_differences(
        ref_panel=ref_panel,
        tgt_panel=tgt_panel,
        diff_threshold=diff_threshold,
        min_area=min_area,
        blur_radius=blur_radius,
        border_margin=border_margin,
    )

    # Populate global coordinates
    rx, ry = ref_offset
    tx, ty = tgt_offset
    for d in differences:
        d.global_ref_center = (rx + d.center_x, ry + d.center_y)
        d.global_tgt_center = (tx + d.center_x, ty + d.center_y)

    annotated_image = annotate_game_sheet(
        image=image,
        split_mode=effective_mode,
        differences=differences,
        ref_offset=ref_offset,
        tgt_offset=tgt_offset,
    )

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    result = DiffResult(
        split_mode=effective_mode,
        difference_count=len(differences),
        differences=differences,
        execution_time_ms=round(duration_ms, 2),
    )

    return result, annotated_image
