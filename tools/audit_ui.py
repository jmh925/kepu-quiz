# -*- coding: utf-8 -*-
"""界面与渲染审计：在多种视口宽度下量化找问题，不靠肉眼猜。

查什么（都是能客观判定的）：
1. **横向溢出**：页面出现横向滚动条，或某个元素比它的容器还宽；
2. **元素越界**：元素右边缘超出视口；
3. **点击目标过小**：可点元素小于 40×40（触摸屏上很难点准）；
4. **文字截断**：单行容器里的文字被裁掉（scrollWidth > clientWidth 且没有省略号）；
5. **顶栏拥挤**：顶栏里的各项互相重叠，或换行后错位；
6. **对比度不足**：正文/按钮文字与背景的对比度低于 4.5:1（WCAG AA）；
7. **空渲染**：该有内容的容器是空的（例如胶囊、卡片列表）。

用法：
    python tools/audit_ui.py                 # 审计本地 127.0.0.1:8000
    python tools/audit_ui.py --url https://xxx.trycloudflare.com
    python tools/audit_ui.py --shots         # 顺便把各视口截图存下来
"""
import argparse
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

# 覆盖真实使用场景：手机竖屏、小平板、笔记本、宽屏
VIEWPORTS = [
    ("手机 390", 390, 844),
    ("平板 768", 768, 1024),
    ("笔记本 1180", 1180, 900),
    ("宽屏 1440", 1440, 950),
]

STUDENT_PAGES = [
    ("home", "去闯关"),
    ("pk", "PK 对战"),
    ("ranks", "成长阶梯"),
    ("wrong", "错题本"),
    ("knowledge", "知识库"),
    ("profile", "我的"),
]

MIN_TAP = 40          # 触摸优先界面（学生端）的按钮目标尺寸
MIN_TAP_DESKTOP = 32  # 鼠标优先界面（管理端）的按钮目标尺寸
WCAG_TARGET = 24      # WCAG 2.5.8（AA）对点击目标的硬底线，任何界面都必须满足
MIN_CONTRAST = 4.5    # WCAG AA 正文对比度

problems = []
notes = []


def check(ok, msg, hard=True):
    """hard=True 的失败计入未通过；hard=False 只提示（[注意]），不影响结论。

    两者必须分开记：早前把提示也塞进 problems，于是"文字链接 24px 达标边缘"
    这种非阻塞项会让整轮审计判为失败，噪音盖过了真问题。
    """
    tag = "[OK  ] " if ok else ("[FAIL] " if hard else "[注意] ")
    print(tag + msg)
    if not ok:
        (problems if hard else notes).append(msg)


