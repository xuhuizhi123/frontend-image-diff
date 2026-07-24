"""
一键 Web 截图 → 拼接 → 比对 → 报告 工作流

工作流：
  1. 用 Playwright 访问网页，分块截取各路由页面
  2. 拼接分块为完整长图
  3. 与本地原型图批量对比
  4. 生成 MD 报告

用法：
  # 使用内置默认配置（URL + 路由都已预设）
  python web_to_diff.py --proto-dir "C:/path/to/prototypes" --work-dir ".workbuddy/web_diff"

  # 完整参数
  python web_to_diff.py \
    --base-url "https://example.com" \
    --routes '[{"name":"首页","route":"/#/home"},{"name":"设置","route":"/#/settings"}]' \
    --device "iPhone 8" \
    --proto-dir "C:/path/to/prototypes" \
    --work-dir ".workbuddy/web_diff" \
    --sensitivity medium
"""
import os
import sys
import json
import argparse
import subprocess
import shutil


# ===== 可移植路径解析（环境变量 > PATH > 可选 workbuddy 回退）=====
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = SKILL_DIR
SKILL_ROOT = os.path.abspath(os.path.join(SKILL_DIR, '..'))


def _which(cmd):
    return shutil.which(cmd)


def _resolve_python():
    # FRONTEND_DIFF_PYTHON / PYTHON 可覆盖
    for key in ('FRONTEND_DIFF_PYTHON', 'PYTHON'):
        p = os.environ.get(key)
        if p and os.path.isfile(p):
            return p
    # 可选：本机若装了 workbuddy，仍可用（不强制）
    wb = os.path.expandvars(
        r'%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
    )
    if os.path.isfile(wb):
        return wb
    return _which('python') or _which('python3') or sys.executable


def _resolve_node():
    for key in ('FRONTEND_DIFF_NODE',):
        p = os.environ.get(key)
        if p and os.path.isfile(p):
            return p
    # 可选：本机若装了 workbuddy 常用版本，仍可用（不强制、不写死用户名）
    if os.name == 'nt':
        wb_fixed = os.path.expandvars(
            r'%USERPROFILE%\.workbuddy\binaries\node\versions\22.22.2\node.exe'
        )
    else:
        wb_fixed = os.path.expanduser(
            '~/.workbuddy/binaries/node/versions/22.22.2/node'
        )
    if os.path.isfile(wb_fixed):
        return wb_fixed
    return _which('node') or 'node'


def _resolve_node_path():
    """返回含 playwright 包的 node_modules 目录。"""
    env = os.environ.get('FRONTEND_DIFF_NODE_PATH') or os.environ.get('NODE_PATH')
    if env:
        for part in env.split(os.pathsep):
            part = part.strip()
            if part and os.path.isdir(os.path.join(part, 'playwright')):
                return part
            # 允许直接指向含 node_modules 的上级
            nm = os.path.join(part, 'node_modules')
            if os.path.isdir(os.path.join(nm, 'playwright')):
                return nm

    candidates = [
        os.path.join(SKILL_ROOT, 'node_modules'),
        os.path.join(os.getcwd(), 'node_modules'),
    ]
    # 可选 workbuddy（按用户主目录，不写死用户名）
    wb_nm = os.path.expandvars(
        r'%USERPROFILE%\.workbuddy\binaries\node\workspace\node_modules'
    )
    if os.name != 'nt':
        wb_nm = os.path.expanduser('~/.workbuddy/binaries/node/workspace/node_modules')
    candidates.append(wb_nm)

    for c in candidates:
        if c and os.path.isdir(os.path.join(c, 'playwright')):
            return c
    return ''


PYTHON = _resolve_python()
NODE = _resolve_node()
NODE_PATH = _resolve_node_path()


def _print_runtime():
    print(f"  python:    {PYTHON}")
    print(f"  node:      {NODE}")
    print(f"  NODE_PATH: {NODE_PATH or '(empty — run: npm install  in skill root)'}")
    if not NODE_PATH:
        print("  WARNING: playwright not found under NODE_PATH; web capture may fail.")


