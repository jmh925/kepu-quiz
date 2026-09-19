/* eslint-disable */
/**
 * 演示页运行时（浏览器端迷你「小程序」实现）。
 *
 * 为什么单独放一个文件而不是在生成脚本里拼字符串：这段代码里有正则与模板字符串，
 * 用脚本拼装容易被转义规则吃掉反斜杠（本文件就是这么踩过一次坑）。独立成文件后
 * 由 tools/make_demo.js 原样内联进 demo/index.html，所见即所得。
 *
 * 它提供的能力，足以让 frontend/ 里真实的页面 JS 不改一行就跑起来：
 *   wx.request / wx.showToast / wx.showLoading / wx.showModal / wx.setStorageSync
 *   wx.navigateTo / wx.switchTab / wx.reLaunch / wx.navigateBack
 *   App / Page / Component 注册、setData、WXML 模板渲染（{{}}、wx:if/elif/else、wx:for）
 *   hover-class、data-* 数据集、bindtap/bindinput/bindconfirm 事件
 *
 * 渲染方式：**按节点对比更新 DOM**（不是每次 setData 都重建 innerHTML）。
 * 这一点很关键——页面在 bindinput 里会 setData，如果整段重建，
 * 正在输入的 input 会被销毁，表现就是「打一个字就丢焦点」。
 */
