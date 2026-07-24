# 使用示例

假设 skill 根目录为当前目录（含 `scripts/`），且已执行：

```bash
pip install -r requirements.txt
npm install
```

## 单对图片比对

```bash
python scripts/image_diff.py \
  --a "/path/to/image_a.png" \
  --b "/path/to/image_b.png" \
  --output "/path/to/output" \
  --sensitivity medium
```

## 批量比对（推荐）

```bash
python scripts/batch_diff.py \
  --dir-a "/path/to/screenshots_v1" \
  --dir-b "/path/to/screenshots_v2" \
  --output "/path/to/output" \
  --sensitivity medium \
  --workers 4
```

## 生成 MD 报告

```bash
python scripts/report_gen.py \
  --results "/path/to/output/batch_results.json" \
  --output "/path/to/output/report.md" \
  --descriptions "/path/to/output/descriptions.json" \
  --dir-a "screenshots_v1" \
  --dir-b "screenshots_v2" \
  --sensitivity medium
```

## 灵敏度说明

- `low`: 只报告大差异，忽略细微变化
- `medium`: 平衡模式，适合大多数场景
- `high`: 报告细微差异，但可能产生更多噪声

## 输出文件

- `batch_results.json`: 所有比对结果
- `comparison_*.png`: 带标注的对比图
- `crops_*/region_*_a.png` / `crops_*/region_*_b.png`: 差异区域裁剪图
- `report.md`: 最终报告

## 完整工作流示例

假设你有两套截图：

- `/data/png_v1/`: 旧版本截图
- `/data/png_v2/`: 新版本截图

### 步骤 1：批量比对

```bash
python scripts/batch_diff.py \
  --dir-a "/data/png_v1" \
  --dir-b "/data/png_v2" \
  --output "/data/diff_output" \
  --sensitivity medium \
  --workers 4
```

### 步骤 2：AI 语义描述

读取 `/data/diff_output/batch_results.json`：

- 对每对有差异的图片，查看对比图
- 用一句话描述每个差异区域
- 保存为 `/data/diff_output/descriptions.json`：

```json
{
  "首页:1": "Fat版字体偏粗",
  "首页:2": "轮播图数量不同，A版2张B版3张",
  "政策:1": "缺少'政策直达'模块"
}
```

### 步骤 3：生成报告

```bash
python scripts/report_gen.py \
  --results "/data/diff_output/batch_results.json" \
  --output "/data/diff_output/report.md" \
  --descriptions "/data/diff_output/descriptions.json" \
  --dir-a "png_v1" \
  --dir-b "png_v2" \
  --sensitivity medium
```

最终打开 `/data/diff_output/report.md` 查看结果。

## 跨机器说明

不要写死某用户目录。若 PATH 中已有 `python` / `node`，直接按上面命令即可。需要指定解释器时：

```bash
# Windows PowerShell
$env:FRONTEND_DIFF_PYTHON="C:\Python312\python.exe"
$env:FRONTEND_DIFF_NODE_PATH="D:\tools\my-project\node_modules"
python scripts/web_to_diff.py --proto-dir "...\proto" --work-dir "...\out"
```