# 注入到页面里的审计函数：一次把该页所有指标量出来
AUDIT_JS = r"""
(minTap) => {
  // 按钮目标尺寸由调用方按界面类型给：学生端 40（触摸优先），管理端 32（鼠标优先）。
  // 纯文字链接一律按 WCAG 2.5.8 的 24px —— 那是标准里的硬底线。
  const MIN_TAP = minTap;
  const WCAG_TARGET = 24;   // WCAG 2.5.8 的硬底线，任何界面都不许破
  const out = {
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    vw: window.innerWidth,
    overflowing: [],     // 比视口宽的元素
    tinyTaps: [],        // 太小的可点元素
    clipped: [],         // 被裁掉的单行文字
    emptyBoxes: [],      // 该有内容却是空的容器
    topbar: null,
  };
  const sel = 'div,section,table,header,nav,main,button,a,input,select,span';

  // 判断元素是否处在某个可横向滚动（或裁切）的祖先里。
  // 这种元素"超出视口"是设计意图（例如窄屏下横向滑动的导航条），
  // 不该报成越界；第一版没排除，把导航链接全报成了溢出。
  const inScroller = (el) => {
    let p = el.parentElement;
    while (p && p !== document.body) {
      const cs = getComputedStyle(p);
      const scrollable = (cs.overflowX === 'auto' || cs.overflowX === 'scroll' ||
                          cs.overflowX === 'hidden' || cs.overflow === 'auto' ||
                          cs.overflow === 'scroll' || cs.overflow === 'hidden');
      if (scrollable) return true;
      p = p.parentElement;
    }
    return false;
  };

  // 1/2. 越界元素（只看有实际尺寸的）
  document.querySelectorAll(sel).forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || cs.visibility === 'hidden' || cs.display === 'none') return;
    if (inScroller(el)) return;
    if (r.right > out.vw + 1) {
      const path = el.tagName.toLowerCase() +
        (el.id ? '#' + el.id : '') +
        (el.className && typeof el.className === 'string'
           ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : '');
      out.overflowing.push({sel: path, right: Math.round(r.right), w: Math.round(r.width)});
    }
  });

  // 3. 点击目标：按钮类按触摸标准 40px，纯文字链接按 WCAG 2.5.8 的 24px
  document.querySelectorAll('button,a,[data-opt],[data-toggle],[data-topic],[onclick]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const isButton = el.tagName === 'BUTTON' || el.hasAttribute('data-opt') ||
                     el.hasAttribute('data-toggle') || el.hasAttribute('data-topic');
    const need = isButton ? Math.max(MIN_TAP, WCAG_TARGET) : WCAG_TARGET;
    if (r.height < need || r.width < need) {
      const label = (el.innerText || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 14);
      out.tinyTaps.push({label: label, w: Math.round(r.width), h: Math.round(r.height),
                         need: need, kind: isButton ? '按钮' : '链接'});
    }
  });

  // 4. 文字截断：单行 + overflow hidden + 内容比可视宽
  document.querySelectorAll('div,span,td,th,p,h1,h2,h3,button,a').forEach(el => {
    if (!el.childNodes.length) return;
    const cs = getComputedStyle(el);
    if (cs.whiteSpace !== 'nowrap' && cs.textOverflow !== 'ellipsis') return;
    if (cs.textOverflow === 'ellipsis') return;      // 有省略号是设计意图
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {
      const label = (el.innerText || '').trim().slice(0, 16);
      out.clipped.push({label: label, need: el.scrollWidth, have: el.clientWidth});
    }
  });

  // 5. 顶栏：各子项是否互相重叠 / 是否挤成多行
  const tb = document.querySelector('.topbar');
  if (tb) {
    // 重叠：同一行内左右区间相交。
    // 必须排除**祖先-后代**关系：顶栏里 #lv-chip 是 span，它内部还有两个 span，
    // 它们天然"重叠"。第一版没排除，宽屏下报出 2 处重叠，其实是父子关系。
    let overlap = 0;
    const els = [];
    tb.querySelectorAll('a,button,span').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return;
      els.push({el: el, t: (el.innerText||'').trim().slice(0,10),
                l: Math.round(r.left), r: Math.round(r.right),
                top: Math.round(r.top), bottom: Math.round(r.bottom)});
    });
    const kids = els;
    for (let i = 0; i < kids.length; i++) {
      for (let j = i + 1; j < kids.length; j++) {
        const a = kids[i], b = kids[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const sameRow = !(a.bottom <= b.top + 1 || b.bottom <= a.top + 1);
        if (sameRow && a.l < b.r - 1 && b.l < a.r - 1) overlap++;
      }
    }
    // 行数：按**垂直区间是否相交**归并成"行带"，而不是数 top 有几个不同值 ——
    // 同一行里不同高度的元素（24px 的链接和 34px 的按钮垂直居中）top 本来就不同，
    // 数 top 会把一行误报成五行。
    const bands = [];
    kids.slice().sort((a, b) => a.top - b.top).forEach(k => {
      const hit = bands.find(b => !(k.bottom <= b.top + 1 || b.bottom <= k.top + 1));
      if (hit) { hit.top = Math.min(hit.top, k.top); hit.bottom = Math.max(hit.bottom, k.bottom); }
      else bands.push({top: k.top, bottom: k.bottom});
    });
    out.topbar = {h: Math.round(tb.getBoundingClientRect().height),
                  rows: bands.length, kids: kids.length, overlap: overlap,
                  w: Math.round(tb.getBoundingClientRect().width)};
  }

  // 6. 该有内容的容器却是空的（只算**可见**的：管理端有多个 hidden 的视图，
  //    它们的表格元素天然是空的，不该算问题）
  const mustHaveContent = ['.chips', '.settle-grid', '.rank-row', '.options',
                           '#u-table', '#q-table'];
  mustHaveContent.forEach(s => {
    document.querySelectorAll(s).forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
      if (!el.children.length && !(el.innerText || '').trim()) out.emptyBoxes.push(s);
    });
  });

  // 7. 关键文字的颜色与背景，供对比度计算
  const samples = [];
  const pick = (sel, label) => {
    const el = document.querySelector(sel);
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.width < 2) return;
    const cs = getComputedStyle(el);
    // 往上找第一个**不透明**背景。
    // 注意：只有 background-color 是不够的——渐变写在 background-image 里，
    // 而此时的 background-color 是 rgba(0,0,0,0)。第一版没看 background-image，
    // 于是"主按钮"一路找到了页面白底，算出白字白底 1.30:1 这种假数字。
    let bg = '', node = el, gradient = false;
    while (node) {
      const s = getComputedStyle(node);
      const img = s.backgroundImage || 'none';
      if (img !== 'none' && img.indexOf('gradient') >= 0) { gradient = true; break; }
      const c = s.backgroundColor;
      const m = c && c.match(/rgba?\(([^)]+)\)/);
      if (m) {
        const parts = m[1].split(',').map(x => parseFloat(x));
        const alpha = parts.length > 3 ? parts[3] : 1;
        if (alpha > 0.95) { bg = c; break; }
      }
      node = node.parentElement;
    }
    // 渐变背景下无法用一个数值代表对比度，标记为"无法判定"而不是编一个数
    samples.push({label: label, fg: cs.color, bg: bg, gradient: gradient,
                  size: parseFloat(cs.fontSize), weight: cs.fontWeight});
  };
  pick('.muted', '次要文字');
  pick('.tag', '小标签');
  pick('.btn-primary', '主按钮');
  pick('.lv-chip', '顶栏段位胶囊');
  pick('.rank-name', '段位名');
  pick('.chip-group-label', '分组标题');
  // 管理端专用（学生端页面上取不到就跳过）。
  // 注意标签要和学生端区分开，否则同名会在去重时把管理端那组盖掉。
  pick('.table th', '管理端表头');
  pick('.nav a', '管理端导航项');
  pick('.card .k', '管理端指标名');
  pick('.card .s', '管理端指标说明');
  pick('.tip', '管理端提示文字');
  pick('.view .btn-primary', '管理端主按钮');
  pick('.tag-ok', '管理端成功标签');
  pick('.tag-warn', '管理端提醒标签');
  pick('.tag-off', '管理端停用标签');
  out.colorSamples = samples;
  return out;
}
"""