(function () {
  /* ---------------- 请求地址与存储 ---------------- */
  var API_BASE = localStorage.getItem('kepu_api_base') || 'http://127.0.0.1:8000/api/v1';

  var storage = {
    get: function (k) { try { return JSON.parse(localStorage.getItem('kepu_st_' + k)); } catch (e) { return ''; } },
    set: function (k, v) { try { localStorage.setItem('kepu_st_' + k, JSON.stringify(v)); } catch (e) {} },
    remove: function (k) { try { localStorage.removeItem('kepu_st_' + k); } catch (e) {} }
  };

  /* ---------------- UI 反馈 ---------------- */
  function toast(title) {
    var el = document.getElementById('mp-toast');
    el.textContent = title || '';
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove('show'); }, 2000);
  }
  function showLoading(title) {
    document.getElementById('mp-loading-text').textContent = title || '小科正在准备…';
    document.getElementById('mp-loading').classList.add('show');
  }
  function hideLoading() { document.getElementById('mp-loading').classList.remove('show'); }
  function showModal(opt) {
    var el = document.getElementById('mp-modal');
    document.getElementById('mp-modal-title').textContent = opt.title || '';
    document.getElementById('mp-modal-content').textContent = opt.content || '';
    var okBtn = document.getElementById('mp-modal-ok');
    var cancelBtn = document.getElementById('mp-modal-cancel');
    okBtn.textContent = opt.confirmText || '确定';
    cancelBtn.textContent = opt.cancelText || '取消';
    okBtn.style.color = opt.confirmColor || '#0288D1';
    el.classList.add('show');
    okBtn.onclick = function () { el.classList.remove('show'); opt.success && opt.success({ confirm: true, cancel: false }); };
    cancelBtn.onclick = function () { el.classList.remove('show'); opt.success && opt.success({ confirm: false, cancel: true }); };
  }

  /* ---------------- wx.* ---------------- */
  window.wx = {
    request: function (opt) {
      // 关键：config.js 里的 BASE_URL 已经是完整地址（含 /api/v1），
      // 因此这里不能再拼一次 API_BASE，否则会出现
      // "…/api/v1http://127.0.0.1:8000/api/v1/grades" 这种双前缀 404。
      var url = String(opt.url || '');
      if (url.indexOf('http://') !== 0 && url.indexOf('https://') !== 0) url = API_BASE + url;
      var init = { method: opt.method || 'GET', headers: Object.assign({}, opt.header || {}) };
      if (opt.data && String(opt.method).toUpperCase() !== 'GET') init.body = JSON.stringify(opt.data);
      fetch(url, init).then(function (r) {
        return r.text().then(function (t) {
          var body;
          try { body = JSON.parse(t); } catch (e) { body = { code: -1, message: '响应解析失败' }; }
          opt.success && opt.success({ statusCode: r.status, data: body });
        });
      }).catch(function () { opt.fail && opt.fail({ errMsg: 'request:fail' }); });
      return { abort: function () {} };
    },
    uploadFile: function (opt) {
      toast('浏览器演示不支持选择文件，上传请用微信开发者工具或真机');
      opt.fail && opt.fail({});
    },
    login: function (opt) { setTimeout(function () { opt.success && opt.success({ code: 'demo_' + Date.now() }); }, 60); },
    showToast: function (o) { toast(o && o.title); },
    hideToast: function () { document.getElementById('mp-toast').classList.remove('show'); },
    showLoading: function (o) { showLoading(o && o.title); },
    hideLoading: hideLoading,
    showModal: showModal,
    getStorageSync: storage.get,
    setStorageSync: storage.set,
    removeStorageSync: storage.remove,
    stopPullDownRefresh: function () {},
    setNavigationBarTitle: function (o) { setTitle(o && o.title); },
    navigateTo: function (o) { router.push(o.url); },
    redirectTo: function (o) { router.replace(o.url); },
    switchTab: function (o) { router.replace(o.url); },
    reLaunch: function (o) { router.reset(o.url); },
    navigateBack: function () { router.back(); }
  };
  window.qq = window.wx;

  /* ---------------- 模块系统（供 utils/request.js 这类文件使用） ---------------- */
  window.__kepuModules = {};
  window.require = function (p) {
    var mods = window.__kepuModules;
    if (mods[p]) return mods[p];
    // 按后缀匹配：页面里写的是 '../../utils/request' 这类相对路径，
    // 而注册用的是 'utils/request'，不做归一化会拿到空对象
    // （这会导致 api.post is not a function 这种难查的错误）。
    var normalized = String(p).replace(/\\/g, '/').replace(/^\.+\//, '');
    var keys = Object.keys(mods);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i] === normalized
          || normalized.indexOf(keys[i]) !== -1
          || keys[i].indexOf(normalized) !== -1) {
        return mods[keys[i]];
      }
    }
    return {};
  };

  /* ---------------- 模板引擎 ---------------- */
  var exprCache = {};
  var KEYWORDS = {
    'true': 1, 'false': 1, 'null': 1, 'undefined': 1, 'typeof': 1, 'in': 1, 'of': 1, 'new': 1,
    'Math': 1, 'Date': 1, 'JSON': 1, 'String': 1, 'Number': 1, 'Boolean': 1, 'Array': 1, 'Object': 1
  };

  function compile(expr) {
    // 只在「合法标识符起点」上做作用域前缀替换：前面不能是点、引号、$ 或标识符字符。
    // 否则 !canAsk 会被切错、字符串内容也会被改写（这两个坑都踩过）。
    var t = expr.replace(/(^|[^.\w$'"])([A-Za-z_$][A-Za-z0-9_$]*)/g, function (m, pre, name) {
      if (KEYWORDS[name]) return m;
      return pre + 'scope["' + name + '"]';
    });
    try {
      return new Function('scope', 'try { return (' + t + '); } catch (e) { return undefined; }');
    } catch (e) {
      return function () { return undefined; };
    }
  }
  function evalExpr(expr, scope) {
    if (!exprCache[expr]) exprCache[expr] = compile(expr);
    return exprCache[expr](scope);
  }
  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function attrValue(raw) {
    if (raw === undefined) return true;
    var m = /^\{\{([\s\S]*)\}\}$/.exec(String(raw).trim());
    if (m) return { dynamic: m[1].trim() };
    return String(raw).replace(/^["']|["']$/g, '');
  }

  /** 找到标签真正的结束位置：引号内的 > 不算（例如 wx:if="{{total > 0}}"）。 */
  function findTagEnd(src, from) {
    var quote = null;
    for (var i = from; i < src.length; i++) {
      var ch = src.charAt(i);
      if (quote) {
        if (ch === quote) quote = null;
        continue;
      }
      if (ch === '"' || ch === "'") { quote = ch; continue; }
      if (ch === '>') return i;
    }
    return -1;
  }

  function parseAttrs(text) {
    var out = [];
    var re = /([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*("([^"]*)"|'([^']*)')|([A-Za-z_:][-A-Za-z0-9_:.]*)/g;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (m[1]) out.push({ name: m[1], raw: m[3] !== undefined ? m[3] : m[4] });
      else if (m[5]) out.push({ name: m[5], raw: undefined });
    }
    return out;
  }

  function parseWxml(src) {
    var root = { tag: '#root', attrs: [], children: [] };
    var stack = [root];
    var i = 0;
    function pushText(t) {
      if (t.trim() === '') {
        if (t.indexOf('{{') !== -1) stack[stack.length - 1].children.push({ tag: '#text', text: ' ' });
        return;
      }
      stack[stack.length - 1].children.push({ tag: '#text', text: t });
    }
    while (i < src.length) {
      var lt = src.indexOf('<', i);
      if (lt === -1) { pushText(src.slice(i)); break; }
      pushText(src.slice(i, lt));
      if (src.startsWith('<!--', lt)) {
        var ce = src.indexOf('-->', lt);
        i = ce === -1 ? src.length : ce + 3;
        continue;
      }
      var gt = findTagEnd(src, lt + 1);
      if (gt === -1) { pushText(src.slice(lt)); break; }
      var inner = src.slice(lt + 1, gt);
      i = gt + 1;
      if (inner.charAt(0) === '/') { if (stack.length > 1) stack.pop(); continue; }
      var trimmed = inner.trim();
      var isVoid = trimmed.indexOf('input') === 0 || trimmed.indexOf('image') === 0 || trimmed.indexOf('br') === 0;
      var selfClose = inner.charAt(inner.length - 1) === '/' || isVoid;
      var body = selfClose ? inner.replace(/\/$/, '') : inner;
      var spaceAt = -1;
      for (var k = 0; k < body.length; k++) {
        var code = body.charCodeAt(k);
        if (code === 32 || code === 9 || code === 10 || code === 13) { spaceAt = k; break; }
      }
      var tag = (spaceAt === -1 ? body : body.slice(0, spaceAt)).trim();
      var node = { tag: tag, attrs: parseAttrs(spaceAt === -1 ? '' : body.slice(spaceAt)), children: [] };
      stack[stack.length - 1].children.push(node);
      if (!selfClose) stack.push(node);
    }
    return root;
  }

  var TAG_MAP = {
    view: 'div', text: 'span', image: 'img', block: 'div', 'scroll-view': 'div',
    button: 'button', input: 'input', textarea: 'textarea', navigator: 'a', form: 'form',
    label: 'label', picker: 'div', 'rich-text': 'div', progress: 'div'
  };
  var CAPTIONS = {
    idle: '我是小科，陪你一起探索科学', thinking: '小科正在思考…',
    correct: '答对啦，你真棒！', wrong: '差一点点，再看看解析？',
    encourage: '别着急，慢慢来～', win: '这一关通过啦！'
  };

  function directives(node, scope) {
    var forAttr = null, ifAttr = null;
    for (var i = 0; i < node.attrs.length; i++) {
      if (node.attrs[i].name === 'wx:for') forAttr = node.attrs[i];
      if (node.attrs[i].name === 'wx:if') ifAttr = node.attrs[i];
    }
    if (forAttr) {
      var av = attrValue(forAttr.raw);
      var list = (av && av.dynamic) ? evalExpr(av.dynamic, scope) : [];
      var itemName = 'item', indexName = 'index';
      node.attrs.forEach(function (a) {
        if (a.name === 'wx:for-item') itemName = a.raw;
        if (a.name === 'wx:for-index') indexName = a.raw;
      });
      var out = [];
      (Array.isArray(list) ? list : []).forEach(function (item, index) {
        var child = Object.create(scope);
        child[itemName] = item;
        child[indexName] = index;
        out.push({ scope: child });
      });
      return { repeat: out };
    }
    if (ifAttr) {
      var iv = attrValue(ifAttr.raw);
      return { visible: (iv && iv.dynamic) ? !!evalExpr(iv.dynamic, scope) : !!iv };
    }
    return {};
  }

  function renderText(text, scope) {
    if (text.indexOf('{{') === -1) return esc(text);
    var out = '';
    var rest = text;
    while (true) {
      var s = rest.indexOf('{{');
      if (s === -1) { out += esc(rest); break; }
      out += esc(rest.slice(0, s));
      var e = rest.indexOf('}}', s);
      if (e === -1) { out += esc(rest.slice(s)); break; }
      var v = evalExpr(rest.slice(s + 2, e), scope);
      out += esc(v === undefined || v === null ? '' : v);
      rest = rest.slice(e + 2);
    }
    return out;
  }

  function renderMascot(node, scope) {
    var state = 'idle', size = 'md', caption = '';
    node.attrs.forEach(function (a) {
      var v = attrValue(a.raw);
      var val = (v && v.dynamic) ? evalExpr(v.dynamic, scope) : v;
      if (a.name === 'state') state = val;
      if (a.name === 'size') size = val;
      if (a.name === 'caption') caption = val;
    });
    var shown = (caption && String(caption).length) ? caption : (CAPTIONS[state] || CAPTIONS.idle);
    return '<div class="mascot mascot-' + esc(size) + ' mascot-' + esc(state) + '">'
      + '<div class="mascot-stage">'
      + (state === 'thinking'
        ? '<div class="mascot-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>'
        : '')
      + '<div class="mascot-body"><div class="ear ear-left"></div><div class="ear ear-right"></div>'
      + '<div class="mascot-head"><div class="mascot-face"><div class="mascot-eyes">'
      + '<div class="eye eye-left"></div><div class="eye eye-right"></div></div>'
      + '<div class="mouth"></div><div class="cheek cheek-left"></div><div class="cheek cheek-right"></div>'
      + '</div></div></div></div>'
      + '<div class="mascot-caption">' + esc(shown) + '</div></div>';
  }

  function renderNode(node, scope) {
    if (node.tag === 'mascot') return renderMascot(node, scope);

    var tag = TAG_MAP[node.tag] || 'div';
    var cls = '', style = '', dataAttrs = '', events = '', attrsOut = '';

    node.attrs.forEach(function (a) {
      var name = a.name;
      if (name.indexOf('wx:') === 0) return;
      var av = attrValue(a.raw);

      if (name === 'class') {
        if (av && av.dynamic) {
          cls = String(evalExpr(av.dynamic, scope) || '');
        } else {
          cls = String(a.raw || '').replace(/\{\{([\s\S]*?)\}\}/g, function (m, ex) {
            var v = evalExpr(ex, scope);
            return v === undefined || v === null ? '' : String(v);
          });
        }
        cls = cls.replace(/\s+/g, ' ').trim();
        return;
      }
      if (name === 'style') { style = a.raw || ''; return; }
      if (name === 'hover-class' || name === 'placeholder-class') return;
      if (name.indexOf('data-') === 0) {
        var dv = (av && av.dynamic) ? evalExpr(av.dynamic, scope) : av;
        dataAttrs += ' data-' + name.slice(5) + '="' + esc(dv) + '"';
        return;
      }
      if (name.indexOf('bind') === 0 || name.indexOf('catch') === 0) {
        var handler = a.raw === undefined ? name.replace(/^(bind|catch)/, '') : a.raw;
        events += ' data-ev-' + name.replace(/^(bind|catch)/, '') + '="1" data-handler="' + esc(handler) + '"';
        return;
      }
      if (name === 'value') {
        var vv = (av && av.dynamic) ? evalExpr(av.dynamic, scope) : av;
        attrsOut += ' value="' + esc(vv === undefined ? '' : vv) + '"';
        return;
      }
      if (name === 'disabled') {
        var dvv = (av && av.dynamic) ? evalExpr(av.dynamic, scope) : av;
        if (dvv) attrsOut += ' disabled';
        return;
      }
      var plain = (av && av.dynamic) ? evalExpr(av.dynamic, scope) : (a.raw === undefined ? '' : a.raw);
      attrsOut += ' ' + name + '="' + esc(plain) + '"';
    });

    if (tag === 'input' || tag === 'img') {
      return '<' + tag + (cls ? ' class="' + esc(cls) + '"' : '')
        + (style ? ' style="' + esc(style) + '"' : '') + dataAttrs + events + attrsOut + '>';
    }
    return '<' + tag + (cls ? ' class="' + esc(cls) + '"' : '')
      + (style ? ' style="' + esc(style) + '"' : '') + dataAttrs + events + attrsOut + '>'
      + renderList(node.children, scope) + '</' + tag + '>';
  }

  function renderList(nodes, scope) {
    var html = '';
    var lastIf = null;
    for (var n = 0; n < nodes.length; n++) {
      var node = nodes[n];
      if (node.tag === '#text') { html += renderText(node.text, scope); continue; }

      var names = node.attrs.map(function (a) { return a.name; });
      if (names.indexOf('wx:elif') !== -1) {
        if (lastIf) continue;
        var eAttr = null;
        node.attrs.forEach(function (a) { if (a.name === 'wx:elif') eAttr = a; });
        var ev = attrValue(eAttr.raw);
        var ok = (ev && ev.dynamic) ? !!evalExpr(ev.dynamic, scope) : !!ev;
        lastIf = ok;
        if (!ok) continue;
      } else if (names.indexOf('wx:else') !== -1) {
        if (lastIf) continue;
        lastIf = true;
      } else if (names.indexOf('wx:if') !== -1 || names.indexOf('wx:for') !== -1) {
        var dir = directives(node, scope);
        if (dir.repeat) {
          for (var r = 0; r < dir.repeat.length; r++) html += renderNode(node, dir.repeat[r].scope);
          lastIf = null;
          continue;
        }
        if (dir.visible === false) { lastIf = false; continue; }
        lastIf = dir.visible === undefined ? null : true;
      } else {
        lastIf = null;
      }
      html += renderNode(node, scope);
    }
    return html;
  }

  /* ---------------- DOM 更新：按节点对比，保留输入焦点 ---------------- */
  var EVENTS = ['tap', 'input', 'change', 'confirm', 'blur', 'focus', 'longpress', 'submit'];
  var DOM_EVENT = {
    tap: 'click', input: 'input', change: 'change', confirm: 'keydown',
    blur: 'blur', focus: 'focus', longpress: 'contextmenu', submit: 'submit'
  };

  function bindEvents(scopeEl, inst) {
    EVENTS.forEach(function (evt) {
      var nodes = scopeEl.querySelectorAll('[data-ev-' + evt + ']:not([data-ev-bound])');
      Array.prototype.forEach.call(nodes, function (node) {
        node.setAttribute('data-ev-bound', '1');
        node.addEventListener(DOM_EVENT[evt], function (e) {
          if (evt === 'confirm' && e.key !== 'Enter') return;
          var handler = node.getAttribute('data-handler');
          var fn = inst.__options[handler];
          if (typeof fn !== 'function') return;
          var dataset = {};
          Array.prototype.forEach.call(node.attributes, function (at) {
            if (at.name.indexOf('data-') === 0 && at.name.indexOf('data-ev-') !== 0
                && at.name !== 'data-handler') {
              dataset[at.name.slice(5)] = at.value;
            }
          });
          fn.call(inst, {
            type: evt,
            detail: { value: node.value },
            currentTarget: { dataset: dataset, id: node.id },
            target: { dataset: dataset, id: node.id }
          });
        });
      });
    });
  }

  function makeElement(html, inst) {
    var holder = document.createElement('div');
    holder.innerHTML = html;
    var el = holder.firstElementChild || holder.firstChild;
    if (!el) return null;
    bindEvents(el.nodeType === 1 ? el : holder, inst);
    return el;
  }

  function attrsOf(el, skipValue) {
    var map = {};
    for (var i = 0; i < el.attributes.length; i++) {
      var a = el.attributes[i];
      if (a.name === 'data-ev-bound') continue;                // 运行时内部标记
      if (skipValue && (a.name === 'value')) continue;         // 输入框当前值单独处理
      map[a.name] = a.value;
    }
    return map;
  }

  function applyAttrs(el, want, skipValue) {
    var has = attrsOf(el, skipValue);
    Object.keys(want).forEach(function (name) {
      if (name === 'data-ev-bound') return;
      if (name === 'value') {
        if (el.value !== want[name]) { try { el.value = want[name]; } catch (e) {} }
        return;
      }
      if (has[name] !== want[name]) {
        try { el.setAttribute(name, want[name]); } catch (e) {}
      }
    });
    Object.keys(has).forEach(function (name) {
      if (name === 'value' && skipValue) return;
      if (!(name in want)) el.removeAttribute(name);
    });
  }

  /** 节点的「身份」：优先 wx:key 对应的 data-key，否则用标签 + 类名 + 事件处理器。 */
  function sigOf(node) {
    if (node.nodeType === 3) return '#text';
    var tag = node.nodeName;
    var key = node.getAttribute ? node.getAttribute('data-key') : null;
    if (key) return tag + '|key=' + key;
    var cls = node.getAttribute ? (node.getAttribute('class') || '') : '';
    var handler = node.getAttribute ? (node.getAttribute('data-handler') || '') : '';
    var onClick = node.onclick ? 'onclick' : '';
    return tag + '|' + cls + '|' + handler + '|' + onClick;
  }

  /**
   * 用新的 HTML 片段更新容器内容。
   *
   * 两个要点（都在实测里踩过坑）：
   * 1. **不能整段 innerHTML 重建**：页面在 bindinput 里会 setData，
   *    重建会销毁正在输入的 input，表现成「打一个字就丢焦点」。
   * 2. **不能只按序号对比**：WXML 里 wx:if / wx:for 会让节点数量变化
   *    （例如「先告诉小科你想学什么吧」这行提示消失时），
   *    按序号硬配会把节点错配、插入错位置，页面直接失灵。
   *    因此这里用「身份 + 序列匹配」对齐新旧节点。
   */
  function reconcile(oldNodes, newNodes) {
    var pairs = oldNodes.map(function () { return null; });
    var used = newNodes.map(function () { return false; });
    var start = 0;
    // 1) 先吃掉前后完全匹配的部分（绝大多数更新都走到这里）
    while (start < oldNodes.length && start < newNodes.length
           && sigOf(oldNodes[start]) === sigOf(newNodes[start])) {
      pairs[start] = start;
      used[start] = true;
      start++;
    }
    var oi = oldNodes.length - 1;
    var ni = newNodes.length - 1;
    while (oi >= start && ni >= start && sigOf(oldNodes[oi]) === sigOf(newNodes[ni])) {
      pairs[oi] = ni;
      used[ni] = true;
      oi--;
      ni--;
    }
    // 2) 中间部分用身份做贪心匹配，并**强制保持前后顺序**：
    //    一旦允许交叉配对，后面的插入锚点就会错位，导致兄弟节点被吞掉。
    var lastJ = start - 1;
    for (var i = start; i <= oi; i++) {
      var sig = sigOf(oldNodes[i]);
      for (var j = lastJ + 1; j <= ni; j++) {
        if (!used[j] && sigOf(newNodes[j]) === sig) {
          pairs[i] = j;
          used[j] = true;
          lastJ = j;
          break;
        }
      }
    }
    return pairs;
  }

  function patchChildren(container, html, inst) {
    var holder = document.createElement('div');
    holder.innerHTML = html;
    var newNodes = Array.prototype.slice.call(holder.childNodes);
    var oldNodes = Array.prototype.slice.call(container.childNodes);
    var pairs = reconcile(oldNodes, newNodes);

    // 第一遍：删掉在新片段里找不到对应身份的旧节点
    for (var i = 0; i < oldNodes.length; i++) {
      if (pairs[i] === null && oldNodes[i].parentNode === container) {
        container.removeChild(oldNodes[i]);
      }
    }

    // 第二遍：按新片段的顺序走一遍，缺的插进去、错位的挪位置、其余就地打补丁。
    // 锚点用「下一个已经挂在容器里的新节点」，这样插入位置一定正确
    // （之前用旧节点数组当锚点，插入会和删除互相干扰，把兄弟节点吞掉）。
    for (var k = 0; k < newNodes.length; k++) {
      var node = newNodes[k];
      if (node.parentNode === container) continue;

      var anchor = null;
      for (var t = k + 1; t < newNodes.length; t++) {
        if (newNodes[t].parentNode === container) { anchor = newNodes[t]; break; }
      }

      // 找到与它配对的旧节点
      var matched = null;
      for (var o = 0; o < oldNodes.length; o++) {
        if (pairs[o] === k && oldNodes[o].parentNode === container) { matched = oldNodes[o]; break; }
      }

      if (matched && sigOf(matched) === sigOf(node)) {
        if (matched.nextSibling !== anchor && matched !== anchor) {
          container.insertBefore(matched, anchor);
        }
        patchNode(container, matched, node, inst);
      } else {
        if (matched) container.removeChild(matched);
        container.insertBefore(node, anchor);
        bindEvents(node.nodeType === 1 ? node : container, inst);
      }
    }
  }

  function patchNode(parent, oldNode, newNode, inst) {
    if (oldNode.nodeType !== newNode.nodeType || oldNode.nodeName !== newNode.nodeName) {
      var fresh = newNode;
      parent.replaceChild(fresh, oldNode);
      bindEvents(fresh.nodeType === 1 ? fresh : parent, inst);
      return;
    }
    if (oldNode.nodeType === 3) {                 // 文本节点
      if (oldNode.nodeValue !== newNode.nodeValue) oldNode.nodeValue = newNode.nodeValue;
      return;
    }

    var el = oldNode;
    var isField = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA';
    var want = {};
    for (var i = 0; i < newNode.attributes.length; i++) {
      var a = newNode.attributes[i];
      want[a.name] = a.value;
    }
    var focused = el === document.activeElement;
    if (focused && want.class && want.class.indexOf(' focus') === -1) {
      want.class = want.class + ' focus';        // 聚焦态是运行时加的，比较时忽略
    }
    applyAttrs(el, want, isField);
    if (isField) return;                          // 输入框没有子节点

    var oldKids = Array.prototype.slice.call(el.childNodes);
    var newKids = Array.prototype.slice.call(newNode.childNodes);
    for (var j = 0; j < Math.max(oldKids.length, newKids.length); j++) {
      var ok = oldKids[j];
      var nk = newKids[j];
      if (ok && nk) {
        patchNode(el, ok, nk, inst);
      } else if (nk) {
        el.appendChild(nk);
        bindEvents(nk.nodeType === 1 ? nk : el, inst);
      } else if (ok) {
        el.removeChild(ok);
      }
    }
  }

  function render(inst) {
    var src = pageSources()[inst.__key];
    if (!src) return;
    if (!inst.__tree) inst.__tree = parseWxml(src);
    var scope = Object.create(null);
    for (var k in inst.data) scope[k] = inst.data[k];
    inst.__scope = scope;

    var host = document.getElementById('mp-view');
    patchChildren(host, renderList(inst.__tree.children, scope), inst);
    bindEvents(host, inst);
  }

  /* ---------------- 页面注册与挂载 ---------------- */
  // 注意：页面源与路由表由生成脚本在其后的 <script> 里挂到 window 上，
  // 因此这里**不能在启动时缓存**，必须在每次使用时现读，
  // 否则会拿到空对象（这个坑踩过一次了）。
  function pageSources() { return window.__kepuPageSources || {}; }
  var instances = {};
  var stack = ['pages/index'];

  function keyOf(url) {
    var p = String(url || '').split('?')[0].replace(/^\//, '');
    return p.replace(/\/index$/, '');
  }
  function queryOf(url) {
    var q = {};
    var i = String(url || '').indexOf('?');
    if (i === -1) return q;
    String(url).slice(i + 1).split('&').forEach(function (kv) {
      if (!kv) return;
      var pair = kv.split('=');
      q[decodeURIComponent(pair[0])] = decodeURIComponent(pair[1] || '');
    });
    return q;
  }
  function setTitle(t) {
    var el = document.getElementById('mp-title');
    if (el) el.textContent = t || '科普闯关';
  }

  function instantiate(key, options) {
    var inst = {};
    inst.__key = key;
    inst.__options = options;
    inst.data = JSON.parse(JSON.stringify(options.data || {}));

    /**
     * 支持小程序 setData 的「路径写法」。
     *
     * 页面里会用 this.setData({ 'questions[0].expanded': true }) 这种写法，
     * 如果不解析路径、直接当普通键名塞进去，界面就永远不会更新
     * （错题本展开讲解点了没反应，就是这么来的）。
     */
    function setByPath(path, value) {
      var keys = String(path).replace(/\[(\d+)\]/g, '.$1').split('.');
      var target = inst.data;
      for (var i = 0; i < keys.length - 1; i++) {
        var k = keys[i];
        if (target[k] === undefined || target[k] === null || typeof target[k] !== 'object') {
          target[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
        }
        target = target[k];
      }
      target[keys[keys.length - 1]] = value;
    }

    inst.setData = function (patch, cb) {
      for (var k in patch) {
        if (k.indexOf('.') !== -1 || k.indexOf('[') !== -1) {
          setByPath(k, patch[k]);
        } else {
          inst.data[k] = patch[k];
        }
      }
      render(inst);
      if (cb) cb();
    };
    // 函数绑到实例上；其余非 data 字段（如 askTimers / questionStates 这类
    // 页面自定义状态）也要原样带上，否则 this.askTimers.push 会报
    // "Cannot read properties of undefined"。
    Object.keys(options).forEach(function (name) {
      if (name === 'data' || name === 'properties') return;
      if (typeof options[name] === 'function') inst[name] = options[name].bind(inst);
      else inst[name] = JSON.parse(JSON.stringify(options[name]));
    });
    if (!inst.data) inst.data = {};
    return inst;
  }

  function show(key, query) {
    var host = document.getElementById('mp-view');
    var tabKeys = ['pages/index', 'pages/wrong', 'pages/knowledge', 'pages/profile'];
    Array.prototype.forEach.call(document.querySelectorAll('.mp-tab'), function (t) {
      t.classList.toggle('on', t.getAttribute('data-page') === key);
    });
    setTitle(((window.__kepuPageMeta || {})[key] || {}).title || '科普闯关');
    document.getElementById('mp-tabbar').style.visibility =
      (tabKeys.indexOf(key) !== -1) ? 'visible' : 'hidden';

    var inst = instances[key];
    if (!inst) {
      var opts = window.__kepuPages[key];   // 注册时由 Page() 收集的真实页面配置
      if (!opts) {
        host.innerHTML = '<div class="page-root"><div class="empty">这个页面还没接进来</div></div>';
        return;
      }
      inst = instantiate(key, opts);
      instances[key] = inst;
      host.innerHTML = '';                  // 换页时清空，避免残留上一页节点
      if (inst.onLoad) inst.onLoad(query || {});
      render(inst);
      if (inst.onShow) inst.onShow();
      if (inst.onReady) inst.onReady();
    } else {
      if (query && Object.keys(query).length && inst.onLoad) inst.onLoad(query);
      render(inst);
      if (inst.onShow) inst.onShow();
    }
  }

  var router = {
    push: function (url) { stack.push(keyOf(url)); show(keyOf(url), queryOf(url)); },
    replace: function (url) { show(keyOf(url), queryOf(url)); },
    reset: function (url) {
      Object.keys(instances).forEach(function (k) { delete instances[k]; });
      stack = [keyOf(url)];
      show(keyOf(url), queryOf(url));
    },
    back: function () {
      stack.pop();
      show(stack[stack.length - 1] || 'pages/index', {});
    }
  };

  /* ---------------- App / Page / Component ---------------- */
  window.__kepuPages = window.__kepuPages || {};
  window.App = function (options) {
    var app = options || {};
    app.globalData = app.globalData || {};
    window.__kepuApp = app;
  };
  window.getApp = function () { return window.__kepuApp; };
  window.Page = function (options) { window.__kepuCurrentPage = options; };
  window.Component = function (options) { window.__kepuCurrentComponent = options; };

  /* ---------------- 调试钩子（便于定位渲染问题，正常使用无影响） ---------------- */
  window.__kepuDebug = {
    parseWxml: parseWxml, renderList: renderList, evalExpr: evalExpr,
    directives: directives, attrValue: attrValue, instances: instances,
    patchChildren: patchChildren, router: router,
    sigOf: sigOf, reconcile: reconcile
  };

  /* ---------------- 启动 ---------------- */
  window.__kepuBoot = function () {
    if (window.__kepuApp && window.__kepuApp.onLaunch) window.__kepuApp.onLaunch();
    var tabbar = document.getElementById('mp-tabbar');
    var list = window.__kepuTabBar || [];
    list.forEach(function (item) {
      var btn = document.createElement('div');
      btn.className = 'mp-tab';
      btn.setAttribute('data-page', item.pagePath.replace(/\/index$/, ''));
      btn.textContent = item.text;
      btn.onclick = function () { router.replace('/' + item.pagePath); };
      tabbar.appendChild(btn);
    });
    show('pages/index', {});
  };
})();
