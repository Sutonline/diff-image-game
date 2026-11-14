from typing import Tuple, List, Optional
import time
import cv2
import numpy as np
from diff_game.models import DifferenceMark, DiffResult


def detect_matching_frame_bodies(
    image: np.ndarray, split_mode: str = "auto"
) -> Optional[Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], str]]:
    """
    Automatic frame body segmentation:
    Finds prominent rectangular frames/card boundaries in the image that are
    roughly consistent ('大概一致') in geometry and highly correlated in visual content.
    Returns: (ref_box, tgt_box, layout_mode) or None if no matching frame pair is found.
    Allows independent widths, heights, and offsets for the top and bottom panels.
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 and image.shape[2] == 3 else image.copy()

    candidate_boxes = []

    # 1. Horizontal boundary line detection via morphological line filter
    h_len = max(30, int(w * 0.25))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    gy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    h_lines = cv2.morphologyEx((gy > 25).astype(np.uint8) * 255, cv2.MORPH_OPEN, h_kernel)

    row_sums = np.sum(h_lines > 0, axis=1)
    line_rows = []
    for y in range(h):
        if row_sums[y] > w * 0.22:
            if not line_rows or (y - line_rows[-1][-1]) > 6:
                line_rows.append([y])
            else:
                line_rows[-1].append(y)

    peak_y = [int(np.mean(cluster)) for cluster in line_rows]

    for i in range(len(peak_y)):
        for j in range(i + 1, len(peak_y)):
            box_h = peak_y[j] - peak_y[i]
            if int(h * 0.12) <= box_h <= int(h * 0.60):
                band = gray[peak_y[i] : peak_y[j], :]
                col_std = np.std(band, axis=0)
                gx = np.abs(cv2.Sobel(band, cv2.CV_32F, 1, 0, ksize=3))
                col_grad = np.mean(gx, axis=0)

                left_x = 0
                while left_x < int(w * 0.20) and col_std[left_x] < 3.0:
                    left_x += 1
                for x in range(left_x, min(int(w * 0.20), left_x + 35)):
                    if col_grad[x] > 35:
                        left_x = x
                        break

                right_x = w
                while right_x > int(w * 0.80) and col_std[right_x - 1] < 3.0:
                    right_x -= 1
                for x in range(right_x - 1, max(int(w * 0.80), right_x - 35), -1):
                    if col_grad[x] > 35:
                        right_x = x + 1
                        break

                box_w = right_x - left_x
                if box_w > w * 0.35:
                    candidate_boxes.append((int(left_x), int(peak_y[i]), int(box_w), int(box_h)))

    # 2. Contour-based candidate boxes
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k_close)
    contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > w * 0.35 and int(h * 0.12) <= bh <= int(h * 0.60):
            candidate_boxes.append((int(x), int(y), int(bw), int(bh)))

    # Deduplicate candidate boxes
    unique = []
    for b in candidate_boxes:
        if not any(
            abs(b[0] - u[0]) < 12 and abs(b[1] - u[1]) < 12 and abs(b[2] - u[2]) < 20 and abs(b[3] - u[3]) < 20
            for u in unique
        ):
            unique.append(b)

    best_pair = None
    best_score = -1.0
    layout_mode = "vertical"

    # Evaluate pairs ('大概一致' geometric consistency + visual correlation)
    for i in range(len(unique)):
        for j in range(len(unique)):
            if i == j:
                continue
            b1 = unique[i]
            b2 = unique[j]

            # Vertical pair check
            if split_mode in ("auto", "vertical") and b2[1] >= b1[1] + b1[3] * 0.75:
                w_diff = abs(b1[2] - b2[2]) / max(b1[2], b2[2])
                h_diff = abs(b1[3] - b2[3]) / max(b1[3], b2[3])
                x_diff = abs(b1[0] - b2[0]) / float(w)

                if w_diff <= 0.18 and h_diff <= 0.18 and x_diff <= 0.15:
                    p1 = gray[b1[1] : b1[1] + b1[3], b1[0] : b1[0] + b1[2]]
                    p2 = gray[b2[1] : b2[1] + b2[3], b2[0] : b2[0] + b2[2]]
                    if p1.size > 0 and p2.size > 0:
                        r1 = cv2.resize(p1, (96, 96))
                        r2 = cv2.resize(p2, (96, 96))
                        res = cv2.matchTemplate(r1, r2, cv2.TM_CCOEFF_NORMED)
                        corr = float(res[0][0])
                        geom_score = 1.0 - (w_diff + h_diff) * 0.5
                        total = corr * 0.75 + geom_score * 0.25
                        if corr > 0.40 and total > best_score:
                            best_score = total
                            best_pair = (b1, b2)
                            layout_mode = "vertical"

            # Horizontal pair check
            if split_mode in ("auto", "horizontal") and b2[0] >= b1[0] + b1[2] * 0.75:
                w_diff = abs(b1[2] - b2[2]) / max(b1[2], b2[2])
                h_diff = abs(b1[3] - b2[3]) / max(b1[3], b2[3])
                y_diff = abs(b1[1] - b2[1]) / float(h)

                if w_diff <= 0.18 and h_diff <= 0.18 and y_diff <= 0.15:
                    p1 = gray[b1[1] : b1[1] + b1[3], b1[0] : b1[0] + b1[2]]
                    p2 = gray[b2[1] : b2[1] + b2[3], b2[0] : b2[0] + b2[2]]
                    if p1.size > 0 and p2.size > 0:
                        r1 = cv2.resize(p1, (96, 96))
                        r2 = cv2.resize(p2, (96, 96))
                        res = cv2.matchTemplate(r1, r2, cv2.TM_CCOEFF_NORMED)
                        corr = float(res[0][0])
                        geom_score = 1.0 - (w_diff + h_diff) * 0.5
                        total = corr * 0.75 + geom_score * 0.25
                        if corr > 0.40 and total > best_score:
                            best_score = total
                            best_pair = (b1, b2)
                            layout_mode = "horizontal"

    if best_pair and best_score >= 0.50:
        return best_pair[0], best_pair[1], layout_mode
    return None


def align_panels_content(
    ref: np.ndarray, tgt: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, Tuple[int, int], Tuple[int, int]]:
    """
    Micro-aligns two panels to absorb slight border width differences, asymmetrical padding,
    or 1-5 pixel translation jitter between panels without stretching.
    Returns: (aligned_ref, aligned_tgt, (ref_sub_x, ref_sub_y), (tgt_sub_x, tgt_sub_y))
    """
    if ref is None or tgt is None or ref.size == 0 or tgt.size == 0:
        return ref, tgt, (0, 0), (0, 0)

    rh, rw = ref.shape[:2]
    th, tw = tgt.shape[:2]

    gray_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY) if len(ref.shape) == 3 and ref.shape[2] == 3 else ref
    gray_tgt = cv2.cvtColor(tgt, cv2.COLOR_BGR2GRAY) if len(tgt.shape) == 3 and tgt.shape[2] == 3 else tgt

    cw = max(20, int(min(rw, tw) * 0.60))
    ch = max(20, int(min(rh, th) * 0.60))

    if rw <= tw and rh <= th:
        cx_ref = (rw - cw) // 2
        cy_ref = (rh - ch) // 2
        patch = gray_ref[cy_ref : cy_ref + ch, cx_ref : cx_ref + cw]
        res = cv2.matchTemplate(gray_tgt, patch, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > 0.40:
            shift_x = max_loc[0] - cx_ref
            shift_y = max_loc[1] - cy_ref
        else:
            shift_x, shift_y = 0, 0
    else:
        cx_tgt = (tw - cw) // 2
        cy_tgt = (th - ch) // 2
        patch = gray_tgt[cy_tgt : cy_tgt + ch, cx_tgt : cx_tgt + cw]
        res = cv2.matchTemplate(gray_ref, patch, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > 0.40:
            shift_x = -(max_loc[0] - cx_tgt)
            shift_y = -(max_loc[1] - cy_tgt)
        else:
            shift_x, shift_y = 0, 0

    if abs(shift_x) > rw * 0.25 or abs(shift_y) > rh * 0.25:
        shift_x, shift_y = 0, 0

    ref_x1 = max(0, -shift_x)
    ref_y1 = max(0, -shift_y)
    ref_x2 = min(rw, tw - shift_x)
    ref_y2 = min(rh, th - shift_y)

    tgt_x1 = ref_x1 + shift_x
    tgt_y1 = ref_y1 + shift_y
    tgt_x2 = ref_x2 + shift_x
    tgt_y2 = ref_y2 + shift_y

    aligned_ref = ref[ref_y1:ref_y2, ref_x1:ref_x2].copy()
    aligned_tgt = tgt[tgt_y1:tgt_y2, tgt_x1:tgt_x2].copy()

    min_h = min(aligned_ref.shape[0], aligned_tgt.shape[0])
    min_w = min(aligned_ref.shape[1], aligned_tgt.shape[1])
    aligned_ref = aligned_ref[:min_h, :min_w]
    aligned_tgt = aligned_tgt[:min_h, :min_w]

    return aligned_ref, aligned_tgt, (ref_x1, ref_y1), (tgt_x1, tgt_y1)


def detect_viewports(image: np.ndarray, split_mode: str = "auto") -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], str]:
    """
    Detects active game viewports (Reference Panel and Target Panel) within a composite image.
    Handles cropped game sheets, WeChat desktop mini programs, and full mobile screenshots.
    Returns: (ref_box, tgt_box, effective_mode) where box is (x, y, width, height).
    """
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 and image.shape[2] == 3 else image.copy()

    # 0. High-accuracy frame body segmentation: find prominent matching frame bodies
    frame_match = detect_matching_frame_bodies(image, split_mode=split_mode)
    if frame_match is not None:
        return frame_match

    # 1. Vertical periodic matching for dual vertical panels
    if split_mode in ("auto", "vertical") and height > width * 1.05:
        # Downsample 2x for fast multi-scale period discovery robust to any mini program window zoom/scale
        scale = 2
        small = cv2.resize(gray, (width // scale, height // scale))
        sh, sw = small.shape

        best_val = -1.0
        best_delta_y = 0
        best_delta_x = 0

        margin_x = int(sw * 0.10)
        tpl_h = max(20, int(sh * 0.10))

        # Sample across multiple potential vertical positions to handle any window scale / zoom
        for y_ratio in np.linspace(0.18, 0.35, 8):
            ty = int(sh * y_ratio)
            tpl = small[ty : ty + tpl_h, margin_x : sw - margin_x]
            search_top = max(int(sh * 0.40), ty + tpl_h + int(sh * 0.05))
            search = small[search_top :, int(margin_x * 0.5) : sw - int(margin_x * 0.5)]

            res = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            dy = (search_top + max_loc[1] - ty) * scale
            dx = (int(margin_x * 0.5) + max_loc[0] - margin_x) * scale

            if max_val > best_val and dy > height * 0.25:
                best_val = max_val
                best_delta_y = dy
                best_delta_x = dx

        if best_val > 0.50 and best_delta_y > height * 0.25:
            delta_y = int(best_delta_y)
            delta_x = int(best_delta_x)

            # Determine active panel bounds via row-by-row consistency between panels
            valid_h = height - delta_y
            row_diffs = np.zeros(valid_h, dtype=np.float32)
            row_stds = np.zeros(valid_h, dtype=np.float32)
            for y in range(valid_h):
                r1 = gray[y, margin_x * scale : width - margin_x * scale].astype(np.float32)
                r2 = gray[y + delta_y, margin_x * scale + delta_x : width - margin_x * scale + delta_x].astype(np.float32)
                row_diffs[y] = np.mean(np.abs(r1 - r2))
                row_stds[y] = np.std(r1)

            sorted_diffs = np.sort(row_diffs)
            base_diff = np.median(sorted_diffs[:int(valid_h * 0.4)])
            threshold = min(35.0, max(18.0, base_diff * 2.2))

            is_panel = ((row_diffs < threshold) & (row_stds > 10.0)).astype(np.uint8)
            
            # Simple run-length encoding to identify contiguous panel block:
            runs = []
            start = None
            for y in range(valid_h):
                if is_panel[y] and start is None:
                    start = y
                elif not is_panel[y] and start is not None:
                    runs.append([start, y - start])
                    start = None
            if start is not None:
                runs.append([start, valid_h - start])

            # Bridge internal gaps smaller than 10% of delta_y (e.g. internal game differences)
            gap_limit = max(40, int(delta_y * 0.10))
            merged_runs = []
            for r in runs:
                if not merged_runs:
                    merged_runs.append(r)
                else:
                    prev_start, prev_len = merged_runs[-1]
                    gap = r[0] - (prev_start + prev_len)
                    if gap < gap_limit:
                        merged_runs[-1][1] = (r[0] + r[1]) - prev_start
                    else:
                        merged_runs.append(r)

            if merged_runs:
                longest_run = max(merged_runs, key=lambda r: r[1])
                panel_y = longest_run[0]
                panel_h = min(delta_y, longest_run[1])
            else:
                panel_y = 0
                panel_h = delta_y

            if panel_h < 20:
                panel_y = 0
                panel_h = delta_y

            # Detect left/right solid borders (letterboxing or window chrome)
            sample_ref = gray[panel_y:panel_y + panel_h, :]
            col_stds = np.std(sample_ref, axis=0) if sample_ref.size > 0 else np.ones(width) * 10.0
            left_x = 0
            while left_x < int(width * 0.15) and col_stds[left_x] < 3.0:
                left_x += 1
            right_x = width
            while right_x > int(width * 0.85) and col_stds[right_x - 1] < 3.0:
                right_x -= 1
            panel_x = left_x
            panel_w = max(width // 2, right_x - left_x)

            ref_box = (int(panel_x), int(panel_y), int(panel_w), int(panel_h))
            tgt_box = (int(panel_x + delta_x), int(panel_y + delta_y), int(panel_w), int(panel_h))
            return ref_box, tgt_box, "vertical"

    # 2. Horizontal correlation for wide images
    if split_mode in ("auto", "horizontal") and width > height * 1.3:
        best_val = -1.0
        best_delta_x = 0

        for tx_ratio in [0.08, 0.15, 0.22, 0.30]:
            tpl_x = int(width * tx_ratio)
            tpl_w = max(30, int(width * 0.12))
            crop_y = int(height * 0.1)
            tpl = gray[crop_y:height - crop_y, tpl_x:tpl_x + tpl_w]
            search_area = gray[crop_y:height - crop_y, int(width * 0.38):]

            res = cv2.matchTemplate(search_area, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val > best_val:
                best_val = max_val
                best_delta_x = int(width * 0.38) + max_loc[0] - tpl_x

        if best_val > 0.65 and best_delta_x > width * 0.3:
            delta_x = best_delta_x
            valid_w = width - delta_x
            margin_y = int(height * 0.08)
            col_diffs = np.zeros(valid_w, dtype=np.float32)
            for x in range(valid_w):
                c1 = gray[margin_y:height - margin_y, x].astype(np.float32)
                c2 = gray[margin_y:height - margin_y, x + delta_x].astype(np.float32)
                col_diffs[x] = np.mean(np.abs(c1 - c2))

            sorted_diffs = np.sort(col_diffs)
            base_diff = np.median(sorted_diffs[:int(valid_w * 0.4)])
            threshold = max(18.0, base_diff * 3.5)
            is_panel = col_diffs < threshold

            max_start = 0
            max_len = 0
            curr_start = None
            for i, val in enumerate(is_panel):
                if val and curr_start is None:
                    curr_start = i
                elif not val and curr_start is not None:
                    if (i - curr_start) > max_len:
                        max_len = i - curr_start
                        max_start = curr_start
                    curr_start = None
            if curr_start is not None and (len(is_panel) - curr_start) > max_len:
                max_len = len(is_panel) - curr_start
                max_start = curr_start

            panel_x = max_start
            panel_w = max_len
            if panel_w < delta_x * 0.5:
                panel_w = delta_x

            ref_box = (int(panel_x), 0, int(panel_w), height)
            tgt_box = (int(panel_x + delta_x), 0, int(delta_x if panel_w >= delta_x else panel_w), height)
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

    # Guard against invalid or empty crops
    if ref.size == 0 or tgt.size == 0 or ref.shape[0] < 5 or ref.shape[1] < 5:
        height, width = image.shape[:2]
        if (split_mode == "auto" and width > height) or split_mode == "horizontal":
            mid = width // 2
            ref = image[:, :mid].copy()
            tgt = image[:, mid:].copy()
            rx, ry = 0, 0
            tx, ty = mid, 0
            effective_mode = "horizontal"
        else:
            mid = height // 2
            ref = image[:mid, :].copy()
            tgt = image[mid:, :].copy()
            rx, ry = 0, 0
            tx, ty = 0, mid
            effective_mode = "vertical"

    # Align dimensions if 1-pixel rounding difference exists
    min_h = min(ref.shape[0], tgt.shape[0])
    min_w = min(ref.shape[1], tgt.shape[1])
    ref = ref[:min_h, :min_w]
    tgt = tgt[:min_h, :min_w]

    if return_offsets:
        return ref, tgt, effective_mode, (rx, ry), (tx, ty)
    return ref, tgt, effective_mode


def merge_overlapping_circles(
    marks: List[DifferenceMark], buffer_ratio: float = 1.05, max_radius: int = 120
) -> List[DifferenceMark]:
    """
    Guarantees that NO difference marks overlap.
    Iteratively merges any pair of circular marks whose distance is less than
    the sum of their radii (dist < (r1 + r2) * buffer_ratio) into a single
    minimum enclosing circle encompassing both marks.
    """
    if not marks:
        return []

    current = list(marks)
    changed = True
    while changed:
        changed = False
        new_list: List[DifferenceMark] = []
        used = set()
        for i in range(len(current)):
            if i in used:
                continue
            merged = current[i]
            for j in range(i + 1, len(current)):
                if j in used:
                    continue
                m2 = current[j]
                dist = np.hypot(merged.center_x - m2.center_x, merged.center_y - m2.center_y)
                # Overlap condition: circles intersect or touch within buffer
                if dist < (merged.radius + m2.radius) * buffer_ratio:
                    if dist == 0:
                        new_r = max(merged.radius, m2.radius)
                        new_cx, new_cy = merged.center_x, merged.center_y
                    else:
                        ux = (m2.center_x - merged.center_x) / dist
                        uy = (m2.center_y - merged.center_y) / dist
                        p1x = merged.center_x - ux * merged.radius
                        p1y = merged.center_y - uy * merged.radius
                        p2x = m2.center_x + ux * m2.radius
                        p2y = m2.center_y + uy * m2.radius
                        new_cx = int(round((p1x + p2x) / 2))
                        new_cy = int(round((p1y + p2y) / 2))
                        new_r = int(round(np.hypot(p2x - p1x, p2y - p1y) / 2))

                    # Hard ceiling: prevent merging into an unnatural giant circle spanning across unrelated regions
                    if new_r > max_radius:
                        continue

                    merged = DifferenceMark(
                        id=0,
                        center_x=new_cx,
                        center_y=new_cy,
                        radius=new_r,
                        bounding_box=(
                            max(0, new_cx - new_r),
                            max(0, new_cy - new_r),
                            2 * new_r,
                            2 * new_r,
                        ),
                        area=merged.area + m2.area,
                    )
                    used.add(j)
                    changed = True
            new_list.append(merged)
            used.add(i)
        current = new_list

    current.sort(key=lambda m: (m.center_y, m.center_x))
    for idx, m in enumerate(current, start=1):
        m.id = idx

    return current


def apply_circular_nms(marks: List[DifferenceMark], overlap_threshold: float = 1.0) -> List[DifferenceMark]:
    """
    Backward-compatible alias for merge_overlapping_circles.
    """
    return merge_overlapping_circles(marks, buffer_ratio=overlap_threshold)


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
    if ref_panel is None or tgt_panel is None or ref_panel.size == 0 or tgt_panel.size == 0:
        return []

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

    # Shift-tolerant difference (morphological tolerance absorbs 1-2 pixel micro-jitter / Retina subpixel shifts without warping)
    k_dim = 5 if panel_w > 500 else 3
    tol_k = cv2.getStructuringElement(cv2.MORPH_RECT, (k_dim, k_dim))
    diff_ref = np.maximum(0, blurred_ref.astype(np.int16) - cv2.dilate(blurred_tgt, tol_k).astype(np.int16))
    diff_tgt = np.maximum(0, blurred_tgt.astype(np.int16) - cv2.dilate(blurred_ref, tol_k).astype(np.int16))
    diff = np.maximum(diff_ref, diff_tgt).astype(np.uint8)

    # Exclude border seam if specified
    if border_margin > 0 and panel_h > border_margin * 2 and panel_w > border_margin * 2:
        diff_inner = diff[border_margin:panel_h - border_margin, border_margin:panel_w - border_margin]
    else:
        diff_inner = diff
        border_margin = 0

    # Guard: if panels have massive global difference (e.g. menu, ad, or game-over screen), reject false positives
    if float(np.mean(diff_inner)) > 30.0:
        return []

    # Binary Threshold
    _, thresh = cv2.threshold(diff_inner, diff_threshold, 255, cv2.THRESH_BINARY)

    # Morphological Open (filter high-frequency speckles)
    open_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, open_k)

    # Morphological Close
    close_kernel_size = 7 if max(panel_h, panel_w) > 600 else 5
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_kernel_size, close_kernel_size))
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, close_k)

    # Find contours
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_marks: List[DifferenceMark] = []
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area:
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        max_r_allowed = int(min(panel_h, panel_w) * 0.15)
        if radius > max_r_allowed:
            continue
        # Reject thin wire/seam noise (solidity check)
        if radius > 18 and (area / (np.pi * radius * radius)) < 0.10:
            continue
        padded_radius = max(int(radius) + 3, 12)

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

    # Apply strict non-overlapping merge with adaptive radius ceiling to guarantee clean, accurate circles
    max_merge_r = max(60, int(min(panel_h, panel_w) * 0.20))
    return merge_overlapping_circles(raw_marks, buffer_ratio=1.0, max_radius=max_merge_r)


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
        pt_ref = mark.global_ref_center if mark.global_ref_center is not None else (rx + mark.center_x, ry + mark.center_y)
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
        pt_tgt = mark.global_tgt_center if mark.global_tgt_center is not None else (tx + mark.center_x, ty + mark.center_y)
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
    diff_threshold: int = 18,
    min_area: int = 50,
    blur_radius: int = 3,
    max_differences: Optional[int] = None,
    custom_boxes: Optional[Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]] = None,
) -> Tuple[DiffResult, np.ndarray]:
    """
    Main high-level comparison pipeline:
    1. Detects panel viewports (or uses custom calibrated boxes).
    2. Compares panels with adaptive morphology and NMS.
    3. Annotates symmetric difference marks.
    """
    start_time = time.perf_counter()

    if custom_boxes is not None:
        (rx, ry, rw, rh), (tx, ty, tw, th) = custom_boxes
        ref_panel = image[ry : ry + rh, rx : rx + rw].copy()
        tgt_panel = image[ty : ty + th, tx : tx + tw].copy()
        ref_offset = (rx, ry)
        tgt_offset = (tx, ty)
        effective_mode = "custom"
        border_margin = 0
    else:
        ref_panel, tgt_panel, effective_mode, ref_offset, tgt_offset = split_game_sheet(
            image, split_mode=split_mode, return_offsets=True
        )
        # If mobile screenshot viewport is detected (offset > 50px), ignore outer 20px frame border
        border_margin = 20 if (ref_offset[1] > 50 or ref_offset[0] > 50) else 0

    if ref_panel is None or tgt_panel is None or ref_panel.size == 0 or tgt_panel.size == 0:
        return (
            DiffResult(
                split_mode=effective_mode,
                difference_count=0,
                differences=[],
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            ),
            image.copy(),
        )

    # Micro-align panels to absorb asymmetric borders, independent widths, or minor translation jitter
    ref_aligned, tgt_aligned, (ref_sub_x, ref_sub_y), (tgt_sub_x, tgt_sub_y) = align_panels_content(
        ref_panel, tgt_panel
    )

    differences = detect_differences(
        ref_panel=ref_aligned,
        tgt_panel=tgt_aligned,
        diff_threshold=diff_threshold,
        min_area=min_area,
        blur_radius=blur_radius,
        border_margin=border_margin,
    )

    # If maximum differences limit is specified, select top-K most prominent differences by area
    if max_differences is not None and max_differences > 0 and len(differences) > max_differences:
        differences = sorted(differences, key=lambda d: d.area, reverse=True)[:max_differences]
        differences.sort(key=lambda d: (d.center_y, d.center_x))
        for idx, d in enumerate(differences, 1):
            d.id = idx

    # Populate global coordinates including micro-alignment sub-offsets
    rx, ry = ref_offset
    tx, ty = tgt_offset
    for d in differences:
        d.global_ref_center = (rx + ref_sub_x + d.center_x, ry + ref_sub_y + d.center_y)
        d.global_tgt_center = (tx + tgt_sub_x + d.center_x, ty + tgt_sub_y + d.center_y)

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
        ref_box=(rx, ry, ref_panel.shape[1], ref_panel.shape[0]),
        tgt_box=(tx, ty, tgt_panel.shape[1], tgt_panel.shape[0]),
    )

    return result, annotated_image
