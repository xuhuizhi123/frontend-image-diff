"""
align.py - Image alignment for frontend screenshot comparison.

Strategy depends on the dimensions:

1. Identical dims -> direct comparison, no alignment needed.
2. Same width, different height -> top-align, compare common height,
   mark the extra bottom of the taller image with a blue line.
3. Different width -> ORB feature matching + affine warp of A to B's
   full size. This preserves A's local features (warp is based on actual
   feature matches, not pixel interpolation), so pixel-level SSIM
   works well. Same as the v1 approach that produced 96%+ similarity
   on file-explorer screenshots.

We do NOT use simple resize for case 3, because INTER_AREA resize on
both images introduces pixel-level noise that SSIM treats as real
differences, polluting the result.
"""

import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


def register_images(img_a, img_b):
    """
    Align two frontend screenshots for comparison.

    Returns:
        dict with:
        - overlap_a: region of A that will be compared (aligned to overlap_b's size)
        - overlap_b: region of B that will be compared
        - extra_a_resized: list of (x, y, w, h, direction) extra regions
                           in ORIGINAL A coordinates
        - extra_b_resized: list of (x, y, w, h, direction) extra regions
                           in ORIGINAL B coordinates
        - method: "none", "top_aligned", or "orb_warp"
        - inv_warp: 2x3 inverse affine matrix (only for "orb_warp"), or None
    """
    h_a, w_a = img_a.shape[:2]
    h_b, w_b = img_b.shape[:2]

    # Case 1: identical dimensions -> direct comparison
    if (h_a, w_a) == (h_b, w_b):
        return {
            "overlap_a": img_a,
            "overlap_b": img_b,
            "extra_a_resized": [],
            "extra_b_resized": [],
            "method": "none",
            "inv_warp": None,
        }

    # Case 2: same width, different height -> top align, mark extra bottom
    if w_a == w_b:
        return _top_align_same_width(img_a, img_b, w_a, h_a, h_b)

    # Case 3: different width -> ORB affine warp of A to B's full size
    return _orb_warp_a_to_b(img_a, img_b)


def _top_align_same_width(img_a, img_b, w, h_a, h_b):
    """Top-align two images with the same width. Mark extra bottom with blue."""
    common_h = min(h_a, h_b)
    overlap_a = img_a[0:common_h, 0:w]
    overlap_b = img_b[0:common_h, 0:w]

    extra_a = []
    extra_b = []
    if h_a > h_b:
        extra_a.append((0, h_b, w, h_a - h_b, "bottom"))
    elif h_b > h_a:
        extra_b.append((0, h_a, w, h_b - h_a, "bottom"))

    logger.info("Top-aligned (same width %d): common_h=%d, extra_a=%d, extra_b=%d",
                w, common_h, len(extra_a), len(extra_b))

    return {
        "overlap_a": overlap_a,
        "overlap_b": overlap_b,
        "extra_a_resized": extra_a,
        "extra_b_resized": extra_b,
        "method": "top_aligned",
        "inv_warp": None,
    }


def _orb_warp_a_to_b(img_a, img_b):
    """
    Warp A to B's full size using ORB feature matching + affine transform.

    This is the v1 approach: warp the entire A image to B's dimensions
    so they can be SSIM-compared at the same scale. Local features are
    preserved by the affine transform.

    Falls back to top-aligned resize if ORB registration fails.
    """
    h_a, w_a = img_a.shape[:2]
    h_b, w_b = img_b.shape[:2]

    warp = _try_orb_warp(img_a, img_b, w_b, h_b)
    if warp is not None:
        return warp

    # Fallback: top-aligned resize to common width
    logger.warning("ORB warp failed, falling back to top-aligned resize")
    target_w = min(w_a, w_b)
    new_h_a = int(round(h_a * target_w / w_a))
    new_h_b = int(round(h_b * target_w / w_b))
    resized_a = cv2.resize(img_a, (target_w, new_h_a), interpolation=cv2.INTER_AREA)
    resized_b = cv2.resize(img_b, (target_w, new_h_b), interpolation=cv2.INTER_AREA)
    common_h = min(new_h_a, new_h_b)
    overlap_a = resized_a[0:common_h, 0:target_w]
    overlap_b = resized_b[0:common_h, 0:target_w]
    extra_a = []
    extra_b = []
    if new_h_a > new_h_b:
        extra_a.append((0, new_h_b, target_w, new_h_a - new_h_b, "bottom"))
    elif new_h_b > new_h_a:
        extra_b.append((0, new_h_a, target_w, new_h_b - new_h_a, "bottom"))
    return {
        "overlap_a": overlap_a,
        "overlap_b": overlap_b,
        "extra_a_resized": extra_a,
        "extra_b_resized": extra_b,
        "method": "resize_fallback",
        "inv_warp": None,
    }


def _try_orb_warp(img_a, img_b, w_b, h_b):
    """Try to compute an affine transform from A to B using ORB features."""
    h_a, w_a = img_a.shape[:2]
    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=3000)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)

    if des_a is None or des_b is None or len(des_a) < 10 or len(des_b) < 10:
        return None

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des_a, des_b, k=2)

    good = []
    for pair in matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good.append(m)

    if len(good) < 10:
        return None

    src = np.float32([kp_a[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_b[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    M, inlier_mask = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0
    )
    if M is None:
        return None
    inliers = int(np.sum(inlier_mask)) if inlier_mask is not None else 0
    if inliers < 8:
        return None

    # Warp A to B's full size
    overlap_a = cv2.warpAffine(img_a, M, (w_b, h_b), flags=cv2.INTER_LINEAR)
    overlap_b = img_b
    M_inv = cv2.invertAffineTransform(M)

    scale = float(np.sqrt(M[0, 0] ** 2 + M[0, 1] ** 2))
    logger.info("ORB warp: %d matches, %d inliers, scale=%.4f, "
                "A[%dx%d]->B[%dx%d]",
                len(good), inliers, scale, w_a, h_a, w_b, h_b)

    # Extra regions: parts of B not covered by warped A, or vice versa.
    # With affine warp of A to B's full size, A's content is fully warped
    # into B's frame. If A is much smaller in scale, the warped A may
    # cover only a portion of B (and parts of A may warp outside B).
    # For simplicity, we don't detect these here -- the v1 approach
    # didn't either. Blue lines are only for the top_aligned case.
    return {
        "overlap_a": overlap_a,
        "overlap_b": overlap_b,
        "extra_a_resized": [],
        "extra_b_resized": [],
        "method": "orb_warp",
        "inv_warp": M_inv,
    }


# Backward compatibility
def align_images(img_a, img_b):
    """Legacy interface -- delegates to register_images()."""
    reg = register_images(img_a, img_b)
    return reg["overlap_a"], reg["overlap_b"], 1.0, reg["method"]
