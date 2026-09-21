/**
 * 生成「浏览器里可交互的小程序演示页」。
 *
 * 为什么要做这个：微信小程序的 .wxml / .wxss 只能由微信开发者工具或真机渲染，
 * 在没装开发者工具的环境里，作品就是「看不见的」。这个脚本把真实的小程序页面
 * （模板 + 样式 + 页面逻辑）原样搬到浏览器里跑，数据仍然打真实后端接口，
 * 于是答辩前可以先在浏览器里把整条流程点一遍，确认界面与交互没问题。
 *
 * 关键点：**不重写界面**。WXML 由本脚本转成 HTML，WXSS 由本脚本转成 CSS，
 * 页面 JS 也直接加载 frontend/pages/**\/index.js（由内置的迷你运行时提供
 * Page / Component / setData / wx.* 等接口）。因此演示页里看到的就是小程序的样子。
 *
 * 用法（在仓库根目录，先启动后端）：
 *     node tools/make_demo.js
 * 产物：demo/index.html（单文件，双击即可打开）
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FRONTEND = path.join(ROOT, 'frontend');
const OUT_DIR = path.join(ROOT, 'demo');
const OUT_FILE = path.join(OUT_DIR, 'index.html');

// ============================================================
// 一、WXSS → CSS
// ============================================================
/**
 * rpx → px 的换算。
 *
 * 小程序里 750rpx 等于屏幕宽度。演示机身固定 375px 宽，因此 1rpx = 0.5px，
 * 直接换算成固定 px 最稳妥。
 *
 * 为什么不用 rem：rem 永远相对**根元素**字号解析，改「手机壳」的字号没用
 * （这一点踩过坑：同一个 0.28rem 在卡片内外量出来都是 3.92px，
 *  即 0.28 × html 的 14px，而不是父元素的 50px）。
 */
function rpxToPx(css) {
  return css.replace(/(-?\d*\.?\d+)rpx\b/g, (m, n) => {
    const px = parseFloat(n) / 2;
    return (Math.round(px * 1000) / 1000) + 'px';
  });
}

/** 把 app.wxss 里的 `page { ... }`（设计令牌所在处）绑到演示外壳上。
 *
 * 关键：小程序的 `page` 是页面根节点，自定义属性必须挂在真实存在的元素上才生效。
 * 这条规则若没落地，所有 var(--c-*) / var(--r-card) 都会失效，界面会整体塌掉
 * （症状是字号、间距全变成默认值）。 */
