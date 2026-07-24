"""
auto_pair.py - Automatic image pairing for batch comparison.

Pairs images from two directories by:
1. Filename matching (normalized: case-insensitive, strip spaces/underscores)
2. Perceptual hash (pHash) fallback for unmatched images
"""

import re
from pathlib import Path
from PIL import Image
import imagehash
import logging

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def auto_pair(dir_a, dir_b):
    """
    Automatically pair images from two directories.

    Args:
        dir_a: Path to first directory.
        dir_b: Path to second directory.

    Returns:
        tuple: (pairs, unmatched_a, unmatched_b)
            - pairs: list of (Path_a, Path_b) tuples
            - unmatched_a: list of unmatched Path objects from dir_a
            - unmatched_b: list of unmatched Path objects from dir_b
    """
    dir_a = Path(dir_a)
    dir_b = Path(dir_b)

    files_a = sorted([f for f in dir_a.iterdir()
                      if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()])
    files_b = sorted([f for f in dir_b.iterdir()
                      if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()])

    if not files_a:
        return [], [], files_b
    if not files_b:
        return [], files_a, []

    pairs = []
    unmatched_a = []
    unmatched_b = []

    # Round 1: filename matching
    name_map_b = {}
    for f in files_b:
        key = _normalize_name(f.stem)
        name_map_b[key] = f

    consumed_b = set()
    for fa in files_a:
        key = _normalize_name(fa.stem)
        if key in name_map_b and key not in consumed_b:
            pairs.append((fa, name_map_b[key]))
            consumed_b.add(key)
        else:
            unmatched_a.append(fa)

    unmatched_b = [f for f in files_b if _normalize_name(f.stem) not in consumed_b]

    # Round 2: perceptual hash matching for remaining images
    if unmatched_a and unmatched_b:
        hash_pairs = _pair_by_phash(unmatched_a, unmatched_b)
        for fa, fb in hash_pairs:
            pairs.append((fa, fb))
            unmatched_a.remove(fa)
            unmatched_b.remove(fb)

    logger.info("Auto-pairing: %d pairs matched, %d unmatched in A, %d unmatched in B",
                len(pairs), len(unmatched_a), len(unmatched_b))

    return pairs, unmatched_a, unmatched_b


def _normalize_name(name):
    """
    Normalize a filename for matching.
    Removes spaces, underscores, hyphens, and converts to lowercase.
    """
    name = name.lower()
    name = re.sub(r'[\s_\-]+', '', name)
    return name


def _compute_phash(image_path, hash_size=8):
    """Compute perceptual hash of an image."""
    try:
        img = Image.open(image_path)
        return imagehash.phash(img, hash_size=hash_size)
    except Exception as e:
        logger.warning("Failed to compute pHash for %s: %s", image_path, e)
        return None


def _hamming_distance(hash_a, hash_b):
    """Compute Hamming distance between two perceptual hashes."""
    return hash_a - hash_b


def _pair_by_phash(files_a, files_b, max_distance=20):
    """
    Pair unmatched images by perceptual hash similarity.

    Uses greedy matching: for each image in A, find the closest match in B.
    Max Hamming distance of 20 (out of 64) is considered a match.
    This is lenient enough to match same-page screenshots with UI changes,
    but strict enough to reject completely different pages.
    """
    # Compute hashes
    hashes_a = {}
    for f in files_a:
        h = _compute_phash(f)
        if h is not None:
            hashes_a[f] = h

    hashes_b = {}
    for f in files_b:
        h = _compute_phash(f)
        if h is not None:
            hashes_b[f] = h

    if not hashes_a or not hashes_b:
        return []

    # Greedy matching: find best match for each A image
    pairs = []
    used_b = set()

    # Sort A images by best match distance (ascending) to prioritize strong matches
    all_distances = []
    for fa, ha in hashes_a.items():
        for fb, hb in hashes_b.items():
            dist = _hamming_distance(ha, hb)
            all_distances.append((dist, fa, fb))

    all_distances.sort(key=lambda x: x[0])

    for dist, fa, fb in all_distances:
        if dist > max_distance:
            break
        if fa not in hashes_a or fb in used_b:
            continue
        pairs.append((fa, fb))
        used_b.add(fb)
        del hashes_a[fa]
        if not hashes_a:
            break

    return pairs
