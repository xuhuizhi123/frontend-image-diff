#!/usr/bin/env node
/**
 * Web 页面截图工具（配合 frontend-image-diff skill 使用）
 *
 * 用法（从 web_to_diff.py 调用）：
 *   node web_capture.js --base-url <url> --routes <json> --device <name> --output <dir> [--step <px>]
 *
 * 参数：
 *   --base-url   页面基地址
 *   --routes     JSON 数组 [{"name":"首页","route":"/#/zwhome"},...]
 *   --device     Playwright 内置设备名，如 "iPhone 8"、"iPhone 13"
 *   --output     输出目录
 *   --step       滚动步长 CSS px（默认 500）
 *
 * 未传参时使用内置默认值（默认 URL + 5 个路由）。
 */

const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

// ===== 参数解析 =====
function parseArgs() {
    const args = process.argv.slice(2);
    const opts = {
        baseUrl: 'https://fat.bitechdevelop.com/pdkjwpolicy-operation-h5',
        routes: null,
        device: 'iPhone 8',
        output: null,
        step: 500,
    };

    for (let i = 0; i < args.length; i++) {
        switch (args[i]) {
            case '--base-url': opts.baseUrl = args[++i]; break;
            case '--routes': opts.routes = JSON.parse(args[++i]); break;
            case '--device': opts.device = args[++i]; break;
            case '--output': opts.output = args[++i]; break;
            case '--step': opts.step = parseInt(args[++i]); break;
        }
    }

    if (!opts.routes) {
        opts.routes = [
            { name: '首页', route: '/#/zwhome' },
            { name: '政策', route: '/#/zwpolicy' },
            { name: '企业', route: '/#/zwenterprise' },
            { name: '产业', route: '/#/zwindustry' },
            { name: '我的', route: '/#/zwmy' },
        ];
    }

    return opts;
}

// ===== 滚动容器操作 =====
async function findScrollable(page) {
    return page.evaluate(() => {
        const candidates = [
            document.documentElement,
            document.body,
            ...Array.from(document.querySelectorAll('*')).filter((el) => {
                const style = window.getComputedStyle(el);
                return (style.overflowY === 'auto' || style.overflowY === 'scroll')
                    && el.scrollHeight > el.clientHeight;
            }),
        ];
        const el = candidates.reduce((max, el) =>
            (el.scrollHeight > max.scrollHeight ? el : max), candidates[0]);
        return {
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight,
        };
    });
}

async function scrollContainerTo(page, y) {
    return page.evaluate((targetY) => {
        const candidates = [
            document.documentElement,
            document.body,
            ...Array.from(document.querySelectorAll('*')).filter((el) => {
                const style = window.getComputedStyle(el);
                return (style.overflowY === 'auto' || style.overflowY === 'scroll')
                    && el.scrollHeight > el.clientHeight;
            }),
        ];
        const el = candidates.reduce((max, el) =>
            (el.scrollHeight > max.scrollHeight ? el : max), candidates[0]);
        el.scrollTop = targetY;
        return el.scrollTop; // 返回实际滚动位置（浏览器可能截断）
    }, y);
}