def rel_lum(rgb):
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])


def parse_color(s):
    s = (s or "").strip()
    if s.startswith("rgb"):
        nums = s[s.find("(") + 1:s.find(")")].replace(",", " ").split()
        try:
            vals = [float(x.rstrip("%")) for x in nums[:4]]
        except ValueError:
            return None
        if len(vals) == 4 and vals[3] == 0:
            return None
        return tuple(int(v) for v in vals[:3])
    return None


def contrast(fg, bg):
    a, b = parse_color(fg), parse_color(bg)
    if not a or not b:
        return None
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def login(pg, base, role="student", username=None, password=None):
    """登录（学生或管理员），返回是否成功。"""
    if role == "admin":
        u, p = kepu_env.admin_credentials()
        pg.goto(base + "/admin/", timeout=90000)
        pg.wait_for_timeout(2500)
        if pg.locator("#app").is_visible():
            return True
        pg.locator("#username").fill(username or u)
        pg.locator("#password").fill(password or p)
        pg.locator("#login-form button[type=submit]").click()
        pg.wait_for_timeout(2500)
        return pg.locator("#app").is_visible()
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("KEPU_WEB_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--shots", action="store_true", help="顺便截图")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    web = base + "/app/"
    shots = os.path.join(ROOT, "web", "shots")
    if args.shots:
        os.makedirs(shots, exist_ok=True)

    from playwright.sync_api import sync_playwright      # noqa: E402

    uname = "ui" + str(int(__import__("time").time() * 1000))[-8:]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1180, "height": 900})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))

        # 注册一个学生账号，后面各页才有内容可审
        pg.goto(web, timeout=90000)
        pg.wait_for_timeout(2500)
        pg.locator("#tab-register").click()
        pg.wait_for_timeout(400)
        pg.locator("#auth-user").fill(uname)
        pg.locator("#auth-pass").fill("kepu123456")
        pg.locator("#auth-nick").fill("界面审同学")
        pg.locator("#auth-grade").select_option("primary_high")
        pg.locator("#auth-submit").click()
        pg.wait_for_timeout(3000)

        all_color_samples = []
        for label, w, h in VIEWPORTS:
            print("\n" + "=" * 66)
            print("  视口 %s（%d × %d）" % (label, w, h))
            print("=" * 66)
            pg.set_viewport_size({"width": w, "height": h})
            for route, name in STUDENT_PAGES:
                pg.goto(web + "#/" + route)
                pg.wait_for_timeout(1600)
                d = pg.evaluate(AUDIT_JS, MIN_TAP)
                prefix = "%s / %s" % (label, name)

                # 横向溢出
                doc_over = d["docScrollW"] > d["docClientW"] + 1
                check(not doc_over, "%s：页面没有横向滚动条（%d vs %d）"
                      % (prefix, d["docScrollW"], d["docClientW"]))
                if d["overflowing"]:
                    worst = sorted(d["overflowing"], key=lambda x: -x["right"])[:3]
                    check(False, "%s：有元素超出视口 %s" % (prefix, worst))
                else:
                    check(True, "%s：没有元素超出视口" % prefix)

                # 点击目标：按钮按触摸标准 40px，纯文字链接按 WCAG 2.5.8 的 24px
                if d["tinyTaps"]:
                    uniq = {}
                    for t in d["tinyTaps"]:
                        uniq["%s(%s)" % (t["label"], t["kind"])] = (t["w"], t["h"])
                    # 只有按钮偏小才算硬问题；链接只要 ≥24px 就符合 WCAG AA
                    hard = any(t["kind"] == "按钮" for t in d["tinyTaps"])
                    check(False, "%s：点击目标偏小 %d 处 %s"
                          % (prefix, len(d["tinyTaps"]), list(uniq.items())[:4]), hard=hard)
                else:
                    check(True, "%s：可点元素尺寸都达标" % prefix)

                # 文字截断
                if d["clipped"]:
                    check(False, "%s：文字被裁掉 %s" % (prefix, d["clipped"][:3]), hard=False)
                else:
                    check(True, "%s：没有被裁掉的文字" % prefix)

                # 空容器
                if d["emptyBoxes"]:
                    check(False, "%s：该有内容的容器是空的 %s"
                          % (prefix, sorted(set(d["emptyBoxes"]))))
                else:
                    check(True, "%s：没有空的内容容器" % prefix)

                # 顶栏（只看一次就够了，但每页都量一下以防页面切换出错）
                tb = d["topbar"]
                if tb:
                    # 窄屏允许折成两行（品牌+状态一行，导航一行）；宽屏必须单行
                    max_rows = 2 if w <= 900 else 1
                    check(tb["overlap"] == 0 and tb["rows"] <= max_rows,
                          "%s：顶栏无重叠且不超过 %d 行（%d 项 / %d 行 / 重叠 %d）"
                          % (prefix, max_rows, tb["kids"], tb["rows"], tb["overlap"]))

                if w == 1180:
                    all_color_samples.extend(d["colorSamples"])
                if args.shots and w in (390, 1440):
                    tag = "ui_%d_%s" % (w, route)
                    pg.screenshot(path=os.path.join(shots, tag + ".png"), full_page=True)

        # 对比度（只报一次，按最差情况）
        print("\n" + "=" * 66)
        print("  文字对比度（WCAG AA 要求 ≥ %.1f:1）" % MIN_CONTRAST)
        print("=" * 66)
        seen = {}
        for s in all_color_samples:
            seen.setdefault(s["label"], s)
        for label, s in seen.items():
            if s.get("gradient"):
                print("[跳过] %s：背景是渐变，无法用一个数值代表对比度" % label)
                continue
            c = contrast(s["fg"], s["bg"])
            if c is None:
                print("[跳过] %s：背景色取不到不透明值（fg=%s bg=%s）"
                      % (label, s["fg"], s["bg"]))
                continue
            # 大字（≥18pt 或 ≥14pt 粗体）标准放宽到 3:1
            big = s["size"] >= 24 or (s["size"] >= 18.66 and int(s["weight"] or 400) >= 700)
            need = 3.0 if big else MIN_CONTRAST
            # 每个组合都打印实测值，作为"确实达标"的证据，而不是只说没失败
            check(c >= need, "%s %.2f:1（要求 %.1f，字号 %.0fpx，%s）"
                  % (label, c, need, s["size"], s["fg"]))

        # ---------- 管理端 ----------
        print("\n" + "=" * 66)
        print("  管理端（1180 × 900）")
        print("=" * 66)
        pg.set_viewport_size({"width": 1180, "height": 900})
        admin_colors = []
        if login(pg, base, role="admin"):
            for route, name in [("dashboard", "看板"), ("questions", "题库"),
                                ("users", "用户"), ("sessions", "闯关记录"),
                                ("logs", "日志")]:
                pg.goto(base + "/admin/#/" + route)
                pg.wait_for_timeout(1800)
                d = pg.evaluate(AUDIT_JS, MIN_TAP_DESKTOP)
                check(d["docScrollW"] <= d["docClientW"] + 1,
                      "管理端 %s：没有横向滚动条" % name)
                check(not d["overflowing"], "管理端 %s：没有元素超出视口%s"
                      % (name, "" if not d["overflowing"] else " " + str(d["overflowing"][:2])))
                if d["emptyBoxes"]:
                    check(False, "管理端 %s：空容器 %s" % (name, sorted(set(d["emptyBoxes"]))))
                if d["tinyTaps"]:
                    hard = any(t["kind"] == "按钮" for t in d["tinyTaps"])
                    uniq = {}
                    for t in d["tinyTaps"]:
                        uniq["%s(%s)" % (t["label"], t["kind"])] = (t["w"], t["h"])
                    check(False, "管理端 %s：点击目标偏小 %s" % (name, list(uniq.items())[:3]),
                          hard=hard)
                admin_colors.extend(d["colorSamples"])
            # 学生详情弹窗
            pg.goto(base + "/admin/#/users")
            pg.wait_for_timeout(2000)
            pg.locator("#u-keyword").fill(uname)
            pg.locator("#view-users button:has-text('搜索')").click()
            pg.wait_for_timeout(2000)
            if pg.locator("#u-table button:has-text('答题详情')").count():
                pg.locator("#u-table button:has-text('答题详情')").first.click()
                pg.wait_for_timeout(2500)
                d = pg.evaluate(AUDIT_JS, MIN_TAP_DESKTOP)
                check(not d["overflowing"], "管理端学生详情弹窗：没有元素超出视口%s"
                      % ("" if not d["overflowing"] else " " + str(d["overflowing"][:2])))
                if args.shots:
                    pg.screenshot(path=os.path.join(shots, "ui_admin_detail.png"), full_page=True)
        else:
            check(False, "管理端登录失败，跳过管理端审计")

        # 管理端的对比度也要量：只查版面不查颜色的话，
        # 「次要文字 4.38:1」这种不达标会一直藏着（这轮就是补上这一项才发现的）。
        if admin_colors:
            print("\n" + "=" * 66)
            print("  管理端文字对比度（WCAG AA 要求 ≥ %.1f:1）" % MIN_CONTRAST)
            print("=" * 66)
            aseen = {}
            for s in admin_colors:
                aseen.setdefault(s["label"], s)
            for label, s in aseen.items():
                if s.get("gradient"):
                    print("[跳过] 管理端 %s：背景是渐变" % label)
                    continue
                c = contrast(s["fg"], s["bg"])
                if c is None:
                    print("[跳过] 管理端 %s：背景色取不到不透明值" % label)
                    continue
                big = s["size"] >= 24 or (s["size"] >= 18.66 and int(s["weight"] or 400) >= 700)
                need = 3.0 if big else MIN_CONTRAST
                check(c >= need, "管理端 %s %.2f:1（要求 %.1f，字号 %.0fpx，%s）"
                      % (label, c, need, s["size"], s["fg"]))

        check(not errs, "全程无 JS 报错%s" % ("" if not errs else "：" + " | ".join(errs[:2])))
        b.close()

    print("\n未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    if notes:
        print("提示（不影响结论）：%d 项" % len(notes))
        for x in notes[:6]:
            print("  · " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