def run_cmd(cmd, env=None, cwd=None):
    """运行命令并打印输出"""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print(f"  RUN: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=merged_env, cwd=cwd,
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=900)
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            try:
                print(f"  {line}")
            except UnicodeEncodeError:
                print(f"  {line.encode('utf-8', errors='replace').decode('utf-8', errors='replace')}")
    if result.returncode != 0:
        err = (result.stderr or '')[:500]
        try:
            print(f"  ERROR (code={result.returncode}): {err}")
        except UnicodeEncodeError:
            print(f"  ERROR (code={result.returncode})")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Web截图 → 拼接 → 比对 → 报告 一键工作流")
    parser.add_argument('--base-url', default='https://fat.bitechdevelop.com/pdkjwpolicy-operation-h5',
                        help='页面基地址')
    parser.add_argument('--routes', type=json.loads, default=None,
                        help='路由列表 JSON')
    parser.add_argument('--device', default='iPhone 8',
                        help='Playwright 设备名（如 "iPhone 8", "iPhone 13"）')
    parser.add_argument('--proto-dir', required=True,
                        help='本地原型图目录')
    parser.add_argument('--work-dir', required=True,
                        help='工作目录（存放截图和比对结果）')
    parser.add_argument('--sensitivity', default='medium',
                        choices=['low', 'medium', 'high'],
                        help='差异检测灵敏度')
    parser.add_argument('--step', type=int, default=500,
                        help='滚动步长 CSS px')
    parser.add_argument('--workers', type=int, default=4,
                        help='并行比对进程数')
    args = parser.parse_args()

    print("\nRuntime:")
    _print_runtime()

    web_dir = os.path.join(args.work_dir, 'web_screenshots')
    compare_dir = os.path.join(args.work_dir, 'compare_output')

    if not NODE_PATH:
        print("\n[FAILED] Cannot find playwright. In the skill root run:")
        print(f"  cd \"{SKILL_ROOT}\"")
        print("  npm install")
        print("Or set FRONTEND_DIFF_NODE_PATH to a node_modules directory that contains playwright.")
        sys.exit(1)
    # ===== Step 1: Web 截图 =====
    print("\n" + "="*60)
    print("Step 1/4: Capturing web screenshots...")
    print("="*60)

    capture_script = os.path.join(SCRIPTS_DIR, 'web_capture.js')
    capture_cmd = [
        NODE, capture_script,
        '--base-url', args.base_url,
        '--device', args.device,
        '--output', web_dir,
        '--step', str(args.step),
    ]
    if args.routes:
        capture_cmd.extend(['--routes', json.dumps(args.routes)])

    # 清空旧截图
    if os.path.exists(web_dir):
        shutil.rmtree(web_dir)

    rc = run_cmd(capture_cmd, env={'NODE_PATH': NODE_PATH})
    if rc != 0:
        print("\n[FAILED] Web capture failed. Check the errors above.")
        sys.exit(1)

    # ===== Step 2: 拼接分块 =====
    print("\n" + "="*60)
    print("Step 2/4: Stitching chunks...")
    print("="*60)

    stitch_script = os.path.join(SCRIPTS_DIR, 'web_stitch.py')
    rc = run_cmd([
        PYTHON, stitch_script,
        '--chunks-dir', web_dir,
        '--output', web_dir,
    ])
    if rc != 0:
        print("\n[FAILED] Stitching failed.")
        sys.exit(1)

    # 列出拼接好的图片
    stitched = sorted([f for f in os.listdir(web_dir) if f.endswith('.png') and not f.startswith('chunk')])
    print(f"  Stitched images ({len(stitched)}): {', '.join(stitched)}")

    # ===== Step 3: 批量比对 =====
    print("\n" + "="*60)
    print("Step 3/4: Running batch comparison...")
    print("="*60)

    if os.path.exists(compare_dir):
        shutil.rmtree(compare_dir)

    batch_script = os.path.join(SCRIPTS_DIR, 'batch_diff.py')
    rc = run_cmd([
        PYTHON, batch_script,
        '--dir-a', args.proto_dir,
        '--dir-b', web_dir,
        '--output', compare_dir,
        '--sensitivity', args.sensitivity,
        '--workers', str(args.workers),
    ])
    if rc != 0:
        print("\n[FAILED] Batch comparison failed.")
        sys.exit(1)

    # ===== Step 4: 生成报告 =====
    print("\n" + "="*60)
    print("Step 4/4: Generating report...")
    print("="*60)

    results_json = os.path.join(compare_dir, 'batch_results.json')
    report_md = os.path.join(compare_dir, 'report.md')

    report_script = os.path.join(SCRIPTS_DIR, 'report_gen.py')
    rc = run_cmd([
        PYTHON, report_script,
        '--results', results_json,
        '--output', report_md,
        '--dir-a', os.path.basename(args.proto_dir),
        '--dir-b', 'web_impl',
        '--sensitivity', args.sensitivity,
    ])
    if rc != 0:
        print("\n[WARNING] Report generation failed, but comparison results are available.")

    # ===== 汇总 =====
    # 读取结果统计
    summary = {}
    if os.path.exists(results_json):
        with open(results_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        s = data.get('summary', {})
        total_pairs = s.get('total_pairs', 0)
        total_diffs = s.get('total_diffs', 0)
        avg_score = s.get('avg_similarity_percent', 'N/A')

        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"  Pairs compared: {total_pairs}")
        print(f"  Total diffs:    {total_diffs}")
        print(f"  Avg similarity: {avg_score}")
        print(f"\n  Comparison images: {compare_dir}/comparison_*.png")
        print(f"  Report:            {report_md}")
        print(f"  Web screenshots:   {web_dir}/")

    print("\nDone! Check the comparison images to verify the results.")


if __name__ == '__main__':
    main()
