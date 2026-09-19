/**
 * 科普闯关系统 · 网页版公共脚本
 *
 * 包含三块：
 *   1. api    —— 统一请求封装（自动带 JWT、统一拆包、错误提示）
 *   2. sound  —— 纯代码合成的音效（WebAudio，不引入音频文件）
 *   3. 工具函数 —— 转义、时间、选项文案、等级换算、吉祥物渲染
 *
 * 与小程序端共用同一套后端接口，路径与响应体完全一致。
 */
(function (global) {
  'use strict';

  /* ================= 1. 请求封装 ================= */
  // 与后端同源时用相对路径即可；如果前端被单独部署，改这里就行
  var API_BASE = global.__KEPU_API_BASE__ || '/api/v1';
  var TOKEN_KEY = 'kepu_token';
  var USER_KEY = 'kepu_user';

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
  }
  function getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (e) { return null; }
  }
  function saveSession(token, user) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch (e) {}
  }
  function clearSession() {
    try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch (e) {}
  }

  function request(method, path, body, options) {
    var opts = options || {};
    var headers = { 'Accept': 'application/json' };
    var token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;
    var init = { method: method, headers: headers };
    if (body !== undefined && body !== null) {
      headers['Content-Type'] = 'application/json; charset=utf-8';
      init.body = JSON.stringify(body);
    }
    return fetch(API_BASE + path, init).then(function (resp) {
      return resp.text().then(function (text) {
        var data;
        try { data = JSON.parse(text); } catch (e) { data = { code: -1, message: '返回内容看不懂' }; }
        if (resp.ok && data.code === 0) return data.data;
        var err = new Error(data.message || '这一步没走通，再试一次吧');
        err.code = data.code;
        err.status = resp.status;
        if (resp.status === 401) clearSession();
        if (!opts.silent) UI.toast(err.message);
        throw err;
      });
    }).catch(function (e) {
      if (e && e.code !== undefined) throw e;
      var err = new Error('连不上服务器，确认后端已经启动');
      err.code = -1;
      if (!opts.silent) UI.toast(err.message);
      throw err;
    });
  }

  var api = {
    get: function (p, o) { return request('GET', p, null, o); },
    post: function (p, b, o) { return request('POST', p, b, o); },
    put: function (p, b, o) { return request('PUT', p, b, o); },
    del: function (p, o) { return request('DELETE', p, null, o); },
    /** 带请求体的删除（题干里有中文与问号时比塞进 URL 稳） */
    delBody: function (p, b, o) { return request('DELETE', p, b, o); },
    /** 上传知识库资料：以 multipart 形式发送（服务端接口就是按文件接收的） */
    uploadText: function (filename, text) {
      var form = new FormData();
      form.append('file', new Blob([text], { type: 'text/plain;charset=utf-8' }), filename);
      var headers = {};
      var token = getToken();
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(API_BASE + '/knowledge/documents', { method: 'POST', headers: headers, body: form })
        .then(function (resp) {
          return resp.text().then(function (t) {
            var data;
            try { data = JSON.parse(t); } catch (e) { data = { code: -1, message: '返回内容看不懂' }; }
            if (resp.ok && data.code === 0) return data.data;
            var err = new Error(data.message || '这份资料没读进去');
            err.code = data.code;
            UI.toast(err.message);
            throw err;
          });
        });
    },
    getToken: getToken,
    getUser: getUser,
    saveSession: saveSession,
    clearSession: clearSession,
    base: API_BASE,
    /** 学生注册 */
    register: function (username, password, nickname, grade) {
      return request('POST', '/user/register',
                     { username: username, password: password, nickname: nickname, grade: grade });
    },
    /** 学生登录（账号 + 口令） */
    loginWithPassword: function (username, password) {
      return request('POST', '/user/login', { username: username, password: password });
    },
    /** 游客体验：不注册先玩，数据暂存在临时账号上 */
    loginAsGuest: function (grade) {
      return request('POST', '/user/guest', { grade: grade }, { silent: true });
    },
    /** 把游客期间的数据并到当前登录账号，避免「先试后注册」白玩 */
    mergeGuest: function (guestToken) {
      return request('POST', '/user/merge-guest', { guest_token: guestToken },
                     { silent: true });
    },
    /**
     * 管理员登录：入口页上直接放了一个管理员页签，不必先手敲 /admin/ 地址。
     * 管理端登录接口在 /admin/login，用的是 X-Admin-Token，与学生 JWT 互不影响；
     * 拿到 token 后按管理端的约定存进 sessionStorage，然后跳 /admin/ 即可直接进。
     */
    adminLogin: function (username, password) {
      return fetch(API_BASE + '/admin/login', {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ username: username, password: password })
      }).then(function (resp) {
        return resp.text().then(function (t) {
          var data;
          try { data = JSON.parse(t); } catch (e) { data = { code: -1, message: '返回内容看不懂' }; }
          if (resp.ok && data.code === 0) {
            var d = data.data || {};
            try {
              if (d.token) sessionStorage.setItem('kepu_admin_token', d.token);
              if (d.admin && d.admin.username) {
                sessionStorage.setItem('kepu_admin_name', d.admin.username);
              }
            } catch (e) {}
            return d;
          }
          throw new Error(data.message || '管理员账号或口令不对');
        });
      }).catch(function (e) {
        if (e instanceof Error && e.message && e.message !== 'Failed to fetch') throw e;
        throw new Error('连不上服务器，确认后端已经启动');
      });
    }
  };

  /* ================= 2. 界面反馈 ================= */
  var UI = {
    toast: function (message) {
      var el = document.getElementById('toast');
      if (!el) return;
      el.textContent = message || '';
      el.classList.add('show');
      clearTimeout(el._t);
      el._t = setTimeout(function () { el.classList.remove('show'); }, 2200);
    },
    loading: function (on, text) {
      var el = document.getElementById('loading');
      if (!el) return;
      if (text) document.getElementById('loading-text').textContent = text;
      el.classList[on ? 'add' : 'remove']('show');
    },
    confirm: function (opt) {
      return new Promise(function (resolve) {
        var el = document.getElementById('modal');
        document.getElementById('modal-title').textContent = opt.title || '';
        document.getElementById('modal-content').textContent = opt.content || '';
        var ok = document.getElementById('modal-ok');
        var no = document.getElementById('modal-cancel');
        ok.textContent = opt.confirmText || '确定';
        no.textContent = opt.cancelText || '取消';
        ok.style.color = opt.confirmColor || 'var(--c-primary-deep)';
        el.classList.add('show');
        ok.onclick = function () { el.classList.remove('show'); resolve(true); };
        no.onclick = function () { el.classList.remove('show'); resolve(false); };
      });
    }
  };

  /* ================= 3. 音效（WebAudio 合成，不用音频文件） ================= */
  var sound = (function () {
    var ctx = null, failed = false;
    function enabled() {
      try {
        var v = localStorage.getItem('kepu_sound');
        return v === null ? true : v === '1';
      } catch (e) { return true; }
    }
    function setEnabled(on) {
      try { localStorage.setItem('kepu_sound', on ? '1' : '0'); } catch (e) {}
    }
    function context() {
      if (ctx || failed) return ctx;
      var Ctor = global.AudioContext || global.webkitAudioContext;
      if (!Ctor) { failed = true; return null; }
      try { ctx = new Ctor(); } catch (e) { failed = true; ctx = null; }
      return ctx;
    }
    function beep(freq, start, dur, gain, type) {
      var ac = context();
      if (!ac) return;
      try {
        if (ac.state === 'suspended') ac.resume();
        var t0 = ac.currentTime + (start || 0);
        var osc = ac.createOscillator();
        var amp = ac.createGain();
        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, t0);
        amp.gain.setValueAtTime(0.0001, t0);
        amp.gain.exponentialRampToValueAtTime(gain || 0.16, t0 + 0.012);
        amp.gain.exponentialRampToValueAtTime(0.0001, t0 + (dur || 0.18));
        osc.connect(amp);
        amp.connect(ac.destination);
        osc.start(t0);
        osc.stop(t0 + (dur || 0.18) + 0.03);
      } catch (e) { /* 声音是锦上添花，出错也不能影响答题 */ }
    }
    return {
      enabled: enabled,
      setEnabled: setEnabled,
      tap: function () { if (enabled()) beep(660, 0, 0.06, 0.07, 'triangle'); },
      correct: function (combo) {
        if (!enabled()) return;
        var step = Math.max(0, Math.min(4, (combo || 1) - 1));
        var base = 660 * Math.pow(1.122, step);
        beep(base, 0, 0.12, 0.16);
        beep(base * 1.25, 0.09, 0.18, 0.14);
      },
      combo: function (level) {
        if (!enabled() || !level || level < 3) return;
        beep(1200, 0, 0.09, 0.1);
        beep(1600, 0.07, 0.12, 0.09);
      },
      wrong: function () {
        if (!enabled()) return;
        beep(392, 0, 0.16, 0.12, 'triangle');
        beep(311, 0.12, 0.22, 0.1, 'triangle');
      },
      win: function () {
        if (!enabled()) return;
        var notes = [523.25, 659.25, 783.99, 1046.5];
        for (var i = 0; i < notes.length; i++) beep(notes[i], i * 0.11, 0.26, 0.15);
      }
    };
  })();

  /* ================= 4. 工具函数 ================= */
  var util = {
    esc: function (s) {
      return String(s === undefined || s === null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },
    /** 「2026-09-19 17:11:51」→「09-19 17:11」 */
    shortTime: function (v) {
      var t = v ? String(v) : '';
      return t.length >= 16 ? t.substring(5, 16) : t;
    },
    /** 选项下标 →「B. 木星」；下标不合法就返回空串 */
    optionText: function (options, index) {
      var list = options || [];
      var i = Number(index);
      if (isNaN(i) || i < 0 || i >= list.length) return '';
      return 'ABCDEFGH'.charAt(i) + '. ' + list[i];
    },
    gradeText: function (g) {
      return { primary_low: '小学低年级', primary_high: '小学高年级', junior: '初中' }[g] || '小学高年级';
    },
    sourceText: function (s) {
      return { ai: '由 AI 生成', bank: '来自题库', wrongbook: '错题重练' }[s] || '来自题库';
    },
    /** 毫秒 →「1 分 20 秒」 */
    durationText: function (ms) {
      var sec = Math.max(0, Math.round((Number(ms) || 0) / 1000));
      var m = Math.floor(sec / 60);
      var s = sec % 60;
      return m ? (m + ' 分 ' + s + ' 秒') : (s + ' 秒');
    },
    sizeText: function (bytes) {
      var n = Number(bytes) || 0;
      if (n < 1024) return n + ' B';
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      return (n / 1024 / 1024).toFixed(1) + ' MB';
    },
    /** 经验值 → 等级信息：每 50 点一级，给孩子一个一直够得着的短期目标 */
    levelInfo: function (totalXp) {
      var unit = 50;
      var xp = Math.max(0, Number(totalXp) || 0);
      var level = Math.floor(xp / unit) + 1;
      var inLevel = xp % unit;
      return {
        level: level,
        inLevel: inLevel,
        need: unit,
        remain: unit - inLevel,
        percent: Math.round((inLevel / unit) * 100)
      };
    },
    levelTitle: function (level) {
      var titles = ['科学小新芽', '好奇心学徒', '问题小侦探', '实验小助手',
                    '知识小达人', '探索小队长', '科学小博士'];
      return titles[Math.max(0, Math.min(titles.length - 1, (Number(level) || 1) - 1))];
    },
    /** 吉祥物「小科」：纯 CSS 绘制，六种状态 */
    mascot: function (state, size, caption) {
      var caps = {
        idle: '我是小科，陪你一起探索科学',
        thinking: '小科正在思考…',
        correct: '答对啦，你真棒！',
        wrong: '差一点点，再看看解析？',
        encourage: '别着急，慢慢来～',
        win: '这一关通过啦！'
      };
      var st = state || 'idle';
      var sz = size || 'md';
      var text = (caption && String(caption).length) ? caption : (caps[st] || caps.idle);
      return '<div class="mascot mascot-' + sz + ' mascot-' + util.esc(st) + '">'
        + '<div class="mascot-stage">'
        + (st === 'thinking' ? '<div class="mascot-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>' : '')
        + '<div class="mascot-body"><div class="ear ear-left"></div><div class="ear ear-right"></div>'
        + '<div class="mascot-head"><div class="mascot-face"><div class="mascot-eyes">'
        + '<div class="eye eye-left"></div><div class="eye eye-right"></div></div>'
        + '<div class="mouth"></div><div class="cheek cheek-left"></div><div class="cheek cheek-right"></div>'
        + '</div></div></div></div>'
        + '<div class="mascot-caption">' + util.esc(text) + '</div></div>';
    },
    /** 主题快捷入口 */
    topicChips: [
      { label: '天文', emoji: '🪐', topic: '太阳系' },
      { label: '地理', emoji: '🌏', topic: '地球的构造' },
      { label: '生物', emoji: '🌿', topic: '植物的光合作用' },
      { label: '物理', emoji: '🧲', topic: '力和运动' },
      { label: '化学', emoji: '⚗️', topic: '水的三态变化' },
      { label: '科技', emoji: '🤖', topic: '人工智能' }
    ],
    /** 等待出题时轮播的科普小知识：把等待时间变成学习时间 */
    scienceFacts: [
      '太阳表面约 5500℃，核心温度超过 1500 万℃。',
      '蜂蜜几乎不会变质，古埃及墓里找到过还能吃的蜂蜜。',
      '彩虹是阳光在水滴里折射又反射形成的，所以它永远是圆的。',
      '章鱼有三颗心脏，游泳时主心脏会停下来，所以它更爱爬着走。',
      '竹子是世界上长得最快的植物之一，一天最多能长高近一米。',
      '月亮每年远离地球约 3.8 厘米。',
      '闪电温度能到 3 万℃，比太阳表面还热好几倍。',
      '水熊虫小到看不见，却能在太空里活下来。',
      '人的鼻子大约能分辨一万亿种气味。',
      '香蕉其实是有小种子的浆果。'
    ]
  };

  global.KEPU = { api: api, UI: UI, sound: sound, util: util };
})(window);
