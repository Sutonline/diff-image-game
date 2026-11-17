from typing import Tuple, List, Optional
import time
import cv2
import numpy as np
from diff_game.models import DifferenceMark, DiffResult


# Calibrated default viewport ratios for standard WeChat mini program window (353x690 pt / 706x1380 px)
DEFAULT_WECHAT_VIEWPORT_RATIOS = {
    "x": 0.038,
    "y_ref": 0.235,
    "y_tgt": 0.559,
    "w": 0.924,
    "h": 0.321,
}


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


def detect_viewports(
    image: np.ndarray,
    split_mode: str = "auto",
    use_fixed_wechat: bool = False,
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], str]:
    """
    Detects active game viewports (Reference Panel and Target Panel) within a composite image.
    Handles cropped game sheets, WeChat desktop mini programs, and full mobile screenshots.
    Returns: (ref_box, tgt_box, effective_mode) where box is (x, y, width, height).
    """
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 and image.shape[2] == 3 else image.copy()

    # Calibrated default viewport boxes for standard WeChat mini program window (353x690 pt / 706x1380 px)
    default_ref_box = (
        int(width * DEFAULT_WECHAT_VIEWPORT_RATIOS["x"]),
        int(height * DEFAULT_WECHAT_VIEWPORT_RATIOS["y_ref"]),
        int(width * DEFAULT_WECHAT_VIEWPORT_RATIOS["w"]),
        int(height * DEFAULT_WECHAT_VIEWPORT_RATIOS["h"]),
    )
    default_tgt_box = (
        int(width * DEFAULT_WECHAT_VIEWPORT_RATIOS["x"]),
        int(height * DEFAULT_WECHAT_VIEWPORT_RATIOS["y_tgt"]),
        int(width * DEFAULT_WECHAT_VIEWPORT_RATIOS["w"]),
        int(height * DEFAULT_WECHAT_VIEWPORT_RATIOS["h"]),
    )

    # If user explicitly requested fixed default WeChat mini-program boxes
    if use_fixed_wechat and height > width * 1.4:
        return default_ref_box, default_tgt_box, "vertical"

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

        # Sample across multiple potential vertical positions with strict vertical alignment (delta_x = 0)
        for y_ratio in np.linspace(0.18, 0.35, 8):
            ty = int(sh * y_ratio)
            tpl = small[ty : ty + tpl_h, margin_x : sw - margin_x]
            search_top = max(int(sh * 0.40), ty + tpl_h + int(sh * 0.05))
            search = small[search_top :, margin_x : sw - margin_x]

            res = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            dy = (search_top + max_loc[1] - ty) * scale

            if max_val > best_val and dy > height * 0.25:
                best_val = max_val
                best_delta_y = dy
                best_delta_x = 0

        if best_val > 0.50 and best_delta_y > height * 0.25:
            delta_y = int(best_delta_y)
            delta_x = 0

            # Determine active panel bounds via row-by-row consistency between panels
            valid_h = height - delta_y
            row_diffs = np.zeros(valid_h, dtype=np.float32)
            row_stds = np.zeros(valid_h, dtype=np.float32)
            for y in range(valid_h):
                r1 = gray[y, margin_x * scale : width - margin_x * scale].astype(np.float32)
                r2 = gray[y + delta_y, margin_x * scale : width - margin_x * scale].astype(np.float32)
                row_diffs[y] = np.mean(np.abs(r1 - r2))
                row_stds[y] = np.std(r1)

            sorted_diffs = np.sort(row_diffs)
            base_diff = np.median(sorted_diffs[:int(valid_h * 0.4)])
            threshold = min(35.0, max(18.0, base_diff * 2.2))

            is_panel = ((row_diffs < threshold) & (row_stds > 10.0)).astype(np.uint8)

            # In window screenshots (height > width * 1.4), skip top window chrome / title bar
            min_panel_y = int(height * 0.10) if height > width * 1.4 else 0
            if min_panel_y > 0:
                is_panel[:min_panel_y] = 0
            
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
            else:
                panel_y = 0

            # The top panel must extend down to the central divider separating the two panels.
            # In dual-panel vertical mobile games, the divider sits immediately above p2_top (panel_y + delta_y).
            # Avoid prematurely cutting off the panel bottom when prominent in-game differences occur near the bottom edge.
            p2_top = panel_y + delta_y
            max_div = max(16, int(delta_y * 0.08))
            search_start = max(panel_y + int(delta_y * 0.85), p2_top - max_div)
            zone = gray[search_start : min(height, p2_top + 2), :]
            if zone.shape[0] > 2:
                grad = np.mean(np.abs(np.diff(zone.astype(float), axis=0)), axis=1)
                div_y = search_start + int(np.argmax(grad))
                refined_h = div_y - panel_y
            else:
                refined_h = delta_y - 6

            # Bound constraints: panel_h fills the artwork area while respecting divider and window bounds
            panel_h = max(int(delta_y * 0.90), min(refined_h, delta_y - 4))
            if panel_y + delta_y + panel_h > height:
                panel_h = height - panel_y - delta_y
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

        # If periodic matching is uncertain but explicitly requested WeChat mini-program layout
        if use_fixed_wechat and height > width * 1.4:
            return default_ref_box, default_tgt_box, "vertical"

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
    image: np.ndarray,
    split_mode: str = "auto",
    return_offsets: bool = False,
    use_fixed_wechat: bool = False,
):
    """
    Extracts panels.
    If return_offsets=False (default): returns (ref_panel, tgt_panel, effective_mode).
    If return_offsets=True: returns (ref_panel, tgt_panel, effective_mode, (ref_x, ref_y), (tgt_x, tgt_y)).
    """
    ref_box, tgt_box, effective_mode = detect_viewports(
        image, split_mode=split_mode, use_fixed_wechat=use_fixed_wechat
    )
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
    marks: List[DifferenceMark],
    buffer_ratio: float = 1.05,
    max_radius: int = 120,
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
                        score=merged.score + m2.score,
                    )
                    used.add(j)
                    changed = True
            new_list.append(merged)
            used.add(i)
        current = new_list

    # Final pass: guarantee strict mathematical non-overlapping invariant: dist >= r1 + r2
    for i in range(len(current)):
        for j in range(i + 1, len(current)):
            m1 = current[i]
            m2 = current[j]
            dist = float(np.hypot(m1.center_x - m2.center_x, m1.center_y - m2.center_y))
            if dist < (m1.radius + m2.radius):
                target_sum = max(16.0, dist - 0.5)
                curr_sum = float(m1.radius + m2.radius)
                if curr_sum > 0:
                    scale = target_sum / curr_sum
                    m1.radius = max(8, int(m1.radius * scale))
                    m2.radius = max(8, int(m2.radius * scale))
                    if m1.radius + m2.radius > dist:
                        m2.radius = max(8, int(dist - m1.radius))

    current.sort(key=lambda m: (m.center_y, m.center_x))
    for idx, m in enumerate(current, start=1):
        m.id = idx

    return current


