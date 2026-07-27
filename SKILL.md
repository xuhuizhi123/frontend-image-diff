---
name: frontend-image-diff
title: "前端图片找不同"
description: "Playwright截图 + SSIM定位 + Agent拆解色/字号/间距；交付物仅 comparison_*.png 与 report.md。"
summary: "两阶段视觉比对：SSIM 定位，Agent 复核；最终只保留对比图与精简报告。"
agent_created: true
read_when:
  - 用户提到"图片比对"、"图片对比"、"找不同"、"截图对比"、"视觉差异"、"UI回归"、"页面对比"
  - 用户提供两张图片或两个目录要求对比差异
  - 用户需要从前端页面截图并与原型对比
  - 用户提到"Agent复核"、"差异拆解"、"设计还原验收"
---

# 前端图片找不同 Skill

原型图 vs 实现图视觉比对。SSIM 第一遍定位，Agent 第二遍拆解（色 / 字号 / **间距** / **静态文案**）。

**最终交付物仅两种**：`comparison_*.png`、`report.md`（`batch_results` 内嵌于 report 注释，目录不留其它临时文件）。

## 前置

- Python 3.10+：`pip install -r requirements.txt`
- Node 18+：在 skill 根目录 `npm install`（playwright）
- 系统已装 Edge 或 Chrome

可选环境变量：`FRONTEND_DIFF_PYTHON`、`FRONTEND_DIFF_NODE`、`FRONTEND_DIFF_NODE_PATH`

## 用法（skill 根目录）

### 输入源与尺寸校验（强制）

- 优先使用用户提供的**本地路径 / 项目内原图文件**；聊天贴图可能被平台压缩，未核尺寸前不可直接当原图。
- 开跑前必须核对 A/B 尺寸（如 `WxH`）是否与预期一致；若明显偏小（相对用户声明或常见桌面稿），应先停并改用路径原图后再跑。

### Web 一键

```bash
python scripts/web_to_diff.py \
  --base-url "https://your-site.com" \
  --routes '[{"name":"政策","route":"/#/zwpolicy"}]' \
  --device "iPhone 8" \
  --proto-dir "/path/to/prototypes" \
  --work-dir "./output/web_diff"
```

默认 quiet；排查加 `--verbose`。结束后 `work-dir/compare_output/` 只有对比图 + 报告。

常用参数：`--viewport-width` / `--dpr`、`--sensitivity`、`--no-deliver`（保留临时文件）

### 本地两目录

```bash
python scripts/batch_diff.py --dir-a A --dir-b B --output ./out --quiet
python scripts/report_gen.py --results ./out/batch_results.json --output ./out/report.md --deliver
```

### 两阶段工作流

1. **SSIM**：`web_to_diff` / `batch_diff` → `comparison_*.png` + 精简 `report.md`（含线索 + 内嵌 results）
2. **Agent Review**：读 comparison + report；大框时再读 `slices_*` / crops / 原图 A/B → 写临时 `agent_review.json`
3. **写回报告**（会校验大框复核完整性；不通过则拒绝默认 deliver）：

```bash
python scripts/report_gen.py \
  --report "./output/compare_output/report.md" \
  --agent-review "./output/compare_output/agent_review.json"
```

（带 `--agent-review` 时默认 deliver，只留两种文件；校验失败需补全后重跑，或显式 `--force-deliver`）

### Agent 强制检查清单

- 中文标题字号/字重；英文副标题颜色
- **间距/留白**（必须评判，不可默认 ignore）
- **大框强制逐模块复核**（见下节）：不可只用一条「整体位移」解释后结束
- 同类 low spacing 合并为一条
- **SSIM 框 ≠ 改动**：第二遍职责是降噪；同类多行小框应合并；无感知差异必须用 `noise_or_fp` 并写 `ignore_scope`
- **表格多小框按列复核**：当表格区域红框较多（如 ≥5）或同行多框时，至少按列核对名称/链接色、Tag（数据来源/当前状态）、操作入口，禁止整表批量归为「渲染噪声」或整表批量归为「Badge 色差」
- **颜色可行动阈值**：报 `color_only` 前先核文字/Tag 前景色；可感知差异才 actionable。若仅 RGB 轻微波动且形态一致，归 `noise_or_fp`
- **动态数据边界**：仅动态内容本身可用 `carousel_content` + `is_actionable=false`；同区域内静态标签/按钮/模板文案仍须比对
- category：`typography` / `color_only` / `spacing` / `scroll_mismatch` / `layout_bug` / `text_or_copy` / `missing_or_extra_module` / `noise_or_fp` / `carousel_content`

