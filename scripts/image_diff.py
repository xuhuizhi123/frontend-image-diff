#!/usr/bin/env python
"""
image_diff.py - Core image comparison engine for frontend page screenshots.

Workflow:
1. Align images (utils/align.py): same-size / top-aligned / ORB warp.
2. Pre-blur with Gaussian (sigma=1.0) to suppress rendering noise.
3. Run SSIM (win_size=11) on the blurred overlap region.
4. Multi-layer noise filtering (fixed threshold + area/dimension/intensity
   checks + proximity merge) to eliminate false positives.
5. Mark content differences with thin red boxes on the ORIGINAL images.
6. Mark extra (non-overlapping) regions with blue lines on the ORIGINAL images.
7. Generate a side-by-side comparison of the annotated originals.

Key design: prototype vs implementation screenshots have inherent rendering
differences (anti-aliasing, font hinting, color profile). The pre-blur +
larger SSIM window + strict filtering chain suppresses these false positives
while catching genuine structural changes.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, str(Path(__file__).parent))
from utils.align import register_images
from utils.noise_filter import filter_diff_mask as filter_diff

# Annotation colors (BGR for OpenCV)
COLOR_RED = (0, 0, 255)       # Content differences
COLOR_BLUE = (255, 0, 0)      # Extra content boundaries
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)

BOX_THICKNESS = 1              # Thin red boxes (precise)
BLUE_LINE_THICKNESS = 2        # Visible blue boundary lines
SEPARATOR_WIDTH = 4
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_SCALE = 0.5
LABEL_THICKNESS = 1


def imread_unicode(path, flags=cv2.IMREAD_COLOR):
    """Read image with Unicode (Chinese) path support on Windows."""
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, flags)


def imwrite_unicode(path, img):
    """Write image with Unicode (Chinese) path support on Windows."""
    ext = Path(str(path)).suffix
    success, encoded = cv2.imencode(ext, img)
    if success:
        encoded.tofile(str(path))
        return True
    return False


def compare_images(img_a_path, img_b_path, output_dir, sensitivity="medium",
                   save_crops=False):
    """
    Compare two images and produce a side-by-side annotated comparison.

    Args:
        img_a_path: Path to first image.
        img_b_path: Path to second image.
        output_dir: Directory to save output files.
        sensitivity: "low", "medium", or "high".
        save_crops: If True, save per-region crop files (saves tokens when False).

    Returns:
        dict with comparison results.
    """
    img_a_path = str(img_a_path)
    img_b_path = str(img_b_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pair_name = Path(img_a_path).stem

    try:
        # Step 1: Load images
        img_a = imread_unicode(img_a_path, cv2.IMREAD_COLOR)
        img_b = imread_unicode(img_b_path, cv2.IMREAD_COLOR)

        if img_a is None:
            return {"pair_name": pair_name, "error": f"Cannot load: {img_a_path}"}
        if img_b is None:
            return {"pair_name": pair_name, "error": f"Cannot load: {img_b_path}"}

        # Step 2: Align images (returns overlap regions already at same size)
        reg = register_images(img_a, img_b)
        overlap_a = reg["overlap_a"]   # same size as overlap_b
        overlap_b = reg["overlap_b"]
        method = reg["method"]
        inv_warp = reg.get("inv_warp")  # None unless method == "orb_warp"
        extra_a_resized = reg["extra_a_resized"]
        extra_b_resized = reg["extra_b_resized"]

        # Step 3: SSIM on overlap region (already same size)
        gray_a = cv2.cvtColor(overlap_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(overlap_b, cv2.COLOR_BGR2GRAY)

        # Safety: ensure same size for SSIM
        if gray_a.shape != gray_b.shape:
            h = min(gray_a.shape[0], gray_b.shape[0])
            w = min(gray_a.shape[1], gray_b.shape[1])
            gray_a = gray_a[0:h, 0:w]
            gray_b = gray_b[0:h, 0:w]

        # Pre-blur: Gaussian blur to smooth out rendering differences
        # (anti-aliasing, font hinting, color profile, sub-pixel alignment).
        # sigma=1.0 is enough to suppress 1-2px anti-aliasing noise while
        # preserving real text/element changes.
        blur_sigma = 1.0
        blur_ksize = 0  # auto-computed from sigma
        gray_a_blur = cv2.GaussianBlur(gray_a, (blur_ksize, blur_ksize), blur_sigma)
        gray_b_blur = cv2.GaussianBlur(gray_b, (blur_ksize, blur_ksize), blur_sigma)

        # SSIM with larger window (win_size=11 vs old 7) for robustness
        # against local pixel noise. gaussian_weights applies a Gaussian
        # weighting within the window.
        score, diff_map = ssim(
            gray_a_blur, gray_b_blur,
            full=True,
            win_size=11,
            gaussian_weights=True,
            sigma=1.5,
            data_range=255.0,
        )

        # Step 4: Filter noise and get bounding boxes (in overlap coordinates)
        boxes = filter_diff(diff_map, overlap_a.shape, sensitivity)

        # Step 5: Map diff boxes to ORIGINAL image coordinates
        # - For case 1 (none) and case 2 (top_aligned, same width):
        #   overlap coordinates == original coordinates
        # - For case 3 (orb_warp): overlap_a is A warped to B's size,
        #   so box in overlap == box in B's original. To map to A's
        #   original, apply inverse affine transform to box corners.
        regions = []
        for i, (rx, ry, rw, rh) in enumerate(boxes):
            # B's original coordinates: same as overlap for ORB; same for resize
            bx_b, by_b, bw_b, bh_b = rx, ry, rw, rh

            if inv_warp is not None:
                # Inverse-warp box corners to A's original
                corners = np.float32([
                    [rx, ry],
                    [rx + rw, ry],
                    [rx + rw, ry + rh],
                    [rx, ry + rh],
                ]).reshape(-1, 1, 2)
                a_corners = cv2.transform(corners, inv_warp)
                xs = a_corners[:, 0, 0]
                ys = a_corners[:, 0, 1]
                bx_a = int(round(max(0, np.min(xs))))
                by_a = int(round(max(0, np.min(ys))))
                bx2_a = int(round(min(img_a.shape[1], np.max(xs))))
                by2_a = int(round(min(img_a.shape[0], np.max(ys))))
                bw_a = max(1, bx2_a - bx_a)
                bh_a = max(1, by2_a - by_a)
                # Clamp B to image bounds
                bx_b = max(0, min(img_b.shape[1] - 1, bx_b))
                by_b = max(0, min(img_b.shape[0] - 1, by_b))
                bw_b = min(bw_b, img_b.shape[1] - bx_b)
                bh_b = min(bh_b, img_b.shape[0] - by_b)
            else:
                # Identity mapping (case 1 & 2)
                bx_a, by_a, bw_a, bh_a = rx, ry, rw, rh

            regions.append({
                "index": i + 1,
                "x_a": bx_a, "y_a": by_a, "w": bw_a, "h": bh_a,
                "x_b": bx_b, "y_b": by_b, "w_b": bw_b, "h_b": bh_b,
            })

        # Step 6: Annotate original images
        marked_a = img_a.copy()
        marked_b = img_b.copy()

        for region in regions:
            idx = region["index"]
            cv2.rectangle(
                marked_a,
                (region["x_a"], region["y_a"]),
                (region["x_a"] + region["w"], region["y_a"] + region["h"]),
                COLOR_RED, BOX_THICKNESS,
            )
            cv2.rectangle(
                marked_b,
                (region["x_b"], region["y_b"]),
                (region["x_b"] + region["w_b"], region["y_b"] + region["h_b"]),
                COLOR_RED, BOX_THICKNESS,
            )
            # Tiny index label above the box
            _draw_label(marked_a, str(idx), region["x_a"], max(0, region["y_a"] - 2), COLOR_RED)
            _draw_label(marked_b, str(idx), region["x_b"], max(0, region["y_b"] - 2), COLOR_RED)

        # Optional: save per-region crops for AI description
        crop_paths = []
        if save_crops and regions:
            crops_dir = output_dir / f"crops_{pair_name}"
            crops_dir.mkdir(exist_ok=True)
            for region in regions:
                idx = region["index"]
                # Crop from overlap images at box coordinates (overlap is same size as B for ORB,
                # or same as top portion for top_aligned / same as A and B for "none").
                # For "none" / "top_aligned", boxes are already in original coords, so
                # we can crop from img_a / img_b directly.
                if method == "orb_warp":
                    rx, ry, rw, rh = region["x_b"], region["y_b"], region["w_b"], region["h_b"]
                    crop_b = _safe_crop(overlap_b, rx, ry, rw, rh, pad=4)
                    crop_a = _safe_crop(overlap_a, rx, ry, rw, rh, pad=4)
                else:
                    crop_a = _safe_crop(img_a, region["x_a"], region["y_a"], region["w"], region["h"], pad=4)
                    crop_b = _safe_crop(img_b, region["x_b"], region["y_b"], region["w_b"], region["h_b"], pad=4)

                if crop_a is not None and crop_b is not None:
                    crop_a_path = crops_dir / f"region_{idx}_a.png"
                    crop_b_path = crops_dir / f"region_{idx}_b.png"
                    imwrite_unicode(crop_a_path, crop_a)
                    imwrite_unicode(crop_b_path, crop_b)
                    crop_paths.append({
                        "index": idx,
                        "crop_a": str(crop_a_path),
                        "crop_b": str(crop_b_path),
                    })

        # Step 7: Draw blue lines for extra (non-overlapping) regions.
        # extra_a_resized / extra_b_resized are already in ORIGINAL coordinates.
        extra_info_a = []
        for (ox, oy, ow, oh, direction) in extra_a_resized:
            _draw_extra_boundary(marked_a, ox, oy, ow, oh, direction, "A")
            extra_info_a.append({
                "x": int(ox), "y": int(oy), "w": int(ow), "h": int(oh), "direction": direction,
            })

        extra_info_b = []
        for (ox, oy, ow, oh, direction) in extra_b_resized:
            _draw_extra_boundary(marked_b, ox, oy, ow, oh, direction, "B")
            extra_info_b.append({
                "x": int(ox), "y": int(oy), "w": int(ow), "h": int(oh), "direction": direction,
            })

        # Step 8: Generate side-by-side comparison of annotated originals
        comparison = _make_side_by_side(marked_a, marked_b)
        comparison_path = output_dir / f"comparison_{pair_name}.png"
        imwrite_unicode(comparison_path, comparison)

        # Step 9: Return results
        result = {
            "pair_name": pair_name,
            "score": round(float(score), 4),
            "score_percent": f"{score * 100:.1f}%",
            "diff_count": len(regions),
            "regions": regions,
            "extra_a": extra_info_a,
            "extra_b": extra_info_b,
            "extra_a_count": len(extra_info_a),
            "extra_b_count": len(extra_info_b),
            "comparison_image": str(comparison_path),
            "crop_paths": crop_paths,
            "alignment_method": method,
            "image_a_size": list(img_a.shape[:2]),
            "image_b_size": list(img_b.shape[:2]),
            "overlap_size": list(overlap_a.shape[:2]),
        }
        return result

    except Exception as e:
        return {"pair_name": pair_name, "error": str(e)}


def _safe_crop(img, x, y, w, h, pad=0):
    """Crop a region with padding, clamped to image bounds. Returns None if invalid."""
    H, W = img.shape[:2]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(W, x + w + pad)
    y1 = min(H, y + h + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    return img[y0:y1, x0:x1]


def _draw_label(img, text, x, y, color):
    """Draw a small label with solid background for readability."""
    (tw, th), _ = cv2.getTextSize(text, LABEL_FONT, LABEL_SCALE, LABEL_THICKNESS)
    ly = max(y, th + 2)
    cv2.rectangle(img, (x, ly - th - 2), (x + tw + 4, ly + 2), color, -1)
    cv2.putText(img, text, (x + 2, ly), LABEL_FONT, LABEL_SCALE,
                COLOR_WHITE, LABEL_THICKNESS, cv2.LINE_AA)


def _draw_extra_boundary(img, x, y, w, h, direction, label_prefix):
    """
    Draw a blue line at the boundary of an extra (non-overlapping) region.
    The line marks the edge where the extra content begins.
    """
    if direction == "bottom":
        # Blue line at the top of the extra bottom region
        line_y = y
        cv2.line(img, (0, line_y), (img.shape[1], line_y),
                 COLOR_BLUE, BLUE_LINE_THICKNESS)
        _draw_label(img, f"仅{label_prefix}有(下)", 4, line_y + 4, COLOR_BLUE)
    elif direction == "right":
        line_x = x
        cv2.line(img, (line_x, y), (line_x, y + h),
                 COLOR_BLUE, BLUE_LINE_THICKNESS)
        _draw_label(img, f"仅{label_prefix}有(右)", line_x + 4, y + 10, COLOR_BLUE)
    elif direction == "top":
        line_y = y + h
        cv2.line(img, (0, line_y), (img.shape[1], line_y),
                 COLOR_BLUE, BLUE_LINE_THICKNESS)
        _draw_label(img, f"仅{label_prefix}有(上)", 4, line_y + 4, COLOR_BLUE)
    elif direction == "left":
        line_x = x + w
        cv2.line(img, (line_x, y), (line_x, y + h),
                 COLOR_BLUE, BLUE_LINE_THICKNESS)
        _draw_label(img, f"仅{label_prefix}有(左)", line_x + 4, y + 10, COLOR_BLUE)


def _make_side_by_side(img_a, img_b):
    """
    Create a side-by-side comparison at the same display height, preserving
    aspect ratio. Pads with gray if heights differ after aspect-preserving
    resize.
    """
    h_a, w_a = img_a.shape[:2]
    h_b, w_b = img_b.shape[:2]

    target_h = max(h_a, h_b)

    if h_a != target_h:
        new_w_a = int(round(w_a * target_h / h_a))
        img_a_r = cv2.resize(img_a, (new_w_a, target_h), interpolation=cv2.INTER_AREA)
    else:
        img_a_r = img_a

    if h_b != target_h:
        new_w_b = int(round(w_b * target_h / h_b))
        img_b_r = cv2.resize(img_b, (new_w_b, target_h), interpolation=cv2.INTER_AREA)
    else:
        img_b_r = img_b

    separator = np.full((target_h, SEPARATOR_WIDTH, 3), 200, dtype=np.uint8)
    return np.hstack([img_a_r, separator, img_b_r])


def main():
    parser = argparse.ArgumentParser(description="Compare two images and find differences")
    parser.add_argument("--a", required=True, help="Path to first image")
    parser.add_argument("--b", required=True, help="Path to second image")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--sensitivity", default="medium",
                        choices=["low", "medium", "high"],
                        help="Sensitivity level (default: medium)")
    parser.add_argument("--save-crops", action="store_true",
                        help="Save per-region crop files (uses more tokens)")
    args = parser.parse_args()

    result = compare_images(
        args.a, args.b, args.output, args.sensitivity, args.save_crops
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
