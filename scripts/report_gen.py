#!/usr/bin/env python
"""
report_gen.py - Markdown report generator for image comparison results.

Generates a comprehensive MD report with:
- Summary table of all compared pairs
- Side-by-side comparison images with diff annotations
- Detailed diff region descriptions (from AI analysis or placeholder)

Usage:
    python report_gen.py --results ./output/batch_results.json --output ./output/report.md
    python report_gen.py --results ./output/batch_results.json --output ./output/report.md --descriptions ./output/descriptions.json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


def generate_report(results, output_path, descriptions=None, dir_a="", dir_b="",
                    sensitivity="medium"):
    """
    Generate a Markdown report from batch comparison results.

    Args:
        results: Batch results dict (from batch_diff.py).
        output_path: Path to save the MD report.
        descriptions: Optional dict mapping "pair_name:region_index" to description text.
        dir_a: Source directory A name (for report header).
        dir_b: Source directory B name (for report header).
        sensitivity: Sensitivity level used.
    """
    if descriptions is None:
        descriptions = {}

    lines = []
    pairs = results.get("pairs", [])
    summary = results.get("summary", {})
    unmatched_a = results.get("unmatched_a", [])
    unmatched_b = results.get("unmatched_b", [])

    # Header
    lines.append("# 图片对比报告")
    lines.append("")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"> 生成时间: {now}")
    if dir_a and dir_b:
        lines.append(f"> 比对目录: A({dir_a}) vs B({dir_b})")
    lines.append(f"> 灵敏度: {sensitivity}")
    lines.append(f"> 总计: {summary.get('total_pairs', 0)} 对图片, "
                 f"发现 {summary.get('total_diffs', 0)} 处内容差异, "
                 f"{summary.get('total_extra_regions', 0)} 处额外区域, "
                 f"平均相似度 {summary.get('avg_similarity_percent', 'N/A')}")
    lines.append("")

    # Summary table
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 图片 | 相似度 | 内容差异 | 额外区域 | 状态 |")
    lines.append("|------|--------|----------|----------|------|")

    for pair in pairs:
        name = pair.get("pair_name", "unknown")
        if "error" in pair:
            lines.append(f"| {name} | - | - | - | 错误: {pair['error'][:30]} |")
            continue
        score = pair.get("score_percent", "N/A")
        diff_count = pair.get("diff_count", 0)
        extra_count = pair.get("extra_a_count", 0) + pair.get("extra_b_count", 0)
        if diff_count == 0 and extra_count == 0:
            status = "✅ 一致"
        else:
            parts = []
            if diff_count > 0:
                parts.append(f"{diff_count}处差异")
            if extra_count > 0:
                parts.append(f"{extra_count}处额外")
            status = "⚠️ " + ", ".join(parts)
        lines.append(f"| {name} | {score} | {diff_count} | {extra_count} | {status} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed sections for each pair
    for pair in pairs:
        name = pair.get("pair_name", "unknown")

        if "error" in pair:
            lines.append(f"## {name} (错误)")
            lines.append("")
            lines.append(f"比对失败: {pair['error']}")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        score = pair.get("score_percent", "N/A")
        diff_count = pair.get("diff_count", 0)
        align_method = pair.get("alignment_method", "unknown")
        # New fields: scale_a, scale_b. Fallback to scale_factor for backward compat.
        scale = pair.get("scale_factor", 1.0)
        if scale == 1.0:
            scale = pair.get("scale_a", 1.0)
        comparison_image = pair.get("comparison_image", "")
        regions = pair.get("regions", [])
        extra_a = pair.get("extra_a", [])
        extra_b = pair.get("extra_b", [])
        overlap_size = pair.get("overlap_size", [])
        img_a_size = pair.get("image_a_size", [])
        img_b_size = pair.get("image_b_size", [])

        extra_total = len(extra_a) + len(extra_b)
        lines.append(f"## {name} (相似度: {score}, {diff_count}处差异, {extra_total}处额外)")
        lines.append("")

        # Alignment info
        align_text = {
            "none": "无需对齐 (同尺寸)",
            "top_aligned": "顶部对齐 (同宽不同高)",
            "resize_top_aligned": "缩放后顶部对齐 (不同宽高)",
            "resize": "缩放归一化 (旧版)",
            "orb": "ORB特征点校准 (旧版)",
            "resize_fallback": "缩放(ORB失败回退, 旧版)",
        }
        lines.append(f"- 对齐方式: {align_text.get(align_method, align_method)}")
        if align_method != "none":
            scale_a = pair.get("scale_a", 1.0)
            scale_b = pair.get("scale_b", 1.0)
            if scale_a != 1.0 or scale_b != 1.0:
                lines.append(f"- 缩放因子: A×{scale_a}, B×{scale_b}")
        if img_a_size and img_b_size:
            lines.append(f"- 图A尺寸: {img_a_size[1]}×{img_a_size[0]} (宽×高)")
            lines.append(f"- 图B尺寸: {img_b_size[1]}×{img_b_size[0]} (宽×高)")
        if overlap_size:
            lines.append(f"- 重叠区域: {overlap_size[1]}×{overlap_size[0]} (宽×高)")
        lines.append("")

        # Embed comparison image
        if comparison_image:
            img_path = Path(comparison_image)
            report_dir = Path(output_path).parent
            try:
                rel_path = img_path.relative_to(report_dir)
                img_ref = str(rel_path).replace("\\", "/")
            except ValueError:
                img_ref = str(img_path).replace("\\", "/")
            lines.append(f"![{name}对比]({img_ref})")
            lines.append("")
            lines.append("> 红框=内容差异 | 蓝线=仅一侧有的额外内容")
            lines.append("")

        # Extra regions (non-overlapping)
        if extra_a:
            lines.append("### 仅A有的额外内容")
            for ext in extra_a:
                direction = ext.get("direction", "")
                dir_text = {"top": "顶部", "bottom": "底部", "left": "左侧", "right": "右侧"}
                desc_key = f"{name}:extra_a:{direction}"
                desc = descriptions.get(desc_key, "")
                lines.append(f"- **{dir_text.get(direction, direction)}** "
                             f"({ext['w']}×{ext['h']}px)"
                             + (f": {desc}" if desc else ""))
            lines.append("")

        if extra_b:
            lines.append("### 仅B有的额外内容")
            for ext in extra_b:
                direction = ext.get("direction", "")
                dir_text = {"top": "顶部", "bottom": "底部", "left": "左侧", "right": "右侧"}
                desc_key = f"{name}:extra_b:{direction}"
                desc = descriptions.get(desc_key, "")
                lines.append(f"- **{dir_text.get(direction, direction)}** "
                             f"({ext['w']}×{ext['h']}px)"
                             + (f": {desc}" if desc else ""))
            lines.append("")

        # Diff regions (content differences within overlap)
        if diff_count == 0 and not extra_a and not extra_b:
            lines.append("未发现差异。")
        elif diff_count == 0:
            lines.append("重叠区内无内容差异。")
        else:
            for region in regions:
                idx = region["index"]
                desc_key = f"{name}:{idx}"
                desc = descriptions.get(desc_key, "")

                lines.append(f"### 差异 {idx}")
                lines.append(f"- **位置A**: (x={region.get('x_a','?')}, y={region.get('y_a','?')}, "
                             f"w={region['w']}, h={region['h']})")
                lines.append(f"- **位置B**: (x={region.get('x_b','?')}, y={region.get('y_b','?')})")
                if desc:
                    lines.append(f"- **描述**: {desc}")
                else:
                    lines.append(f"- **描述**: _(待AI分析)_")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Unmatched files
    if unmatched_a or unmatched_b:
        lines.append("## 未配对的图片")
        lines.append("")
        if unmatched_a:
            lines.append(f"### 目录A中未配对 ({len(unmatched_a)}张)")
            for f in unmatched_a:
                lines.append(f"- {Path(f).name}")
            lines.append("")
        if unmatched_b:
            lines.append(f"### 目录B中未配对 ({len(unmatched_b)}张)")
            for f in unmatched_b:
                lines.append(f"- {Path(f).name}")
            lines.append("")

    # Write report
    report_content = "\n".join(lines)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"[report] Report saved to: {output_path}")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Generate MD report from batch results")
    parser.add_argument("--results", required=True, help="Path to batch_results.json")
    parser.add_argument("--output", required=True, help="Output MD report path")
    parser.add_argument("--descriptions", help="Path to descriptions JSON file")
    parser.add_argument("--dir-a", default="", help="Source directory A name")
    parser.add_argument("--dir-b", default="", help="Source directory B name")
    parser.add_argument("--sensitivity", default="medium", help="Sensitivity level used")
    args = parser.parse_args()

    with open(args.results, "r", encoding="utf-8") as f:
        results = json.load(f)

    descriptions = {}
    if args.descriptions:
        with open(args.descriptions, "r", encoding="utf-8") as f:
            descriptions = json.load(f)

    generate_report(results, args.output, descriptions, args.dir_a, args.dir_b,
                    args.sensitivity)


if __name__ == "__main__":
    main()