schema 见 [`references/agent_review.example.json`](references/agent_review.example.json)

### 大框强制逐模块复核

当 `suspect_global_shift=true`，或任一红框 `area_ratio > 0.40`，或存在 `slices_*` 分段时：

1. 先在 `ssim_note` 说明 SSIM 为何合并成大框（错位/高度差/模块增删等）
2. **按可见模块自上而下**逐段核对（可借助 `slices_*` 纵向分段图），**不可**找到一个根因后把整片标成位移噪音
3. 每个可见模块至少检查：
   - 标题 / Tab 文案
   - 按钮与入口（更多、回到当月、前往查看等）
   - 固定模板文案（字段标签、倒计时前缀如「剩余/剩」）
   - 模块增删 / 图标网格项
   - 间距与布局
4. 在 `reviewed_modules` 列出已检查模块名（须 ≥2，且覆盖大框内可见分区）
5. findings **可多于红框数**；大框通常对应多条可行动 + 若干条带 `ignore_scope` 的忽略项
6. `noise_or_fp` / `carousel_content` 必须写清 `ignore_scope`（忽略范围）与理由；**禁止**把整片混合区域直接 ignore

即使未触发 `area_ratio > 0.40`，若出现密集小框（尤其表格区），也必须执行上面的按列复核规则，避免漏报真实样式差异。

#### 动态 vs 静态（硬性边界）

| 可忽略（carousel_content / 运营数据） | 仍须比对（text_or_copy / missing_or_extra_module 等） |
|--------------------------------------|------------------------------------------------------|
| 文章/政策标题正文、列表条目内容 | 分区标题、Tab 名（如「政策解读」下的固定入口文案） |
| 日期、条数、「168条」等数量 | 「回到当月」「更多」「前往查看」等按钮/入口 |
| 倒计时数字本身（15 / 41） | 倒计时模板文案（「剩余X天」vs「剩X天」） |
| 轮播/Banner 运营图内容 | 图标分类名、静态标签文案（数智低碳 vs 数字低碳） |
| 表格单元格业务值（编号、名称内容、日期值等） | 表格静态样式（字色/链接色/Badge 样式） |

### 用户回复模板（精简）

```text
{页名} · SSIM {xx%} · 可行动 {n}
- [high/medium] …
- [low] …（可合并）
产物: comparison_*.png · report.md
```

## 输出说明

| 文件 | 说明 |
|------|------|
| `comparison_*.png` | 左右对比图（红框=差异，蓝线=仅一侧有） |
| `report.md` | 精简报告；末尾 HTML 注释内嵌 batch_results |
| `slices_*`（临时） | 大框纵向分段；供 Agent 复核，deliver 时删除 |
| `crops_*`（临时） | `--save-crops` 时的区域裁剪；deliver 时删除 |

`--full` 可出完整报告；`--save-crops` 可选裁剪（交付前会删）。配对时忽略 `_` 开头文件名。

## 原理摘要

- 对齐：同尺寸 / 同宽顶对齐 / ORB warp
- SSIM + 噪声过滤；`suspect_global_shift`（单框面积>40%）提示大框合并
- 大框自动产出纵向 `slice_paths`，降低 Agent 漏看中段模块的概率
- `report_gen --agent-review` 会校验 `reviewed_modules` / 大框 findings 覆盖；不完整则拒绝默认 deliver
- 详细原理见历史文档段落；日常以交付物与 Agent 协议为准
