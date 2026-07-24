"""
noise_filter.py - Robust noise filtering for frontend image difference maps.

Design philosophy:
  Frontend prototype vs implementation screenshots have inherent rendering
  differences (anti-aliasing, font hinting, color profile, sub-pixel
  alignment). These are NOT real differences that developers need to fix.

  This module uses a multi-layer filtering strategy to suppress false
  positives while catching genuine structural changes:

  1. Fixed threshold (not Otsu) — Otsu adapts too low on similar images,
     letting noise flood through.
  2. Minimum area filter — discard regions smaller than a fraction of the
     image (e.g., 0.1% for medium).
  3. Minimum dimension filter — discard boxes thinner/shorter than a few
     pixels (e.g., 12px for medium).
  4. Mean diff intensity check — discard regions where average pixel
     difference is too small (likely just rendering noise).
  5. Proximity-based merging — merge boxes within a few pixels of each other,
     grouping scattered real diffs into coherent regions.
"""

import cv2
import numpy as np

# Sensitivity presets
# diff_threshold: on 0-1 scale (1-diff_map), pixels above this are "different"
# min_area_ratio: minimum fraction of total image area
# min_dimension: minimum width AND height in pixels
# min_mean_diff: minimum average diff intensity within a region
# close_kernel: morphological close to merge nearby diff pixels
# open_kernel: morphological open to remove isolated noise
# merge_proximity: merge boxes within this many pixels of each other
SENSITIVITY = {
    "low": {
        "diff_threshold": 0.20,
        "min_area_ratio": 0.003,
        "min_dimension": 20,
        "min_mean_diff": 0.10,
        "close_kernel": 15,
        "open_kernel": 7,
        "merge_proximity": 40,
    },
    "medium": {
        "diff_threshold": 0.15,
        "min_area_ratio": 0.001,
        "min_dimension": 12,
        "min_mean_diff": 0.08,
        "close_kernel": 13,
        "open_kernel": 5,
        "merge_proximity": 30,
    },
    "high": {
        "diff_threshold": 0.10,
        "min_area_ratio": 0.0005,
        "min_dimension": 8,
        "min_mean_diff": 0.04,
        "close_kernel": 11,
        "open_kernel": 3,
        "merge_proximity": 25,
    },
}


def filter_diff_mask(diff_map, img_shape, sensitivity="medium"):
    """
    Process a raw SSIM difference map into filtered bounding boxes.

    Args:
        diff_map: 2D float array from SSIM (values 0-1, where 1 = identical).
        img_shape: (height, width) of the compared image.
        sensitivity: "low", "medium", or "high".

    Returns:
        list of (x, y, w, h) bounding boxes for genuine difference regions.
    """
    params = SENSITIVITY.get(sensitivity, SENSITIVITY["medium"])

    # diff_map: 0-1 where 1 = identical. Convert to "difference" scale.
    diff = 1.0 - diff_map  # Now 0 = identical, 1 = completely different

    # Layer 1: Fixed threshold binary mask
    # Unlike Otsu (which finds a data-dependent threshold that can be
    # extremely low on similar images), we use a fixed threshold.
    # This ensures consistent behavior: only pixels with SSIM < (1-threshold)
    # are considered different.
    binary = (diff > params["diff_threshold"]).astype(np.uint8) * 255

    # Layer 2: Morphological close — merge nearby diff pixels into regions
    close_k = cv2.getStructuringElement(
        cv2.MORPH_RECT, (params["close_kernel"], params["close_kernel"])
    )
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_k)

    # Layer 3: Morphological open — remove isolated noise pixels
    open_k = cv2.getStructuringElement(
        cv2.MORPH_RECT, (params["open_kernel"], params["open_kernel"])
    )
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_k)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Layer 4: Multi-criteria filtering
    h, w = img_shape[:2]
    total_area = h * w
    min_area = total_area * params["min_area_ratio"]
    min_dim = params["min_dimension"]
    min_mean_diff = params["min_mean_diff"]

    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        x, y, bw, bh = cv2.boundingRect(contour)

        # Dimension filter: skip thin slivers
        if bw < min_dim or bh < min_dim:
            continue

        # Mean diff intensity check: compute average difference within region.
        # If the average is low, it's likely rendering noise (anti-aliasing,
        # font hinting) rather than a real structural change.
        region_diff = diff[y:y + bh, x:x + bw]
        mean_diff = float(np.mean(region_diff))
        if mean_diff < min_mean_diff:
            continue

        boxes.append((x, y, bw, bh))

    # Layer 5: Proximity-based merging — merge boxes that are close
    # but not necessarily overlapping. This groups scattered real diffs
    # (e.g., a button that changed color + its label shifted) into one region.
    boxes = merge_nearby_boxes(boxes, proximity=params["merge_proximity"])

    return boxes


def merge_nearby_boxes(boxes, proximity=30):
    """
    Merge bounding boxes that overlap OR are within `proximity` pixels
    of each other.

    Uses greedy iteration: repeatedly scan all pairs, merge the first
    close pair found, until no more merges are possible.
    """
    if len(boxes) <= 1:
        return boxes

    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _boxes_close(boxes[i], boxes[j], proximity):
                    merged = _merge_boxes(boxes[i], boxes[j])
                    boxes.pop(j)
                    boxes.pop(i)
                    boxes.append(merged)
                    changed = True
                    break
            if changed:
                break

    # Sort by y then x for consistent ordering (top-to-bottom, left-to-right)
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def _boxes_close(box_a, box_b, proximity):
    """
    Check if two boxes overlap OR are within `proximity` pixels of each other.
    Expands box_a by proximity on all sides, then checks for overlap with box_b.
    """
    ax1, ay1, aw, ah = box_a
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx1, by1, bw, bh = box_b
    bx2, by2 = bx1 + bw, by1 + bh

    # Expand box_a by proximity
    ax1_e = ax1 - proximity
    ay1_e = ay1 - proximity
    ax2_e = ax2 + proximity
    ay2_e = ay2 + proximity

    # Check overlap between expanded A and B
    inter_x1 = max(ax1_e, bx1)
    inter_y1 = max(ay1_e, by1)
    inter_x2 = min(ax2_e, bx2)
    inter_y2 = min(ay2_e, by2)

    return inter_x2 > inter_x1 and inter_y2 > inter_y1


def _merge_boxes(box_a, box_b):
    """Merge two bounding boxes into one that encompasses both."""
    ax1, ay1, aw, ah = box_a
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx1, by1, bw, bh = box_b
    bx2, by2 = bx1 + bw, by1 + bh

    x1 = min(ax1, bx1)
    y1 = min(ay1, by1)
    x2 = max(ax2, bx2)
    y2 = max(ay2, by2)

    return (x1, y1, x2 - x1, y2 - y1)
