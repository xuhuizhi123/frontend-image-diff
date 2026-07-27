# 前端图片找不同

原型图与实现图的视觉比对工具，面向 **UI 还原验收** 与 **页面回归** 场景。

采用两阶段流程：**SSIM 自动定位差异区域**，再由 **Agent 拆解** 色值、字号、间距与静态文案，输出可行动的验收结论。

## 特性

- **Web 一键**：Playwright 截图 + 自动配对原型图，一条命令完成比对
- **本地批量**：支持两目录 / 两图批量对比，按文件名自动配对
- **智能对齐**：同尺寸、同宽顶对齐、ORB 透视校正
- **降噪过滤**：SSIM + 多层噪声过滤，减少字体抗锯齿误报
- **Agent 复核协议**：大框逐模块拆解、表格按列采色、动态数据边界清晰

最终交付物仅两种：`comparison_*.png`（左右对比图）与 `report.md`（精简报告）。

## 环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+（Web 截图需要） |
| 浏览器 | Edge 或 Chrome |

```bash
pip install -r requirements.txt
npm install
npx playwright install chromium   # 首次使用 Web 截图时
```

可选环境变量：`FRONTEND_DIFF_PYTHON`、`FRONTEND_DIFF_NODE`、`FRONTEND_DIFF_NODE_PATH`

## 快速开始

### 本地两图对比

```bash
python scripts/image_diff.py --a prototype.png --b screenshot.png --output ./out
```

### 本地两目录批量对比

```bash
python scripts/batch_diff.py --dir-a ./prototypes --dir-b ./screenshots --output ./out --quiet
python scripts/report_gen.py --results ./out/batch_results.json --output ./out/report.md --deliver
```

### Web 页面 + 原型一键对比

```bash
python scripts/web_to_diff.py \
  --base-url "https://your-site.com" \
  --routes '[{"name":"政策","route":"/#/zwpolicy"}]' \
  --device "iPhone 8" \
  --proto-dir "./prototypes" \
  --work-dir "./output/web_diff"
```

结束后在 `work-dir/compare_output/` 得到对比图与报告。

更多示例见 [`references/examples.md`](references/examples.md)。

## 两阶段工作流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  SSIM 定位   │ ──▶ │ Agent 复核    │ ──▶ │  写回报告    │
│  红框 + 分数  │     │ 拆解真实差异   │     │  最终交付    │
└─────────────┘     └──────────────┘     └─────────────┘
```

1. **SSIM 定位**：`batch_diff` / `web_to_diff` 产出 `comparison_*.png` 与含线索的 `report.md`
2. **Agent 复核**：对照对比图与原图，按协议写出 `agent_review.json`（色 / 字号 / 间距 / 文案）
3. **写回报告**：

```bash
python scripts/report_gen.py \
  --report "./output/compare_output/report.md" \
  --agent-review "./output/compare_output/agent_review.json"
```

Agent 复核 schema 与示例见 [`references/agent_review.example.json`](references/agent_review.example.json)。完整协议见 [`SKILL.md`](SKILL.md)。

## 输出说明

| 文件 | 说明 |
|------|------|
| `comparison_*.png` | 左右对比图；红框 = 差异区域，蓝线 = 仅一侧存在的内容 |
| `report.md` | 精简报告，含 SSIM 分数、红框线索、可行动差异列表 |

调试时可加 `--verbose` 查看详细日志，`--no-deliver` 保留中间文件（`batch_results.json`、`slices_*` 等）。

## 在 Cursor 中使用

将本仓库作为 **Agent Skill** 使用：把 `SKILL.md` 放入 Cursor Skills 目录，或在对话中 @ 引用。

触发场景：图片比对、找不同、截图对比、视觉差异、UI 回归、设计还原验收。

**重要**：比对时请使用**本地原图路径**，不要使用聊天贴图（平台可能压缩分辨率，影响 SSIM 精度）。

## 项目结构

```
frontend-image-diff/
├── SKILL.md                 # Agent Skill 协议（复核规则与检查清单）
├── scripts/
│   ├── image_diff.py        # 单图对比
│   ├── batch_diff.py        # 批量对比
│   ├── web_to_diff.py       # Web 截图 + 对比一键流程
│   ├── web_capture.js       # Playwright 截图脚本
│   ├── report_gen.py        # 报告生成与 Agent 写回
│   └── utils/               # 对齐、降噪、配对等工具
├── references/
│   ├── examples.md          # 使用示例
│   └── agent_review.example.json
├── requirements.txt
└── package.json
```

## License

MIT
