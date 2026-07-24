---

## name: frontend-image-diff
title: "前端图片找不同"
description: "通用前端页面截图视觉差异比对工具，支持Playwright自动截取Web页面+缩放对齐+ORB仿射校准、同宽不同高顶部对齐+蓝线标记、批量并行比对、输出标注对比图+MD报告。"
summary: "通用前端页面截图视觉差异比对工具，支持Playwright自动截取Web页面+缩放对齐+ORB仿射校准、同宽不同高顶部对齐+蓝线标记、批量并行比对、输出标注对比图+MD报告。"
agent_created: true
read_when:
  - 用户提到"图片比对"、"图片对比"、"找不同"、"截图对比"、"视觉差异"、"UI回归"、"页面对比"
  - 用户提供两张图片或两个目录要求对比差异
  - 用户需要前端页面视觉回归测试
  - 用户需要从网页截图然后和原型图对比
  - 用户提到"web截图"、"页面截图"、"自动截图"、"原型对比"

# 前端图片找不同 Skill

通用前端页面截图视觉差异比对工具。针对**前端原型图 vs 实现图**的对比场景优化：自动消除字体渲染/抗锯齿/色域差异导致的误标，只报真正的结构差异。

支持两种数据来源：

- **本地图片**：直接指定两张图或两个目录
- **Web 截图**：自动用 Playwright 访问网页，分块截图+拼接，再与本地原型图对比

## 核心能力

- **Web 自动截图**（新增）：Playwright 设备模拟（内置 iPhone 8 等30+设备），自动处理 SPA 内部滚动容器分块截图+拼接
- **三种对齐策略**自动选择：同尺寸 / 同宽不同高 / 不同宽高
- **ORB 仿射校准**（不同宽高时）：保留 A 的局部特征，像素级 SSIM 不会因 resize 引入伪差异
- **顶部对齐 + 蓝线**（同宽不同高时）：蓝线在多出部分的边界，标注"仅A有(下)"/"仅B有(下)"
- **细红框标记内容差异**：1px 细红框 + 小角标编号
- **批量并行**：自动配对（文件名优先，感知哈希兜底）+ ProcessPoolExecutor 并行
- **低 token 消耗**：只输出 1 张对比图 + JSON，默认不保存裁剪图

## 前置条件

跨机器通用，不依赖某台电脑的绝对路径：

- **Python 3.10+**（`python` / `python3` 在 PATH 中）
- 安装 Python 依赖：`pip install -r requirements.txt`（opencv-python、Pillow、numpy、scikit-image、imagehash）
- **Node.js 18+**（`node` 在 PATH 中；Web 截图需要）
- 在 skill 根目录安装 Playwright：`npm install`（会生成 `node_modules/playwright`）
- 系统已安装 **Microsoft Edge** 或 **Google Chrome**（截图优先 Edge，失败回退 Chrome）

可选环境变量（需要覆盖默认探测时再设）：


| 变量                                      | 作用                                 |
| --------------------------------------- | ---------------------------------- |
| `FRONTEND_DIFF_PYTHON`                  | Python 可执行文件路径                     |
| `FRONTEND_DIFF_NODE`                    | Node 可执行文件路径                       |
| `FRONTEND_DIFF_NODE_PATH` / `NODE_PATH` | 含 `playwright` 的 `node_modules` 目录 |


脚本目录：本仓库的 `scripts/`（与 `SKILL.md` 同级下的 `scripts/`）。

## 使用方式

以下命令假设当前目录为 skill 根目录（含 `scripts/`、`requirements.txt`、`package.json`）。

### 方式一：Web 截图 → 比对 → 报告（一键，推荐）

```bash
python scripts/web_to_diff.py \
  --proto-dir "/path/to/prototypes" \
  --work-dir "./output/web_diff"
```

完整参数：

```bash
python scripts/web_to_diff.py \
  --base-url "https://your-site.com" \
  --routes '[{"name":"首页","route":"/#/home"},{"name":"设置","route":"/#/settings"}]' \
  --device "iPhone 8" \
  --proto-dir "/path/to/prototypes" \
  --work-dir "./output/web_diff" \
  --sensitivity medium
```


| 参数              | 说明                                                  | 默认值                                                      |
| --------------- | --------------------------------------------------- | -------------------------------------------------------- |
| `--base-url`    | 页面基地址                                               | `https://fat.bitechdevelop.com/pdkjwpolicy-operation-h5` |
| `--routes`      | JSON 路由列表 `[{"name":"首页","route":"/#/zwhome"},...]` | 5个内置路由（首页/政策/企业/产业/我的）                                   |
| `--device`      | Playwright 设备名                                      | `iPhone 8`                                               |
| `--proto-dir`   | 本地原型图目录                                             | **必填**                                                   |
| `--work-dir`    | 工作目录（存放截图+结果）                                       | **必填**                                                   |
| `--sensitivity` | 灵敏度: low/medium/high                                | medium                                                   |
| `--step`        | 滚动步长 CSS px                                         | 500                                                      |
| `--workers`     | 并行进程数                                               | 4                                                        |


### 方式二：单对图片比对

```bash
python scripts/image_diff.py \
  --a "图片A路径" --b "图片B路径" \
  --output "输出目录" --sensitivity medium
```

### 方式三：批量比对（两个目录）

```bash
python scripts/batch_diff.py \
  --dir-a "目录A" --dir-b "目录B" \
  --output "输出目录" --sensitivity medium --workers 4
```

### 方式四：单独 Web 截图（不要比对）

```bash
# Step 1: 截图（需已在 skill 根目录 npm install）
node scripts/web_capture.js \
  --base-url "https://your-site.com" \
  --device "iPhone 8" \
  --output "./output/my_screenshots"

# Step 2: 拼接
python scripts/web_stitch.py \
  --chunks-dir "./output/my_screenshots" \
  --output "./output/my_screenshots"
```