async function loadAllLazyContent(page) {
    let lastHeight = 0;
    let stableCount = 0;
    for (let i = 0; i < 40; i++) {
        const info = await page.evaluate(() => {
            const candidates = [
                document.documentElement,
                document.body,
                ...Array.from(document.querySelectorAll('*')).filter((el) => {
                    const style = window.getComputedStyle(el);
                    return (style.overflowY === 'auto' || style.overflowY === 'scroll')
                        && el.scrollHeight > el.clientHeight;
                }),
            ];
            const el = candidates.reduce((max, el) =>
                (el.scrollHeight > max.scrollHeight ? el : max), candidates[0]);
            el.scrollTop = el.scrollHeight;
            return { scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
        });
        await page.waitForTimeout(500);
        if (info.scrollHeight === lastHeight) {
            stableCount++;
            if (stableCount >= 2) break;
        } else {
            stableCount = 0;
            lastHeight = info.scrollHeight;
        }
    }
    await scrollContainerTo(page, 0);
    await page.waitForTimeout(500);
}

/**
 * Mark fixed/sticky elements (and common mobile tabbar selectors) for hide-during-stitch.
 * Returns estimated bottom fixed bar height in CSS px.
 */
async function markFixedSticky(page) {
    return page.evaluate(() => {
        document.querySelectorAll('[data-pw-fixed-hide]').forEach((el) => {
            el.removeAttribute('data-pw-fixed-hide');
            el.removeAttribute('data-pw-fixed-display');
        });

        const vh = window.innerHeight;
        let fixedBottomCssPx = 0;
        let count = 0;
        const marked = new Set();

        const mark = (el) => {
            if (!el || marked.has(el)) return;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            if (rect.width < 2 || rect.height < 2) return;
            marked.add(el);
            el.setAttribute('data-pw-fixed-hide', '1');
            el.setAttribute('data-pw-fixed-display', style.display || '');
            count += 1;
            if (rect.bottom >= vh - 8 && rect.height >= 30 && rect.height <= 140) {
                fixedBottomCssPx = Math.max(fixedBottomCssPx, Math.ceil(rect.height));
            }
        };

        // 1) computed position fixed/sticky
        for (const el of document.querySelectorAll('body *')) {
            const pos = window.getComputedStyle(el).position;
            if (pos === 'fixed' || pos === 'sticky') mark(el);
        }

        // 2) common mobile tabbar class patterns (even if position is absolute in a shell)
        const tabSelectors = [
            '.van-tabbar',
            '.am-tab-bar',
            '.tab-bar',
            '.tabbar',
            '.bottom-tab',
            '.bottom-nav',
            '[class*="tabbar"]',
            '[class*="tab-bar"]',
            '[class*="TabBar"]',
        ];
        for (const sel of tabSelectors) {
            try {
                document.querySelectorAll(sel).forEach(mark);
            } catch (_) { /* ignore invalid */ }
        }

        // 3) heuristic: full-width bottom docked bars
        const vw = window.innerWidth;
        for (const el of document.querySelectorAll('body *')) {
            if (marked.has(el)) continue;
            const rect = el.getBoundingClientRect();
            if (rect.height < 40 || rect.height > 100) continue;
            if (rect.width < vw * 0.85) continue;
            if (Math.abs(rect.bottom - vh) > 4) continue;
            if (rect.left > 8) continue;
            mark(el);
        }

        if (fixedBottomCssPx <= 0) fixedBottomCssPx = 50;
        return { count, fixedBottomCssPx };
    });
}

async function setFixedHidden(page, hidden) {
    await page.evaluate((hide) => {
        document.querySelectorAll('[data-pw-fixed-hide="1"]').forEach((el) => {
            if (hide) {
                // Keep layout so bottom strip can be cropped safely when stitching.
                el.style.setProperty('visibility', 'hidden', 'important');
                el.style.setProperty('pointer-events', 'none', 'important');
                el.style.setProperty('opacity', '0', 'important');
            } else {
                el.style.removeProperty('visibility');
                el.style.removeProperty('pointer-events');
                el.style.removeProperty('opacity');
            }
        });
    }, hidden);
}

function buildScrollPositions(maxY, step) {
    const positions = [];
    let y = 0;
    if (maxY <= 0) return [0];
    while (true) {
        positions.push(y);
        if (y >= maxY) break;
        const next = Math.min(y + step, maxY);
        if (next === y) break;
        y = next;
    }
    return positions;
}

// ===== 主流程 =====
async function capturePage(page, baseUrl, routeInfo, outputDir, step) {
    const url = `${baseUrl}${routeInfo.route}`;
    console.log(`\n[${routeInfo.name}] ${url}`);

    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForLoadState('load', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2500);

    // 触发懒加载
    await loadAllLazyContent(page);

    const info = await findScrollable(page);
    console.log(`  scrollable: height=${info.scrollHeight}, client=${info.clientHeight}`);

    // 创建分块目录
    const chunksDir = path.join(outputDir, '_chunks', routeInfo.name);
    if (!fs.existsSync(chunksDir)) fs.mkdirSync(chunksDir, { recursive: true });
    fs.readdirSync(chunksDir).forEach((f) => fs.unlinkSync(path.join(chunksDir, f)));

    // 检测并隐藏 fixed/sticky，避免中间帧重复底栏
    const fixedInfo = await markFixedSticky(page);
    console.log(
        `  fixed/sticky: ${fixedInfo.count}, bottomBar≈${fixedInfo.fixedBottomCssPx}px`,
    );
    await setFixedHidden(page, true);
    await page.waitForTimeout(200);

    const maxY = Math.max(0, info.scrollHeight - info.clientHeight);
    const positions = buildScrollPositions(maxY, step);
    const chunkMeta = [];

    for (let idx = 0; idx < positions.length; idx++) {
        const currentY = positions[idx];
        const isLast = idx === positions.length - 1;

        if (isLast) {
            await setFixedHidden(page, false);
            await page.waitForTimeout(200);
        }

        const actualY = await scrollContainerTo(page, currentY);
        await page.waitForTimeout(800);
        const buffer = await page.screenshot({ fullPage: false });
        const chunkFile = `chunk_${String(idx).padStart(3, '0')}.png`;
        fs.writeFileSync(path.join(chunksDir, chunkFile), buffer);

        chunkMeta.push({
            index: idx,
            file: chunkFile,
            targetScroll: currentY,
            actualScroll: actualY,
            isLast,
        });

        console.log(
            `  chunk ${idx}: target=${currentY}, actual=${actualY}` +
                (isLast ? ' (tabbar restored)' : ''),
        );
    }

    console.log(`  captured ${chunkMeta.length} chunks`);
    return {
        chunks: chunkMeta,
        fixedBottomCssPx: fixedInfo.fixedBottomCssPx,
        fixedHiddenCount: fixedInfo.count,
    };
}

(async () => {
    const opts = parseArgs();

    if (!fs.existsSync(opts.output)) {
        fs.mkdirSync(opts.output, { recursive: true });
    }

    // 选择设备
    const deviceDesc = devices[opts.device];
    if (!deviceDesc) {
        console.error(`Unknown device: ${opts.device}`);
        console.error(`Available: ${Object.keys(devices).slice(0, 20).join(', ')}...`);
        process.exit(1);
    }

    const physW = deviceDesc.viewport.width * deviceDesc.deviceScaleFactor;
    const physH = deviceDesc.viewport.height * deviceDesc.deviceScaleFactor;
    console.log(`Device: ${opts.device}`);
    console.log(`  viewport: ${deviceDesc.viewport.width}x${deviceDesc.viewport.height} CSS, DPR=${deviceDesc.deviceScaleFactor}`);
    console.log(`  physical: ${physW}x${physH} px`);

    let browser;
    try {
        browser = await chromium.launch({ headless: true, channel: 'msedge' });
    } catch (e) {
        console.warn('msedge launch failed, fallback to chrome:', e.message);
        browser = await chromium.launch({ headless: true, channel: 'chrome' });
    }
    const context = await browser.newContext({
        ...deviceDesc,
        locale: 'zh-CN',
        timezoneId: 'Asia/Shanghai',
    });

    const page = await context.newPage();
    const allMetadata = {};

    for (const routeInfo of opts.routes) {
        try {
            const result = await capturePage(page, opts.baseUrl, routeInfo, opts.output, opts.step);
            const info = await findScrollable(page);
            allMetadata[routeInfo.name] = {
                scrollHeight: info.scrollHeight,
                clientHeight: info.clientHeight,
                fixedBottomCssPx: result.fixedBottomCssPx,
                fixedHiddenCount: result.fixedHiddenCount,
                chunks: result.chunks,
            };
        } catch (e) {
            console.error(`[${routeInfo.name}] Error:`, e.message);
        }
    }

    // 保存滚动元数据供拼接脚本使用
    const metaPath = path.join(opts.output, '_chunks', 'scroll_metadata.json');
    fs.writeFileSync(metaPath, JSON.stringify(allMetadata, null, 2));
    console.log(`\nMetadata saved to ${metaPath}`);

    await browser.close();
    console.log('Done.');
})();