function scopePageSelector(css) {
  // 注意：app.wxss 的 `page {` 前面通常紧跟着块注释结尾 `*/`，
  // 因此边界字符必须包含 `/`，并且在替换时把它还回去。
  // 否则会生成 `*` + 选择器 这种畸形 CSS，整段设计令牌被浏览器丢弃
  // （症状：颜色、圆角、阴影全部失效）。这个坑踩过一次，务必保留 `/`。
  return css.replace(/(^|[\}\/])\s*page\s*\{/g, (m, pre) => {
    const head = (pre === '}' || pre === '/') ? pre + '\n' : '';
    return head + '.phone, .page-root, #mp-view {';
  }).replace(/^(\s*)page\s*\{/m, '$1.phone, .page-root, #mp-view {');
}

/** 把一段 WXSS 的每条顶层规则都加上作用域前缀（支持 @media 等嵌套块）。 */
function scopeRules(css, scope) {
  // 先去掉注释：否则「注释里提到 {」会让选择器切分错位，
  // 生成出 `.mp-page[...] /* 说明 */` 这种畸形选择器，样式整段失效。
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out = [];
  let i = 0;
  while (i < clean.length) {
    const open = clean.indexOf('{', i);
    if (open === -1) break;
    let depth = 1;
    let j = open + 1;
    while (j < clean.length && depth > 0) {
      if (clean.charAt(j) === '{') depth++;
      else if (clean.charAt(j) === '}') depth--;
      j++;
    }
    const selector = clean.slice(i, open).trim();
    const body = clean.slice(open, j);
    if (!selector) { i = j; continue; }
    if (selector.charAt(0) === '@') {
      out.push(clean.slice(i, j));      // @media / @keyframes 整体保留
    } else {
      const prefixed = selector.split(',').map((s) => {
        const t = s.trim();
        if (!t) return '';
        if (t.indexOf('page') === 0) return scope + ' ' + t.replace(/^page/, '');
        return scope + ' ' + t;
      }).filter(Boolean).join(', ');
      out.push(prefixed + ' ' + body);
    }
    i = j;
  }
  return out.join('\n');
}

function buildCss() {
  const app = fs.readFileSync(path.join(FRONTEND, 'app.wxss'), 'utf8');
  const mascot = fs.readFileSync(path.join(FRONTEND, 'components', 'mascot', 'mascot.wxss'), 'utf8');

  // 各页面 WXSS 里的类名会重名（例如 .card / .h1），直接拼在一起会互相覆盖，
  // 症状是「文字莫名其妙变小」。因此把每个页面的样式限定在该页容器内。
  // 注意：rpx → rem 的转换必须在「作用域前缀」之前做，否则页面样式里的 rpx 不会被转换。
  const scoped = ['index', 'quiz', 'report', 'wrong', 'knowledge', 'profile'].map((name) => {
    const css = rpxToPx(fs.readFileSync(path.join(FRONTEND, 'pages', name, 'index.wxss'), 'utf8'));
    return '/* ---- pages/' + name + ' ---- */\n' + scopeRules(css, '.mp-page[data-page="pages/' + name + '"]');
  }).join('\n\n');

  return [
    '/* ==== 来自 app.wxss（全局视觉基调） ==== */',
    scopePageSelector(rpxToPx(app)),
    '/* ==== 来自 components/mascot/mascot.wxss ==== */',
    rpxToPx(mascot),
    '/* ==== 来自各页面 index.wxss（按页限定作用域） ==== */',
    scoped,
    // WXSS 的 hover-class 在浏览器里用 :active 近似
    '.hover-soft:active, .hover-soft:hover { opacity: .78; }',
    '.btn-primary.disabled, .btn-primary[disabled] { background: #C9E6F5; }'
  ].join('\n\n');
}

// ============================================================
// 二、WXML → 模板（运行时渲染）
// ============================================================
/**
 * 解析 {{ }} 中的表达式。
 * 策略：把裸标识符加上作用域前缀，再交给一个受控的 Function 求值。
 * 这是演示工具，输入完全来自本仓库自己的 WXML，不存在外部注入面。
 */
const JS_KEYWORDS = new Set([
  'true', 'false', 'null', 'undefined', 'typeof', 'in', 'of', 'new',
  'Math', 'Date', 'JSON', 'String', 'Number', 'Boolean', 'Array', 'Object'
]);

function compileExpr(expr) {
  const transformed = expr.replace(/(\.\s*)?\b([A-Za-z_$][A-Za-z0-9_$]*)\b/g,
    (m, dot, name) => {
      if (dot) return m;                       // 属性访问，不动
      if (JS_KEYWORDS.has(name)) return name;  // 关键字与内置对象，不动
      return 'scope["' + name + '"]';
    });
  // eslint-disable-next-line no-new-func
  return new Function('scope', 'try { return (' + transformed + '); } catch (e) { return undefined; }');
}

const exprCache = new Map();
function evalExpr(expr, scope) {
  if (!exprCache.has(expr)) exprCache.set(expr, compileExpr(expr));
  return exprCache.get(expr)(scope);
}

// 自闭合与普通标签的映射
const TAG_MAP = {
  view: 'div',
  text: 'span',
  image: 'img',
  block: 'div',
  'scroll-view': 'div',
  button: 'button',
  input: 'input',
  textarea: 'textarea',
  navigator: 'a',
  form: 'form',
  label: 'label',
  switch: 'input',
  picker: 'div',
  'rich-text': 'div',
  progress: 'div'
};

function attrValue(raw) {
  if (raw === undefined) return true;           // 无值属性
  const m = /^\{\{([\s\S]*)\}\}$/.exec(raw.trim());
  if (m) return { dynamic: m[1].trim() };
  const mm = /^\{\{([\s\S]*)\}\}$/.exec(raw);
  return raw.replace(/^["']|["']$/g, '');
}

function parseAttrs(attrText) {
  const attrs = [];
  const re = /([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')|([A-Za-z_:][-A-Za-z0-9_:.]*)/g;
  let m;
  while ((m = re.exec(attrText)) !== null) {
    if (m[1]) {
      attrs.push({ name: m[1], raw: m[3] !== undefined ? m[3] : m[4] });
    } else if (m[5]) {
      attrs.push({ name: m[5], raw: undefined });
    }
  }
  return attrs;
}

/** 把 WXML 文本切成节点树 */
function parseWxml(src) {
  const root = { tag: '#root', attrs: [], children: [] };
  const stack = [root];
  let i = 0;

  const pushText = (text) => {
    if (text.trim() === '') {
      // 保留纯空格文本没意义，但 {{}} 之间的换行要留一个空格，避免文字粘连
      if (/\{\{/.test(text)) stack[stack.length - 1].children.push({ tag: '#text', text: ' ' });
      return;
    }
    stack[stack.length - 1].children.push({ tag: '#text', text });
  };

  while (i < src.length) {
    const lt = src.indexOf('<', i);
    if (lt === -1) { pushText(src.slice(i)); break; }
    pushText(src.slice(i, lt));

    if (src.startsWith('<!--', lt)) {
      const end = src.indexOf('-->', lt);
      i = end === -1 ? src.length : end + 3;
      continue;
    }
    const gt = src.indexOf('>', lt);
    if (gt === -1) { pushText(src.slice(lt)); break; }
    const inner = src.slice(lt + 1, gt);
    i = gt + 1;

    if (inner.startsWith('/')) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const selfClosing = inner.endsWith('/') || /^(input|image|br)\b/.test(inner.trim());
    const body = selfClosing ? inner.replace(/\/$/, '') : inner;
    const spaceAt = body.search(/\s/);
    const tag = (spaceAt === -1 ? body : body.slice(0, spaceAt)).trim();
    const attrs = parseAttrs(spaceAt === -1 ? '' : body.slice(spaceAt));

    const node = { tag, attrs, children: [] };
    stack[stack.length - 1].children.push(node);
    if (!selfClosing) stack.push(node);
  }
  return root;
}

function esc(s) {
  return String(s === undefined || s === null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 计算节点的 wx:if / wx:for 后交给渲染器 */
function resolveDirectives(node, scope) {
  // wx:for
  const forAttr = node.attrs.find((a) => a.name === 'wx:for');
  if (forAttr) {
    const av = attrValue(forAttr.raw);
    const list = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, scope) : [];
    const itemName = (node.attrs.find((a) => a.name === 'wx:for-item') || {}).raw || 'item';
    const indexName = (node.attrs.find((a) => a.name === 'wx:for-index') || {}).raw || 'index';
    const out = [];
    (Array.isArray(list) ? list : []).forEach((item, index) => {
      const child = Object.assign({}, scope);
      child[itemName] = item;
      child[indexName] = index;
      out.push({ scope: child, item: item, index: index });
    });
    return { repeat: out };
  }
  // wx:if
  const ifAttr = node.attrs.find((a) => a.name === 'wx:if');
  if (ifAttr) {
    const av = attrValue(ifAttr.raw);
    const ok = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, scope) : !!av;
    return { visible: !!ok };
  }
  return {};
}

function renderNodes(nodes, scope) {
  let html = '';
  let lastIfResult = null;      // 用于 wx:elif / wx:else

  for (const node of nodes) {
    if (node.tag === '#text') {
      html += renderText(node.text, scope);
      continue;
    }

    const attrNames = node.attrs.map((a) => a.name);
    // wx:elif / wx:else 依赖上一个兄弟节点的条件结果
    if (attrNames.includes('wx:elif')) {
      if (lastIfResult) continue;
      const av = attrValue(node.attrs.find((a) => a.name === 'wx:elif').raw);
      const ok = typeof av === 'object' && av.dynamic ? !!evalExpr(av.dynamic, scope) : !!av;
      lastIfResult = ok;
      if (!ok) continue;
    } else if (attrNames.includes('wx:else')) {
      if (lastIfResult) continue;
      lastIfResult = true;
    } else if (attrNames.includes('wx:if') || attrNames.includes('wx:for')) {
      const dir = resolveDirectives(node, scope);
      if (dir.repeat) {
        for (const r of dir.repeat) html += renderNode(node, r.scope, r.item, r.index);
        lastIfResult = null;
        continue;
      }
      if (dir.visible === false) { lastIfResult = false; continue; }
      lastIfResult = dir.visible === undefined ? null : true;
    } else {
      lastIfResult = null;
    }

    html += renderNode(node, scope, undefined, undefined);
  }
  return html;
}

function renderText(text, scope) {
  if (!/\{\{/.test(text)) return esc(text);
  let out = '';
  let rest = text;
  while (true) {
    const start = rest.indexOf('{{');
    if (start === -1) { out += esc(rest); break; }
    out += esc(rest.slice(0, start));
    const end = rest.indexOf('}}', start);
    if (end === -1) { out += esc(rest.slice(start)); break; }
    const expr = rest.slice(start + 2, end);
    const val = evalExpr(expr, scope);
    out += esc(val === undefined || val === null ? '' : val);
    rest = rest.slice(end + 2);
  }
  return out;
}

function renderNode(node, scope, item, index) {
  const local = item === undefined ? scope : scope;
  if (item !== undefined) {
    // 循环体内 item/index 已由上层写入 scope
  }
  const dir = resolveDirectives(node, local);
  if (dir.repeat) {
    return dir.repeat.map((r) => renderNode(node, r.scope, undefined, undefined)).join('');
  }
  if (dir.visible === false) return '';

  const isComponent = ['mascot'].includes(node.tag);
  const tag = isComponent ? 'div' : (TAG_MAP[node.tag] || 'div');

  let cls = '';
  let style = '';
  let dataAttrs = '';
  let events = '';
  let attrsOut = '';
  let innerHtml = '';

  for (const a of node.attrs) {
    const { name, raw } = a;
    if (name.startsWith('wx:')) continue;
    const av = attrValue(raw);

    if (name === 'class') {
      const pieces = [];
      if (typeof av === 'object' && av.dynamic) {
        pieces.push(String(evalExpr(av.dynamic, local) || ''));
      } else {
        // class 里可能混有 {{}} 片段
        let text = raw || '';
        text = text.replace(/\{\{([\s\S]*?)\}\}/g, (m, e) => {
          const v = evalExpr(e, local);
          return v === undefined || v === null ? '' : String(v);
        });
        pieces.push(text);
      }
      cls = pieces.join(' ').replace(/\s+/g, ' ').trim();
      continue;
    }
    if (name === 'style') {
      style = raw || '';
      continue;
    }
    if (name === 'hover-class') { continue; }        // 用 CSS :active 近似
    if (name === 'data-value' || name === 'data-topic' || name === 'data-key') {
      const key = name.slice(5);
      const v = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, local) : av;
      dataAttrs += ' data-' + key + '="' + esc(v) + '"';
      continue;
    }
    if (name.startsWith('bind') || name.startsWith('catch')) {
      const evt = name.replace(/^(bind|catch)/, '');
      events += ' data-ev-' + evt + '="1"';
      continue;
    }
    if (name.startsWith('aria-') || name === 'role') {
      const v = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, local) : av;
      attrsOut += ' ' + name + '="' + esc(v) + '"';
      continue;
    }
    if (name === 'src') {
      const v = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, local) : av;
      attrsOut += ' src="' + esc(v) + '"';
      continue;
    }
    if (name === 'value') {
      const v = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, local) : av;
      attrsOut += ' value="' + esc(v === undefined ? '' : v) + '"';
      continue;
    }
    if (['placeholder', 'maxlength', 'type', 'confirm-type', 'placeholder-class',
         'mode', 'disabled', 'id'].includes(name)) {
      let v = typeof av === 'object' && av.dynamic ? evalExpr(av.dynamic, local) : (raw === undefined ? '' : raw);
      if (name === 'placeholder-class') continue;
      if (name === 'disabled') { if (v) attrsOut += ' disabled'; continue; }
      attrsOut += ' ' + name + '="' + esc(v) + '"';
      continue;
    }
  }

  if (isComponent) {
    const state = (node.attrs.find((a) => a.name === 'state') || {}).raw || 'idle';
    const size = (node.attrs.find((a) => a.name === 'size') || {}).raw || 'md';
    const capRaw = (node.attrs.find((a) => a.name === 'caption') || {}).raw;
    let caption = '';
    if (capRaw !== undefined) {
      const cav = attrValue(capRaw);
      caption = typeof cav === 'object' && cav.dynamic ? evalExpr(cav.dynamic, local) : cav;
    }
    const CAPS = {
      idle: '我是小科，陪你一起探索科学', thinking: '小科正在思考…',
      correct: '答对啦，你真棒！', wrong: '差一点点，再看看解析？',
      encourage: '别着急，慢慢来～', win: '这一关通过啦！'
    };
    const shown = caption && String(caption).length ? caption : (CAPS[state] || CAPS.idle);
    return '<div class="mascot mascot-' + esc(size) + ' mascot-' + esc(state) + '" aria-role="img" aria-label="小科：' + esc(shown) + '">'
      + '<div class="mascot-stage">'
      + (state === 'thinking'
        ? '<div class="mascot-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>' : '')
      + '<div class="mascot-body"><div class="ear ear-left"></div><div class="ear ear-right"></div>'
      + '<div class="mascot-head"><div class="mascot-face"><div class="mascot-eyes">'
      + '<div class="eye eye-left"></div><div class="eye eye-right"></div></div>'
      + '<div class="mouth"></div><div class="cheek cheek-left"></div><div class="cheek cheek-right"></div>'
      + '</div></div></div></div>'
      + '<div class="mascot-caption">' + esc(shown) + '</div></div>';
  }

  if (tag === 'input' || tag === 'img') {
    return '<' + tag + (cls ? ' class="' + cls + '"' : '') + (style ? ' style="' + esc(style) + '"' : '')
      + dataAttrs + events + attrsOut + '>';
  }

  innerHtml = renderNodes(node.children, local);
  // 空元素也要撑起来（分档小圆点那种纯装饰节点）
  return '<' + tag + (cls ? ' class="' + cls + '"' : '') + (style ? ' style="' + esc(style) + '"' : '')
    + dataAttrs + events + attrsOut + '>' + innerHtml + '</' + tag + '>';
}

// ============================================================
// 三、迷你运行时（提供 Page / Component / setData / wx.*）
// ============================================================
// ============================================================
// 四、组装 index.html
// ============================================================
function buildPageModules() {
  const pages = [
    { key: 'pages/index', dir: 'index', title: '去闯关' },
    { key: 'pages/quiz', dir: 'quiz', title: '答题闯关' },
    { key: 'pages/report', dir: 'report', title: '复盘报告' },
    { key: 'pages/wrong', dir: 'wrong', title: '错题本' },
    { key: 'pages/knowledge', dir: 'knowledge', title: '知识库' },
    { key: 'pages/profile', dir: 'profile', title: '我的' }
  ];
  return pages.map((p) => {
    const wxmlPath = path.join(FRONTEND, 'pages', p.dir, 'index.wxml');
    const jsPath = path.join(FRONTEND, 'pages', p.dir, 'index.js');
    const jsonPath = path.join(FRONTEND, 'pages', p.dir, 'index.json');
    const tree = parseWxml(fs.readFileSync(wxmlPath, 'utf8'));
    const conf = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
    return {
      key: p.key, dir: p.dir,
      title: conf.navigationBarTitleText || p.title,
      wxml: fs.readFileSync(wxmlPath, 'utf8'),
      js: fs.readFileSync(jsPath, 'utf8')
    };
  });
}

function main() {
  const appJson = JSON.parse(fs.readFileSync(path.join(FRONTEND, 'app.json'), 'utf8'));
  const css = buildCss();
  const mods = buildPageModules();

  const pageScripts = mods.map((m) => `
/* ===== ${m.key} ===== */
(function () {
  window.__kepuCurrentPage = null;
  ${m.js}
  window.__kepuPages[${JSON.stringify(m.key)}] = window.__kepuCurrentPage;
})();
`).join('\n');

  // 运行时本体来自 demo/runtime.js（独立文件，避免正则转义在拼装时被吃掉）
  const runtimeJs = fs.readFileSync(path.join(ROOT, 'demo', 'demo_runtime.js'), 'utf8');
  const pageSources = {};
  const pageOptions = {};
  mods.forEach((m) => {
    pageSources[m.key] = m.wxml;
    pageOptions[m.key] = { title: m.title };
  });
  const tabBarList = (appJson.tabBar || {}).list || [];

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>科普知识闯关小程序 · 浏览器演示</title>
<style>
${css}
/* ================= 演示外壳（不属于小程序本身） ================= */
/* 说明：所有 rpx 已在生成阶段换算为固定 px（1rpx = 0.5px），
   因此这里不需要任何根字号 hack。 */
html, body { margin: 0; height: 100%; background: #eef3f9; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 14px; }
.stage { display: flex; gap: 28px; align-items: flex-start; justify-content: center; padding: 28px 20px 40px; min-height: 100%; box-sizing: border-box; }
.side { width: 300px; color: #35506e; font-size: 13px; line-height: 1.85; }
.side h1 { font-size: 17px; margin: 0 0 6px; color: #1f3d5c; }
.side .tip { background: #fff; border-radius: 12px; padding: 14px 16px; box-shadow: 0 6px 18px rgba(31,61,92,.08); margin-bottom: 12px; }
.side code { background: #eaf1f8; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
.side ol { margin: 6px 0 0 18px; padding: 0; }
.side li { margin-bottom: 4px; }
.badge { display: inline-block; background: #4FC3F7; color: #fff; border-radius: 999px; padding: 2px 10px; font-size: 12px; margin-bottom: 8px; }
.phone { width: 375px; height: 748px; background: #fff; border-radius: 38px; box-shadow: 0 18px 50px rgba(20,50,80,.28); overflow: hidden; display: flex; flex-direction: column; position: relative; flex: 0 0 auto; }
.mp-statusbar { height: 24px; background: #4FC3F7; flex: 0 0 24px; }
.mp-titlebar { height: 44px; background: #4FC3F7; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 600; flex: 0 0 44px; }
.mp-body { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; position: relative; }
.mp-page { display: flex; flex-direction: column; min-height: 100%; }
.mp-tabbar { height: 54px; border-top: 1px solid #E3EEF7; display: flex; background: #fff; flex: 0 0 54px; }
.mp-tab { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 13px; color: #9AA7B4; cursor: pointer; }
.mp-tab.on { color: #0288D1; font-weight: 600; }
#mp-toast { position: absolute; left: 50%; top: 55%; transform: translate(-50%,-50%) scale(.9); background: rgba(30,40,50,.86); color: #fff; padding: 10px 18px; border-radius: 10px; font-size: 14px; opacity: 0; pointer-events: none; transition: .2s; max-width: 70%; text-align: center; }
#mp-toast.show { opacity: 1; transform: translate(-50%,-50%) scale(1); }
#mp-loading { position: absolute; inset: 0; background: rgba(255,255,255,.62); display: none; align-items: center; justify-content: center; flex-direction: column; gap: 10px; }
#mp-loading.show { display: flex; }
#mp-loading .ring { width: 34px; height: 34px; border: 3px solid #CBE7F7; border-top-color: #4FC3F7; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
#mp-loading-text { font-size: 14px; color: #35506e; }
#mp-modal { position: absolute; inset: 0; background: rgba(20,40,60,.42); display: none; align-items: center; justify-content: center; }
#mp-modal.show { display: flex; }
#mp-modal .box { width: 76%; background: #fff; border-radius: 14px; overflow: hidden; text-align: center; }
#mp-modal .box h3 { margin: 0; padding: 18px 16px 6px; font-size: 16px; color: #2F3E4E; }
#mp-modal .box p { margin: 0; padding: 0 18px 16px; font-size: 14px; color: #7B8A99; line-height: 1.6; }
#mp-modal .btns { display: flex; border-top: 1px solid #E3EEF7; }
#mp-modal button { flex: 1; border: 0; background: #fff; padding: 13px 0; font-size: 15px; cursor: pointer; color: #7B8A99; font-family: inherit; }
#mp-modal button + button { border-left: 1px solid #E3EEF7; }
.mp-page[data-page="pages/index"] #mp-view, .mp-page #mp-view { }
</style>
</head>
<body>
<div class="stage">
  <div class="side">
    <span class="badge">浏览器演示</span>
    <h1>科普知识闯关小程序</h1>
    <div class="tip">
      这个页面加载的是 <code>frontend/</code> 里<strong>真实的 WXML / WXSS / 页面 JS</strong>，
      数据打的是真实后端接口，用来在没有微信开发者工具时先把流程点通。
      最终交付的仍是<strong>标准微信小程序工程</strong>（<code>frontend/</code> 目录），
      用微信开发者工具导入即可。
    </div>
    <div class="tip">
      <strong>可以这样试</strong>
      <ol>
        <li>首页选学段 → 输入「太阳系」→ 开始出题</li>
        <li>答题页故意答错两题，看「小科」的鼓励提示</li>
        <li>答完看复盘报告（来源会据实标注）</li>
        <li>错题本 → 只练错题（不调用大模型，很快）</li>
        <li>底部切换：去闯关 / 错题本 / 知识库 / 我的</li>
      </ol>
    </div>
    <div class="tip">
      后端需在运行中：<code>scripts\\run_server.cmd</code><br>
      接口地址：<code id="api-base-label"></code>
    </div>
  </div>

  <div class="phone">
    <div class="mp-statusbar"></div>
    <div class="mp-titlebar" id="mp-title">科普闯关</div>
    <div class="mp-body">
      <div id="mp-view"></div>
      <div id="mp-toast"></div>
      <div id="mp-loading"><div class="ring"></div><div id="mp-loading-text">小科正在准备…</div></div>
      <div id="mp-modal">
        <div class="box">
          <h3 id="mp-modal-title"></h3>
          <p id="mp-modal-content"></p>
          <div class="btns">
            <button id="mp-modal-cancel">取消</button>
            <button id="mp-modal-ok">确定</button>
          </div>
        </div>
      </div>
    </div>
    <div class="mp-tabbar" id="mp-tabbar"></div>
  </div>
</div>


<script>
${runtimeJs}
</script>
<script>
/* ---------- 页面源与路由表（供运行时渲染使用） ---------- */
window.__kepuPageSources = ${JSON.stringify(pageSources)};
window.__kepuPageMeta = ${JSON.stringify(pageOptions)};
window.__kepuTabBar = ${JSON.stringify(tabBarList)};
</script>
<script>
/* ---------- 依赖注入：把 utils/request.js 与 config.js 接进来 ---------- */
(function () {
  var CONFIG_SRC = ${JSON.stringify(fs.readFileSync(path.join(FRONTEND, 'config.js'), 'utf8'))};
  var REQUEST_SRC = ${JSON.stringify(fs.readFileSync(path.join(FRONTEND, 'utils', 'request.js'), 'utf8'))};
  function runModule(src, name) {
    var mod = { exports: {} };
    var fn = new Function('module', 'exports', 'require', 'wx', src);
    fn(mod, mod.exports, function (p) {
      if (p.indexOf('config') !== -1) return window.__kepuModules['config'];
      return {};
    }, window.wx);
    window.__kepuModules[name] = mod.exports;
    return mod.exports;
  }
  runModule(CONFIG_SRC, 'config');
  runModule(REQUEST_SRC, 'utils/request');
})();
</script>
<script>
/* ---------- app.js ---------- */
(function () {
  var APP_SRC = ${JSON.stringify(fs.readFileSync(path.join(FRONTEND, 'app.js'), 'utf8'))};
  var mod = { exports: {} };
  var fn = new Function('module', 'exports', 'require', 'wx', 'App', APP_SRC);
  fn(mod, mod.exports, function (p) {
    if (p.indexOf('request') !== -1) return window.__kepuModules['utils/request'];
    return {};
  }, window.wx, window.App);
})();
</script>
<script>
${pageScripts}
</script>
<script>
document.getElementById('api-base-label').textContent =
  localStorage.getItem('kepu_api_base') || 'http://127.0.0.1:8000/api/v1';
window.__kepuBoot();
</script>
</body>
</html>
`;

  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(OUT_FILE, html, 'utf8');
  console.log('已生成 ' + OUT_FILE + '（' + (html.length / 1024).toFixed(1) + ' KB）');
}

main();