def apply_circular_nms(marks: List[DifferenceMark], overlap_threshold: float = 1.0) -> List[DifferenceMark]:
    """
    Backward-compatible alias for merge_overlapping_circles.
    """
    return merge_overlapping_circles(marks, buffer_ratio=overlap_threshold)


def _bbox_gap(p: List[float], q: List[float]) -> float:
    """Computes minimum Euclidean gap between two axis-aligned bounding boxes [x1, y1, x2, y2]."""
    dx = max(0.0, max(p[0], q[0]) - min(p[2], q[2]))
    dy = max(0.0, max(p[1], q[1]) - min(p[3], q[3]))
    return float(np.hypot(dx, dy))


def _subpixel_align(ref: np.ndarray, tgt: np.ndarray) -> np.ndarray:
    """Warps tgt onto ref with a near-identity affine transform estimated by ECC. Falls back to tgt unchanged."""
    try:
        g_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY) if ref.ndim == 3 else ref
        g_tgt = cv2.cvtColor(tgt, cv2.COLOR_BGR2GRAY) if tgt.ndim == 3 else tgt
        if float(np.std(g_ref)) < 5.0:
            return tgt
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
        _, warp = cv2.findTransformECC(g_ref.astype(np.float32), g_tgt.astype(np.float32), warp,
                                       cv2.MOTION_AFFINE, criteria, None, 5)
        linear_ok = np.allclose(warp[:, :2], np.eye(2), atol=0.02)
        shift_ok = abs(float(warp[0, 2])) <= 4.0 and abs(float(warp[1, 2])) <= 4.0
        if not (linear_ok and shift_ok):
            return tgt
        h, w = ref.shape[:2]
        return cv2.warpAffine(tgt, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)
    except cv2.error:
        return tgt