### 完整工作流（含AI语义描述）

**第1步：批量比对** — 运行 batch_diff.py 或 web_to_diff.py，生成 batch_results.json + 对比图

**第2步：AI语义描述** — 读取 batch_results.json，对每对有差异的图片：

1. 用 Read 工具查看 comparison_*.png 对比图（一张图即可看到所有差异）
2. 对每个 region 用一句话描述差异
3. 对每个 extra_a/extra_b 区域描述多出的内容
4. 将描述保存为 descriptions.json

**第3步：生成报告** — 运行 report_gen.py：

```bash
python scripts/report_gen.py \
  --results "输出目录/batch_results.json" \
  --output "输出目录/report.md" \
  --descriptions "输出目录/descriptions.json" \
  --dir-a "目录A名" --dir-b "目录B名" --sensitivity medium
```

## 输出文件


| 文件                         | 说明                                       |
| -------------------------- | ---------------------------------------- |
| `batch_results.json`       | 所有比对结果的JSON数据                            |
| `comparison_*.png`         | 每对图片的 side-by-side 对比图（细红框=内容差异，蓝线=多出内容） |
| `report.md`                | 最终MD报告（第3步产出）                            |
| `web_screenshots/*.png`    | Web 截图拼接后的完整长图（方式一时产出）                   |
| `web_screenshots/_chunks/` | 分块截图临时文件（方式一时产出）                         |


## 对比图标注说明

- **细红框 (1px)**：重叠区内的内容差异（字体、颜色、布局等变化）
- **蓝线 (2px)**：非重叠区边界，标注"仅A有(上/下/左/右)"或"仅B有(上/下/左/右)"
- **左右并排**：图A在左，图B在右，中间灰色分隔线

## Web 截图技术原理

1. **设备模拟**：使用 Playwright 内置 `devices` 描述符（如 `iPhone 8`：375×667 CSS, DPR 2 → 750×1334 物理像素），确保截图宽度与原型图（750px）一致
2. **设备选择**：自动根据原型图宽度匹配设备。750px 宽 → iPhone 8；1125px 宽 → iPhone X/11 Pro
3. **SPA 内部滚动处理**：通过 `page.evaluate` 找到 `overflow-y:auto/scroll` 且 `scrollHeight > clientHeight` 的元素，直接操作其 `scrollTop`
4. **懒加载触发**：先滚动到底部等待高度稳定（连续2次不变），再滚回顶部开始截图
5. **固定层处理（防底栏重复）**：分块截图前检测并隐藏 `position: fixed|sticky` 以及常见底栏选择器（`.van-tabbar` / `[class*="tabbar"]` 等），使用 `visibility:hidden` 保持布局；**最后一帧**再恢复底栏后截图，使长图底部只保留一次 Tab（接近手机长截图）
6. **分块截图**：按固定步长（默认500 CSS px）滚动，每步截取一个 viewport 截图
7. **精确拼接 + 防残影**：记录每块实际 `scrollTop` 计算 overlap；**固定层隐藏成功时不再裁底**（裁底会破坏 overlap、产生半行残影）；仅在未检出固定层时对非末块裁底兜底；下一帧顶部额外丢弃约 8 物理像素（SEAM_PAD）消化取整误差

## 技术原理（比对引擎）

1. **三种对齐策略**（utils/align.py）：
  - 同尺寸 → 直接比对（method=none）
  - 同宽不同高 → 顶部对齐 + 蓝线（method=top_aligned）
  - 不同宽高 → ORB 仿射 warp A 到 B 的尺寸（method=orb_warp）
2. **差异检测**（scripts/image_diff.py）：
  - 高斯模糊预处理（sigma=1.0）：抑制抗锯齿/字体渲染/色域差异等高频噪声
  - SSIM 在公共区运行（win_size=11，高斯加权窗口）：相比原 win_size=7 对局部像素噪声更鲁棒
3. **多层噪声过滤**（scripts/utils/noise_filter.py）：
  - **固定阈值**（替代 Otsu）：Otsu 在相似图片上会取极低阈值导致误标
  - **最小面积过滤**：medium 灵敏度下 0.1% 图像面积以下直接丢弃
  - **最小尺寸过滤**：过滤细长条等伪影
  - **均值差异强度校验**：区域平均差异强度过低则丢弃，消除边界伪影
  - **邻近合并**：把相距较近的真实差异合并为一个区域
4. **逆 warp 映射**（ORB case）：差异框在 B 坐标系下检测，用逆仿射变换把框的 4 个角点 warp 回 A 的原图坐标系
5. **自动配对**：优先文件名匹配，回退感知哈希(pHash)相似度匹配（distance ≤ 20）
6. **并行处理**：ProcessPoolExecutor 多进程并行

## 注意事项

- 图片格式支持: PNG, JPG, JPEG, BMP, TIFF, WebP
- Web 截图会自动选择与原型图宽度匹配的设备。750px 宽 → iPhone 8；如原型图其他宽度，需手动指定 `--device`
- Web 截图优先使用系统 Edge，失败则回退 Chrome（无需单独下载 Playwright Chromium）
- 同宽不同高时才会有蓝线；不同宽高时（ORB warp）所有内容都 warp 到同一坐标系，无蓝线
- 缩放比例差异越大，ORB 校准耗时越长（通常<2秒）
- **灵敏度建议先用 medium**：这是原型图 vs 实现图对比的推荐默认值，已针对字体/抗锯齿/色域差异做了抑制
- 批量比对时，未配对的图片会在报告和JSON中列出
- AI语义描述需要手动执行第2步，不自动调用
- Web 截图工作流依赖 Playwright：请在 skill 根目录执行 `npm install`

