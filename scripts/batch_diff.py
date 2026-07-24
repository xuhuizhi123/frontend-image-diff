#!/usr/bin/env python
"""
batch_diff.py - Batch image comparison with automatic pairing and parallel processing.

Compares all images in two directories, automatically pairs them by filename
or perceptual hash similarity, processes them in parallel, and outputs
a JSON results file.

Usage:
    python batch_diff.py --dir-a ./screenshots_v1/ --dir-b ./screenshots_v2/ --output ./output
    python batch_diff.py --dir-a ./v1/ --dir-b ./v2/ --output ./output --sensitivity high --workers 8
"""

import argparse
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from image_diff import compare_images
from utils.auto_pair import auto_pair


def _compare_pair_wrapper(args):
    """Wrapper function for ProcessPoolExecutor (must be top-level for pickling)."""
    img_a, img_b, output_dir, sensitivity, save_crops = args
    return compare_images(img_a, img_b, output_dir, sensitivity, save_crops)


def batch_compare(dir_a, dir_b, output_dir, sensitivity="medium",
                  max_workers=4, save_crops=False):
    """
    Batch compare images from two directories.

    Args:
        dir_a: Path to first directory.
        dir_b: Path to second directory.
        output_dir: Output directory for results.
        sensitivity: "low", "medium", or "high".
        max_workers: Number of parallel worker processes.
        enable_ai_crops: If True, save cropped diff regions for AI analysis.

    Returns:
        dict with keys:
            - pairs: list of comparison results
            - unmatched_a: list of unmatched image paths from dir_a
            - unmatched_b: list of unmatched image paths from dir_b
            - summary: summary statistics
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    # Auto-pair images
    pairs, unmatched_a, unmatched_b = auto_pair(dir_a, dir_b)

    print(f"[batch] Found {len(pairs)} pairs to compare, "
          f"{len(unmatched_a)} unmatched in A, {len(unmatched_b)} unmatched in B")

    if not pairs:
        return {
            "pairs": [],
            "unmatched_a": [str(f) for f in unmatched_a],
            "unmatched_b": [str(f) for f in unmatched_b],
            "summary": {"total_pairs": 0, "total_diffs": 0, "elapsed_seconds": 0},
        }

    # Prepare arguments for parallel processing
    task_args = [
        (str(a), str(b), str(output_dir), sensitivity, save_crops)
        for a, b in pairs
    ]

    results = []

    # Use min(max_workers, len(pairs)) to avoid creating unnecessary processes
    actual_workers = min(max_workers, len(pairs))

    if actual_workers <= 1:
        # Sequential processing for single pair or when workers=1
        for i, args in enumerate(task_args):
            print(f"[batch] Comparing pair {i + 1}/{len(pairs)}...")
            result = _compare_pair_wrapper(args)
            results.append(result)
    else:
        # Parallel processing
        with ProcessPoolExecutor(max_workers=actual_workers) as executor:
            futures = {
                executor.submit(_compare_pair_wrapper, args): (i, args)
                for i, args in enumerate(task_args)
            }
            for future in as_completed(futures):
                idx, _ = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    pair_name = result.get("pair_name", f"pair_{idx}")
                    diff_count = result.get("diff_count", "?")
                    score = result.get("score_percent", "?")
                    print(f"[batch] Completed: {pair_name} "
                          f"(score={score}, diffs={diff_count})")
                except Exception as e:
                    print(f"[batch] Error in pair {idx}: {e}")
                    results.append({"pair_name": f"pair_{idx}", "error": str(e)})

    # Sort results by pair name
    results.sort(key=lambda r: r.get("pair_name", ""))

    elapsed = time.time() - start_time

    # Calculate summary
    successful = [r for r in results if "error" not in r]
    total_diffs = sum(r.get("diff_count", 0) for r in successful)
    total_extra = sum(r.get("extra_a_count", 0) + r.get("extra_b_count", 0)
                      for r in successful)
    avg_score = (sum(r.get("score", 0) for r in successful) / len(successful)
                 if successful else 0)

    summary = {
        "total_pairs": len(pairs),
        "successful": len(successful),
        "failed": len(results) - len(successful),
        "total_diffs": total_diffs,
        "total_extra_regions": total_extra,
        "avg_similarity": round(avg_score, 4),
        "avg_similarity_percent": f"{avg_score * 100:.1f}%",
        "elapsed_seconds": round(elapsed, 2),
    }

    output = {
        "pairs": results,
        "unmatched_a": [str(f) for f in unmatched_a],
        "unmatched_b": [str(f) for f in unmatched_b],
        "summary": summary,
    }

    # Save JSON results
    json_path = output_dir / "batch_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[batch] Done! {len(successful)}/{len(pairs)} pairs compared, "
          f"{total_diffs} differences found in {elapsed:.1f}s")
    print(f"[batch] Results saved to: {json_path}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Batch compare images from two directories"
    )
    parser.add_argument("--dir-a", required=True, help="First directory")
    parser.add_argument("--dir-b", required=True, help="Second directory")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--sensitivity", default="medium",
                        choices=["low", "medium", "high"],
                        help="Sensitivity level (default: medium)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
    parser.add_argument("--save-crops", action="store_true",
                        help="Save per-region crop files for AI analysis (uses more tokens)")
    args = parser.parse_args()

    result = batch_compare(
        args.dir_a, args.dir_b, args.output, args.sensitivity,
        args.workers, save_crops=args.save_crops
    )

    # Print summary
    s = result["summary"]
    print(f"\n{'='*60}")
    print(f"Batch Comparison Summary")
    print(f"{'='*60}")
    print(f"Total pairs:     {s['total_pairs']}")
    print(f"Successful:      {s['successful']}")
    print(f"Failed:          {s['failed']}")
    print(f"Total diffs:     {s['total_diffs']}")
    print(f"Avg similarity:  {s['avg_similarity_percent']}")
    print(f"Elapsed:         {s['elapsed_seconds']}s")

    if result["unmatched_a"]:
        print(f"\nUnmatched in A: {len(result['unmatched_a'])}")
        for f in result["unmatched_a"]:
            print(f"  - {f}")
    if result["unmatched_b"]:
        print(f"\nUnmatched in B: {len(result['unmatched_b'])}")
        for f in result["unmatched_b"]:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