def _min_shift_diff(a: np.ndarray, b: np.ndarray, radius: int = 1) -> np.ndarray:
    """For each pixel of a, the smallest colour distance to any pixel of b within +-radius px."""
    best: Optional[np.ndarray] = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(np.roll(b, dy, axis=0), dx, axis=1)
            d = np.linalg.norm(a - shifted, axis=2)
            best = d if best is None else np.minimum(best, d)
    return best


def _near_any_circle(xs: np.ndarray, ys: np.ndarray, circles: List[Tuple[float, float, float]]) -> bool:
    """True if the closest pixel of a blob lies within (0.35 * r + 4) px outside any circle's edge."""
    for cx, cy, r in circles:
        gap = float(np.min(np.hypot(xs - cx, ys - cy))) - r
        if gap <= 0.35 * r + 4.0:
            return True
    return False


def _structural_change_peaks(
    ref: np.ndarray,
    tgt: np.ndarray,
    blocked: List[Tuple[float, float, float]],
    border: int,
    max_peaks: int,
    min_score: float = 0.15,
) -> List[Tuple[float, float, float]]:
    """
    Fallback candidates for changes that keep the colours but alter the shape, e.g. one character
    on a couplet changed (好 -> 坏): black ink on paper either way, so colour difference is tiny,
    but the local stroke pattern no longer matches.

    Works at native resolution (fine strokes vanish when downscaled). For every pixel, the best
    normalised cross-correlation of a small window against the other panel within +-1px is
    computed; 1 - NCC, weighted by local contrast, is high where high-contrast structure changed.
    Low-contrast textures (carpets, walls, compression noise) are suppressed by the contrast weight.

    blocked: [(cx, cy, r)] areas to ignore (already-found rings, existing candidates).
    Returns up to max_peaks [(cx, cy, score)] in panel pixels, best first.
    """
    if max_peaks <= 0 or ref.ndim != 3:
        return []
    h, w = ref.shape[:2]
    tgt = _subpixel_align(ref, tgt)
    ga = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(tgt, cv2.COLOR_BGR2GRAY).astype(np.float32)
    win = max(5, int(round(9 * w / 680.0)) | 1)
    k = (win, win)

    def _local(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        m = cv2.blur(x, k)
        return m, np.sqrt(np.maximum(cv2.blur(x * x, k) - m * m, 1e-3))

    ma, sa = _local(ga)
    best: Optional[np.ndarray] = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            g = np.roll(np.roll(gb, dy, axis=0), dx, axis=1)
            mb, sb = _local(g)
            ncc = (cv2.blur(ga * g, k) - ma * mb) / (sa * sb)
            best = ncc if best is None else np.maximum(best, ncc)
    _, sb0 = _local(gb)
    score = (1.0 - np.clip(best, -1.0, 1.0)) * np.minimum(np.maximum(sa, sb0) / 60.0, 1.0) ** 2

    if border > 0:
        score[:border, :] = 0
        score[-border:, :] = 0
        score[:, :border] = 0
        score[:, -border:] = 0
    for cx, cy, r in blocked:
        cv2.circle(score, (int(round(cx)), int(round(cy))), int(round(r)), 0, -1)
    sk = max(5, int(round(7 * w / 680.0)) | 1)
    score = cv2.GaussianBlur(score, (sk, sk), 0)

    peaks: List[Tuple[float, float, float]] = []
    suppress = max(10, int(round(20 * w / 680.0)))
    for _ in range(max_peaks):
        _, val, _, loc = cv2.minMaxLoc(score)
        if val < min_score:
            break
        peaks.append((float(loc[0]), float(loc[1]), float(val)))
        cv2.circle(score, loc, suppress, 0, -1)
    return peaks


def detect_differences(
    ref_panel: np.ndarray,
    tgt_panel: np.ndarray,
    diff_threshold: int = 18,
    min_area: int = 12,
    blur_radius: int = 3,
    border_margin: int = 8,
    target_count: Optional[int] = None,
    exclude_circles: Optional[List[Tuple[float, float, float]]] = None,
) -> List[DifferenceMark]:
    """
    Detects difference marks between two aligned panels:
    1. Normalizes panels to fixed width 600px before detection.
    2. Computes LAB color difference (delta E) on Gaussian-blurred normalized panels.
    3. Zeros border margins, thresholds, removes noise via morphological open,
       and connects nearby fragments via 9x9 ellipse dilation.
    4. Extracts connected-component bounding boxes, adjusting threshold downward if
       fewer than target_count or merging closest-gap bounding boxes if more than target_count.
    5. Maps centers, bounding boxes, areas, and proportional radii back to original scale.
    """
    if ref_panel is None or tgt_panel is None or ref_panel.size == 0 or tgt_panel.size == 0:
        return []

    panel_h, panel_w = ref_panel.shape[:2]
    if panel_h < 5 or panel_w < 5:
        return []

    norm_w = 600.0
    scale = norm_w / float(panel_w)
    norm_ref = cv2.resize(ref_panel, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    norm_tgt = cv2.resize(tgt_panel, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    # Sub-pixel alignment: window scaling often leaves the two panels offset by a fraction of a pixel,
    # which turns every outline in the artwork into a false difference. Estimate a near-identity
    # affine transform with ECC and warp the target panel onto the reference panel.
    norm_tgt = _subpixel_align(norm_ref, norm_tgt)

    ksize = 3
    if len(norm_ref.shape) == 3 and norm_ref.shape[2] == 3:
        lab_ref = cv2.cvtColor(cv2.GaussianBlur(norm_ref, (ksize, ksize), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
        lab_tgt = cv2.cvtColor(cv2.GaussianBlur(norm_tgt, (ksize, ksize), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    else:
        lab_ref = cv2.GaussianBlur(norm_ref, (ksize, ksize), 0).astype(np.float32)[..., None]
        lab_tgt = cv2.GaussianBlur(norm_tgt, (ksize, ksize), 0).astype(np.float32)[..., None]

    # Shift-tolerant symmetric difference: a pixel only counts as different if no pixel within
    # +-1px in the other panel matches it. Removes residual outline jitter but keeps added/removed objects.
    diff = np.maximum(_min_shift_diff(lab_ref, lab_tgt), _min_shift_diff(lab_tgt, lab_ref))

    margin = border_margin
    if margin > 0 and diff.shape[0] > 2 * margin and diff.shape[1] > 2 * margin:
        diff[:margin, :] = 0
        diff[-margin:, :] = 0
        diff[:, :margin] = 0
        diff[:, -margin:] = 0

    # Differences the player already found (inside the game's green rings) are not candidates:
    # blank them out so their fragments can neither take a slot nor be shown again.
    if exclude_circles:
        for ecx, ecy, er in exclude_circles:
            cv2.circle(diff, (int(round(ecx * scale)), int(round(ecy * scale))),
                       int(round(er * scale * 1.15 + 3)), 0, -1)

    # Guard against completely mismatched screens (e.g. menus, ads, transitions)
    if float(np.mean(diff)) > 45.0:
        return []

    excl_norm = [(ecx * scale, ecy * scale, er * scale) for ecx, ecy, er in (exclude_circles or [])]

    open_kernel = np.ones((2, 2), np.uint8)
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def _extract_blobs(thresh: float) -> List[List[float]]:
        binary = (diff > thresh).astype(np.uint8) * 255
        opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)
        dilated = cv2.dilate(opened, dilate_kernel)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(dilated)
        res: List[List[float]] = []
        for i in range(1, num_labels):
            x, y, w, h, _ = stats[i]
            mask = (labels == i) & (diff > thresh)
            active_px = int(mask.sum())
            if active_px < min_area:
                continue
            # Reject thin straight streaks (1-3px thick, long): residual misalignment along a strong
            # straight edge such as ceiling light strips or table rims, not a real object difference.
            ys, xs = np.nonzero(mask)
            raw_h = int(ys.max() - ys.min() + 1)
            raw_w = int(xs.max() - xs.min() + 1)
            if min(raw_h, raw_w) <= 3 and max(raw_h, raw_w) >= 4 * min(raw_h, raw_w):
                continue
            # A fragment hugging an excluded (already-found) ring is the part of that difference
            # the game's ring did not fully enclose; it is not a new difference.
            if _near_any_circle(xs, ys, excl_norm):
                continue
            res.append([float(x), float(y), float(x + w), float(y + h), float(diff[mask].sum()), float(active_px)])
        return res

    base_t = float(diff_threshold)
    blobs = _extract_blobs(base_t)

    def _structural_fill(existing: List[List[float]], deficit: int) -> List[List[float]]:
        """Shape-change candidates (see _structural_change_peaks) as blobs in normalised coords."""
        blocked = [(ecx, ecy, er * 1.35 + 6.0) for ecx, ecy, er in (exclude_circles or [])]
        for bx1, by1, bx2, by2, *_ in existing:
            blocked.append((((bx1 + bx2) / 2.0) / scale, ((by1 + by2) / 2.0) / scale,
                            (max(bx2 - bx1, by2 - by1) / 2.0 + 6.0) / scale))
        peaks = _structural_change_peaks(ref_panel, tgt_panel, blocked,
                                         border=int(round(margin / scale)) if margin > 0 else 0,
                                         max_peaks=deficit)
        half = 10.0
        return [[px * scale - half, py * scale - half, px * scale + half, py * scale + half,
                 float(v) * 100.0, 1.0] for px, py, v in peaks]

    if target_count is not None and target_count > 0 and len(blobs) < target_count:
        # 1) Colour finds too few: first add places where high-contrast structure changed
        #    (e.g. a single character), which colour difference misses.
        blobs = blobs + _structural_fill(blobs, target_count - len(blobs))

    if target_count is not None and target_count > 0 and len(blobs) < target_count:
        # 2) Still too few: lower the colour threshold, keeping any structural candidates.
        structural = [b for b in blobs if b[5] == 1.0]
        best_blobs = blobs
        for factor in (0.8, 0.65, 0.5):
            cand_t = max(6.0, base_t * factor)
            cand_blobs = _extract_blobs(cand_t)
            for sb_ in structural:
                if all(_bbox_gap(sb_, cb) > 3.0 for cb in cand_blobs):
                    cand_blobs.append(sb_)
            if len(cand_blobs) > len(best_blobs):
                best_blobs = cand_blobs
            if len(best_blobs) >= target_count:
                break
        blobs = best_blobs

    # Fragments whose boxes touch (gap <= 3px) belong to the same object: always merge them first,
    # so a split object never occupies two slots while a faint real difference is dropped.
    merged_any = True
    while merged_any and len(blobs) > 1:
        merged_any = False
        for i in range(len(blobs)):
            for j in range(i + 1, len(blobs)):
                if _bbox_gap(blobs[i], blobs[j]) <= 3.0:
                    p, q = blobs[i], blobs[j]
                    blobs[i] = [min(p[0], q[0]), min(p[1], q[1]), max(p[2], q[2]), max(p[3], q[3]),
                                p[4] + q[4], p[5] + q[5]]
                    del blobs[j]
                    merged_any = True
                    break
            if merged_any:
                break

    if target_count is not None and target_count > 0:
        norm_h, norm_w_px = diff.shape[:2]
        max_side = 0.30 * min(norm_h, norm_w_px)
        while len(blobs) > target_count:
            energies = sorted(b[4] for b in blobs)
            median_e = energies[len(energies) // 2]
            weakest = min(range(len(blobs)), key=lambda k: blobs[k][4])
            # 1) A blob far weaker than a typical difference is residual noise: drop it.
            if blobs[weakest][4] < 0.10 * median_e:
                del blobs[weakest]
                continue
            # 2) Otherwise merge the two closest fragments, as long as the result stays object-sized.
            best: Optional[Tuple[float, int, int]] = None
            for i in range(len(blobs)):
                for j in range(i + 1, len(blobs)):
                    p, q = blobs[i], blobs[j]
                    mw = max(p[2], q[2]) - min(p[0], q[0])
                    mh = max(p[3], q[3]) - min(p[1], q[1])
                    if max(mw, mh) > max_side:
                        continue
                    gap = _bbox_gap(p, q)
                    if best is None or gap < best[0]:
                        best = (gap, i, j)
            # 3) Nothing can be merged sensibly (or fragments are far apart): drop the weakest blob.
            if best is None or best[0] > 0.08 * min(norm_h, norm_w_px):
                del blobs[weakest]
                continue
            _, i, j = best
            p, q = blobs[i], blobs[j]
            blobs[i] = [
                min(p[0], q[0]),
                min(p[1], q[1]),
                max(p[2], q[2]),
                max(p[3], q[3]),
                p[4] + q[4],
                p[5] + q[5],
            ]
            del blobs[j]

    blobs.sort(key=lambda z: (z[1], z[0]))

    marks: List[DifferenceMark] = []
    for idx, (x1, y1, x2, y2, energy, active_px) in enumerate(blobs, start=1):
        cx = int(round((x1 + x2) / 2.0 / scale))
        cy = int(round((y1 + y2) / 2.0 / scale))
        r_norm = min(max(12.0, 0.6 * max(x2 - x1, y2 - y1)), 0.15 * min(diff.shape[:2]))
        radius = max(1, int(round(r_norm / scale)))
        bx = int(round(x1 / scale))
        by = int(round(y1 / scale))
        bw = max(1, int(round((x2 - x1) / scale)))
        bh = max(1, int(round((y2 - y1) / scale)))
        orig_area = float(active_px) / (scale * scale)
        marks.append(
            DifferenceMark(
                id=idx,
                center_x=cx,
                center_y=cy,
                radius=radius,
                bounding_box=(bx, by, bw, bh),
                area=orig_area,
                score=float(energy),
            )
        )

    return marks


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


def _detect_badge_row(image: np.ndarray):
    """
    Finds the row of badge slots ('?' for unfound, green check for found) above the panels.
    Returns (row_circles sorted by x, badge strip image) or None.
    """
    if image is None or image.size == 0:
        return None
    h, w = image.shape[:2]
    if h < w * 1.4:
        return None

    y1 = int(h * 0.16)
    y2 = int(h * 0.26)
    strip = image[y1:y2, :]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.0,
        minDist=max(15, int(w * 0.03)),
        param1=50,
        param2=18,
        minRadius=max(8, int(w * 0.015)),
        maxRadius=max(20, int(w * 0.035)),
    )

    if circles is None or len(circles[0]) < 5:
        return None

    detected = circles[0]
    y_coords = detected[:, 1]
    vals, counts = np.unique(np.round(y_coords), return_counts=True)
    mode_y = float(vals[np.argmax(counts)])
    inliers = y_coords[np.abs(y_coords - mode_y) < 8]
    target_y = float(np.median(inliers)) if len(inliers) > 0 else float(np.median(y_coords))

    row_circles = [c for c in detected if abs(c[1] - target_y) < 8]
    if len(row_circles) < 5:
        return None

    row_circles = sorted(row_circles, key=lambda c: c[0])
    diffs = [row_circles[i + 1][0] - row_circles[i][0] for i in range(len(row_circles) - 1)]
    if len(diffs) < 4:
        return None

    radii = [c[2] for c in row_circles]
    if np.std(radii) > 2.5:
        return None
    if np.std(diffs) > 5.0:
        return None

    return row_circles, strip


def detect_target_differences_count(image: np.ndarray) -> Optional[int]:
    """
    Number of badge slots in the mini-program UI = total differences in the level
    (found + unfound). Returns None if no uniform badge row exists (e.g. cropped artwork).
    """
    row = _detect_badge_row(image)
    return len(row[0]) if row else None


def detect_badge_status(image: np.ndarray) -> Optional[Tuple[int, int]]:
    """
    Returns (total, found): found badges are drawn with the game's green check mark,
    unfound ones are beige '?' slots.
    """
    row = _detect_badge_row(image)
    if not row:
        return None
    circles, strip = row
    green = _game_green_mask(strip)
    found = 0
    for cx, cy, r in circles:
        disc = np.zeros(green.shape, np.uint8)
        cv2.circle(disc, (int(cx), int(cy)), max(2, int(r * 0.9)), 255, -1)
        inside = disc > 0
        if inside.sum() and float(np.mean(green[inside] > 0)) > 0.12:
            found += 1
    return len(circles), found


def _game_green_mask(bgr: np.ndarray) -> np.ndarray:
    """Pixels in the yellow-green colour the game uses for its 'found' rings and check marks."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (34, 110, 140), (52, 215, 235))


def _fit_circle(xs: np.ndarray, ys: np.ndarray) -> Optional[Tuple[float, float, float]]:
    """Least-squares (Kasa) circle fit; works on partial arcs such as rings clipped by the panel edge."""
    A = np.column_stack([xs, ys, np.ones_like(xs)]).astype(np.float64)
    b = -(xs.astype(np.float64) ** 2 + ys.astype(np.float64) ** 2)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = -sol[0] / 2.0, -sol[1] / 2.0
    r2 = cx * cx + cy * cy - sol[2]
    return (float(cx), float(cy), float(np.sqrt(r2))) if r2 > 0 else None


def detect_found_rings(panel: np.ndarray) -> List[Tuple[float, float, float]]:
    """
    Detects the green rings the game draws around differences the player has already found.
    The ring's size is the game's own definition of how big that one difference is.

    Green regions are kept only where they form a thin band (ring stroke); thick green areas such
    as lawns and trees are removed by a morphological opening. Each candidate band must fit a
    circle tightly and be green almost all the way round (rings clipped by the panel edge are
    accepted), which rejects stray arcs of foliage or clothing.
    Returns [(cx, cy, r)] in panel pixels.
    """
    if panel is None or panel.size == 0:
        return []
    h, w = panel.shape[:2]
    unit = w / 676.0
    green = _game_green_mask(panel)

    thick_k = max(7, int(round(11 * unit)) | 1)
    thick = cv2.morphologyEx(green, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thick_k, thick_k)))
    band = cv2.bitwise_and(green, cv2.bitwise_not(cv2.dilate(thick, np.ones((5, 5), np.uint8))))
    band = cv2.morphologyEx(band, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(band)
    rings: List[Tuple[float, float, float]] = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 60 * unit:
            continue
        ys, xs = np.nonzero(labels == i)
        fit = _fit_circle(xs, ys)
        # Robust refit: a ring touching other green (leaves, a green cup) drags the first fit off,
        # so drop points far from the current circle and fit again.
        for _ in range(2):
            if fit is None:
                break
            cx, cy, r = fit
            keep = np.abs(np.hypot(xs - cx, ys - cy) - r) < max(3.0, 0.15 * r)
            if keep.sum() < 20:
                fit = None
                break
            xs, ys = xs[keep], ys[keep]
            fit = _fit_circle(xs, ys)
        if fit is None:
            continue
        cx, cy, r = fit
        if not (8 * unit <= r <= 0.3 * min(h, w)):
            continue
        if float(np.mean(np.abs(np.hypot(xs - cx, ys - cy) - r))) > 0.08 * r:
            continue
        thickness = len(xs) / (2 * np.pi * r)
        if not (2.0 * unit <= thickness <= 0.5 * r):
            continue
        # Walk along the fitted circle: a drawn ring is green almost all the way round
        # (except where clipped by the panel edge); stray arcs of foliage or clothing are not.
        t = np.linspace(0, 2 * np.pi, 180, endpoint=False)
        px = np.round(cx + r * np.cos(t)).astype(int)
        py = np.round(cy + r * np.sin(t)).astype(int)
        inside = (px >= 0) & (px < w) & (py >= 0) & (py < h)
        if inside.mean() < 0.5:
            continue
        on_ring = cv2.dilate(green, np.ones((3, 3), np.uint8))[py[inside], px[inside]] > 0
        if float(np.mean(on_ring)) < 0.80:
            continue
        rings.append((cx, cy, r))
    return rings


def compare_game_sheet(
    image: np.ndarray,
    split_mode: str = "auto",
    diff_threshold: int = 18,
    min_area: int = 12,
    blur_radius: int = 3,
    max_differences: Optional[int] = None,
    extra_differences: int = 0,
    custom_boxes: Optional[Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]] = None,
    use_fixed_wechat: bool = False,
    skip_circles: Optional[List[Tuple[float, float, float]]] = None,
) -> Tuple[DiffResult, np.ndarray]:
    """
    Main high-level comparison pipeline:
    1. Detects panel viewports (or uses custom calibrated boxes).
    2. Micro-aligns panels and auto-detects target count from UI '?' badges.
    3. Compares normalized panels using LAB delta E and dilation clustering.
    4. Annotates symmetric difference marks.

    skip_circles: [(cx, cy, r)] in reference-panel pixels of candidates the player rejected
    (the game did not accept a click there); they are excluded like already-found rings so the
    next-best candidate is shown instead.
    """
    start_time = time.perf_counter()

    if custom_boxes is not None:
        (rx, ry, rw, rh), (tx, ty, tw, th) = custom_boxes
        ref_panel = image[ry : ry + rh, rx : rx + rw].copy()
        tgt_panel = image[ty : ty + th, tx : tx + tw].copy()
        ref_offset = (rx, ry)
        tgt_offset = (tx, ty)
        effective_mode = "custom"
    else:
        ref_panel, tgt_panel, effective_mode, ref_offset, tgt_offset = split_game_sheet(
            image, split_mode=split_mode, return_offsets=True, use_fixed_wechat=use_fixed_wechat
        )

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

    # Auto-detect target differences count from UI question mark slots if not explicitly set
    effective_max = max_differences
    auto_badge_count = None
    found_count = None
    exclude_circles: List[Tuple[float, float, float]] = []
    rings_used = False
    if effective_max is None or effective_max <= 0:
        status = detect_badge_status(image)
        if status is not None and status[0] > 0:
            auto_badge_count, found_count = status
            effective_max = auto_badge_count

    # Apply manual delta adjustment if specified
    if effective_max is not None and effective_max > 0 and extra_differences != 0:
        effective_max = max(1, effective_max + extra_differences)

    # Micro-align panels to absorb asymmetric borders, independent widths, or minor translation jitter
    ref_aligned, tgt_aligned, (ref_sub_x, ref_sub_y), (tgt_sub_x, tgt_sub_y) = align_panels_content(
        ref_panel, tgt_panel
    )

    # Already-found differences: the game circles them in green. Use those rings (the game's own
    # notion of how big one difference is) to exclude them, and only look for the remaining '?' slots.
    if found_count:
        rings = detect_found_rings(ref_aligned)
        # Trust the ring detector only when it roughly agrees with the number of checked badges.
        if 0 < len(rings) <= found_count + 1:
            exclude_circles = rings
            rings_used = True
            remaining = max(0, auto_badge_count - found_count)
            effective_max = remaining
            if extra_differences != 0:
                effective_max = max(1, remaining + extra_differences)

    if skip_circles:
        exclude_circles = list(exclude_circles) + [tuple(map(float, c)) for c in skip_circles]

    if effective_max == 0:
        differences = []
    else:
        differences = detect_differences(
            ref_panel=ref_aligned,
            tgt_panel=tgt_aligned,
            diff_threshold=diff_threshold,
            min_area=min_area,
            blur_radius=blur_radius,
            border_margin=8,
            target_count=effective_max if (effective_max is not None and effective_max > 0) else None,
            exclude_circles=exclude_circles or None,
        )

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
        target_badge_count=auto_badge_count,
        found_count=found_count if rings_used else None,
    )

    return result, annotated_image
