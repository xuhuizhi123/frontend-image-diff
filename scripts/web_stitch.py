"""
Web 截图分块拼接工具（配合 frontend-image-diff skill 使用）

用法：
  python web_stitch.py --chunks-dir <分块目录> --output <输出目录> [--metadata <metadata.json>]

从 scroll_metadata.json 读取每块的实际滚动位置，精确计算 overlap 后拼接。
- 固定层隐藏成功（fixedHiddenCount>0）时不裁底，避免破坏 overlap 数学、产生半行残影
- 固定层未检出时，非末块仍裁掉底部固定栏高度作兜底
- 下一帧顶部额外丢弃 SEAM_PAD_PX，消化 scrollTop/DPR 取整误差
"""
import os
import sys
import json
import argparse
import cv2
import numpy as np

# Extra physical pixels discarded from the top of each subsequent frame
# to absorb scrollTop * dpr rounding / settle error (ghost half-lines).
SEAM_PAD_PX = 8


def load_image(p):
    buf = np.fromfile(p, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot decode {p}")
    return img


def stitch_directory(chunks_dir, output_path, page_meta, dpr=2):
    chunk_meta = page_meta.get('chunks', page_meta if isinstance(page_meta, list) else [])
    fixed_bottom_css = int(page_meta.get('fixedBottomCssPx', 50) or 50)
    fixed_bottom_px = max(0, int(fixed_bottom_css * dpr))
    fixed_hidden_count = int(page_meta.get('fixedHiddenCount', 0) or 0)
    # When fixed layers were hidden during middle frames, bottom crop would
    # cut real content and break scrollTop-based overlap → seam ghosts.
    crop_bottom = fixed_hidden_count <= 0 and fixed_bottom_px > 0

    images = []
    for cm in chunk_meta:
        p = os.path.join(chunks_dir, cm['file'])
        img = load_image(p)
        images.append((img, cm))

    if not images:
        raise ValueError(f"No images found in {chunks_dir}")

    if len(images) == 1:
        result = images[0][0]
    else:
        viewport_h = images[0][0].shape[0]

        def crop_bottom_if_needed(img, is_last):
            """Only when fixed layers were NOT hidden (fallback)."""
            if not crop_bottom or is_last:
                return img
            keep_h = img.shape[0] - fixed_bottom_px
            if keep_h < 1:
                return img
            return img[:keep_h, :]

        first_img, first_meta = images[0]
        first_is_last = bool(first_meta.get('isLast')) or len(images) == 1
        parts = [crop_bottom_if_needed(first_img, first_is_last)]

        for i in range(1, len(images)):
            img, meta = images[i]
            prev_meta = images[i - 1][1]
            is_last = bool(meta.get('isLast')) or (i == len(images) - 1)

            actual_scroll_diff = meta['actualScroll'] - prev_meta['actualScroll']
            overlap_px = viewport_h - int(actual_scroll_diff * dpr)

            if overlap_px < 0:
                overlap_px = 0
            # Safety pad: drop a few more rows at the seam to kill half-line ghosts
            start = overlap_px + SEAM_PAD_PX
            if start >= img.shape[0]:
                start = max(0, img.shape[0] - 1)

            keep = img[start:, :]
            keep = crop_bottom_if_needed(keep, is_last)
            if keep.shape[0] < 1:
                continue
            parts.append(keep)

        result = np.vstack(parts)

    ok, buf = cv2.imencode('.png', result)
    if not ok:
        raise RuntimeError("Failed to encode stitched image")
    buf.tofile(output_path)
    print(
        f"  -> {result.shape[1]}x{result.shape[0]} "
        f"(cropBottom={crop_bottom}, seamPad={SEAM_PAD_PX}, hidden={fixed_hidden_count})"
    )


def main():
    parser = argparse.ArgumentParser(description="Stitch web screenshot chunks")
    parser.add_argument('--chunks-dir', required=True, help='Directory under _chunks/')
    parser.add_argument('--output', required=True, help='Output directory for stitched images')
    parser.add_argument('--metadata', default=None, help='Path to scroll_metadata.json')
    parser.add_argument('--dpr', type=int, default=2, help='Device pixel ratio')
    args = parser.parse_args()

    # 尝试加载元数据
    meta_path = args.metadata
    if not meta_path:
        meta_path = os.path.join(args.chunks_dir, '_chunks', 'scroll_metadata.json')
    if not os.path.exists(meta_path):
        meta_path = os.path.join(os.path.dirname(args.chunks_dir), '_chunks', 'scroll_metadata.json')

    all_meta = None
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            all_meta = json.load(f)
        print(f"Loaded metadata: {len(all_meta)} pages")

    # 遍历页面目录
    chunks_base = args.chunks_dir
    if '_chunks' not in chunks_base:
        chunks_base = os.path.join(chunks_base, '_chunks')

    for name in sorted(os.listdir(chunks_base)):
        page_dir = os.path.join(chunks_base, name)
        if not os.path.isdir(page_dir):
            continue

        chunks = sorted([f for f in os.listdir(page_dir) if f.endswith('.png')])
        if not chunks:
            continue

        output_path = os.path.join(args.output, f'{name}.png')
        print(f"[{name}] {len(chunks)} chunks", end='')

        if all_meta and name in all_meta:
            stitch_directory(page_dir, output_path, all_meta[name], args.dpr)
        else:
            # 回退：固定 overlap + 默认裁底 + seam pad
            fixed_bottom_px = 50 * args.dpr
            imgs = [load_image(os.path.join(page_dir, c)) for c in chunks]
            if len(imgs) == 1:
                result = imgs[0]
            else:
                vh = imgs[0].shape[0]
                step_px = 500 * args.dpr  # 默认 step
                overlap = vh - step_px
                parts = [imgs[0][: max(1, imgs[0].shape[0] - fixed_bottom_px), :]]
                for i, img in enumerate(imgs[1:]):
                    is_last = i == len(imgs) - 2
                    start = max(1, overlap) + SEAM_PAD_PX
                    if start >= img.shape[0]:
                        start = max(0, img.shape[0] - 1)
                    keep = img[start:, :]
                    if not is_last:
                        keep = keep[: max(1, keep.shape[0] - fixed_bottom_px), :]
                    if keep.shape[0] >= 1:
                        parts.append(keep)
                result = np.vstack(parts)
            ok, buf = cv2.imencode('.png', result)
            buf.tofile(output_path)
            print(f"  -> {result.shape[1]}x{result.shape[0]}")


if __name__ == '__main__':
    main()
