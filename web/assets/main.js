/**
 * 科普闯关系统 · 网页版主程序
 *
 * 单页应用：hash 路由 + 六个页面（去闯关 / 答题闯关 / 复盘报告 / 错题本 / 知识库 / 我的）。
 * 交互与文案沿用小程序端的规范：全篇不出现「错误 / 失败 / 排名」，
 * 答错用暖橙、连对给奖励、倒计时到点只提醒不判负。
 *
 * 所有数据来自同一套后端接口，没有本地假数据。
 */
(function () {
  'use strict';

  var api = KEPU.api;
  var util = KEPU.util;
  var sound = KEPU.sound;
  var UI = KEPU.UI;
  var view = document.getElementById('view');

  /* ================= 全局状态 ================= */
  var state = {
    grades: [],
    grade: localStorage.getItem('kepu_grade') || 'primary_high',
    topic: '',
    docId: '',
    docName: '',
    lastQuiz: null,
    lastResult: null,
    totalXp: 0,
    // 想显示入口页的哪个页签：'login' / 'register' / 'admin'。
    // 必须记在 state 里，因为 `location.hash = '#/login'` 会触发 hashchange，
    // 由 routes.login 重新渲染一次；不记住的话那次重渲染会把页签打回「登录」，
    // 于是游客点「注册以保存记录」结果停在登录页、页面上根本没有注册才有的昵称输入框。
    loginMode: 'login'
  };

  function gradeLabel(g) {
    var list = state.grades || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].value === (g || state.grade)) return list[i].short || list[i].label;
    }
    return util.gradeText(g || state.grade);
  }

  function setGrade(g) {
    state.grade = g;
    try { localStorage.setItem('kepu_grade', g); } catch (e) {}
    renderTop();
  }

  function renderTop() {
    var info = util.levelInfo(state.totalXp);
    document.getElementById('lv-chip').textContent = 'Lv.' + info.level + ' ' + util.levelTitle(info.level);
    var user = api.getUser();
    var btn = document.getElementById('auth-switch');
    if (!api.getToken()) {
      document.getElementById('who').textContent = '未登录';
      btn.hidden = false;
      btn.textContent = '登录 / 注册';
      btn.onclick = function () { location.hash = '#/login'; renderLogin(); };
      return;
    }
    var name = (user && user.nickname) || '小科学家';
    document.getElementById('who').textContent = name + (state.isGuest ? '（游客）' : '');
    btn.hidden = false;
    btn.textContent = state.isGuest ? '注册以保存记录' : '退出';
    btn.onclick = function () {
      if (state.isGuest) { location.hash = '#/login'; renderLogin('register'); return; }
      UI.confirm({ title: '要退出吗？', content: '退出后错题本和经验值需要重新登录才能看到。',
                   confirmText: '退出', cancelText: '再看看' })
        .then(function (yes) {
          if (!yes) return;
          api.clearSession();
          state.totalXp = 0;
          state.isGuest = false;
          renderTop();
          location.hash = '#/login';
          renderLogin();
        });
    };
  }

  function flash(text) {
    var el = document.getElementById('flash');
    el.textContent = text;
    el.classList.remove('show');
    void el.offsetWidth;          // 强制重排，让动画能重复触发
    el.classList.add('show');
    setTimeout(function () { el.classList.remove('show'); }, 1150);
  }

  /* ================= 启动 ================= */
  /** 打开方式不对时给出明确提示，而不是静默无反应。
   *
   * 最常见的错误用法是双击 web/index.html（file:// 协议）打开：
   * 这种页面去请求 http://127.0.0.1:8000 会被浏览器跨域拦截，
   * 表现就是「按钮点了没反应、也不报错」，非常难自行诊断。
   */
  function checkOrigin() {
    if (location.protocol === 'file:') {
      view.innerHTML = '<div class="card" style="max-width:640px;margin:60px auto">'
        + '<h2 class="h2">这个页面要用服务端地址打开</h2>'
        + '<div class="body" style="margin-top:12px">你现在是直接双击文件打开的（<code>file://</code> 协议），'
        + '浏览器不允许这样的页面调用接口，所以按钮点了会没有反应。</div>'
        + '<div class="card" style="background:#F7FBFF;margin-top:16px">'
        + '<div class="h3">正确的打开方式</div>'
        + '<div class="body" style="margin-top:8px">1. 在 <code>backend</code> 目录执行：<br>'
        + '<code>python -m uvicorn app.main:app --port 8000</code><br>'
        + '（或者双击 <code>scripts\\run_web.cmd</code>）</div>'
        + '<div class="body" style="margin-top:8px">2. 然后浏览器打开：'
        + '<b>http://127.0.0.1:8000/app/</b></div>'
        + '</div></div>';
      return false;
    }
    return true;
  }

  function boot() {
    if (!checkOrigin()) {
      return;
    }
    // 先把游客 Token 记下来：注册/登录后要把这段时间的数据并过去，否则孩子会觉得白玩。
    var guestToken = api.getToken();

    api.get('/grades', { silent: true })
      .then(function (data) {
        state.grades = (data && data.grades) || [];
        if (!state.grades.some(function (g) { return g.value === state.grade; })) {
          state.grade = (data && data.default) || 'primary_high';
        }
      })
      .catch(function () {
        state.grades = [
          { value: 'primary_low', short: '小学低年级' },
          { value: 'primary_high', short: '小学高年级' },
          { value: 'junior', short: '初中' }
        ];
      });

    // 路由与登录态：没登录先去登录页（但「去闯关」允许以游客身份试玩）
    window.addEventListener('hashchange', route);

    if (!api.getToken()) {
      renderLogin();
      return;
    }
    state.guestToken = guestToken;
    reloadProfile().then(function () {
      route();
    });
  }

  /** 拉一次个人资料，把等级、身份显示刷新 */
  function reloadProfile() {
    return api.get('/user/profile', { silent: true })
      .then(function (d) {
        state.totalXp = (d.user && d.user.total_xp) || 0;
        state.isGuest = !!d.is_guest;
        renderTop();
      })
      .catch(function () {
        // Token 失效：退回登录页
        api.clearSession();
        renderTop();
        if ((location.hash || '').indexOf('#/login') === -1) {
          renderLogin();
        }
      });
  }

  /* ================= 登录 / 注册 =================
   * 之前是启动时静默建一个游客账号，结果是：
   *   1) 用户根本不知道有「账号」这回事，答错题进了哪个账号也无从判断；
   *   2) 直接打开错题本时静默登录还没完成 → 接口 401 → 页面提示「要登录才能用」，
   *      而且不会自动重试，看起来就是「答错了但错题本一直空着」。
   * 现在改成显式的注册 / 登录页，游客也能先试玩，注册后数据自动并过来。
   */
  function renderLogin(mode) {
    var isRegister = mode === 'register';
    var isAdmin = mode === 'admin';
    state.loginMode = isAdmin ? 'admin' : (isRegister ? 'register' : 'login');

    var tabs = '<div class="row" style="gap:10px;margin-bottom:18px">'
      + '  <button id="tab-login" class="btn ' + (!isRegister && !isAdmin ? 'btn-primary' : 'btn-ghost') + ' grow">学生登录</button>'
      + '  <button id="tab-register" class="btn ' + (isRegister ? 'btn-primary' : 'btn-ghost') + ' grow">学生注册</button>'
      + '  <button id="tab-admin" class="btn ' + (isAdmin ? 'btn-primary' : 'btn-ghost') + ' grow">管理员</button>'
      + '</div>';

    if (isAdmin) {
      view.innerHTML = '<div style="max-width:460px;margin:28px auto 0">'
        + '<div class="card" style="text-align:center">'
        + util.mascot('idle', 'lg', '小科把管理端的门也搬到这儿啦')
        + '</div>'
        + '<div class="card">'
        + tabs
        + '  <div class="field"><label>管理员账号</label>'
        + '    <input id="auth-user" class="input" placeholder="管理员登录名" value="' + util.esc(state.lastAdmin || '') + '"></div>'
        + '  <div class="field"><label>管理员口令</label>'
        + '    <input id="auth-pass" class="input" type="password" placeholder="6~32 位；首次部署的默认口令见 README"></div>'
        + '  <button id="auth-submit" class="btn btn-primary btn-block" style="margin-top:6px">进入管理端</button>'
        + '  <div class="muted" style="margin-top:12px;text-align:center">'
        + '    这里看的是每个学生的闯关记录与错题分类，也能维护题库；'
        + '    登录后直接进 <a href="/admin/">/admin/</a>。'
        + '    口令在 config.py / 环境变量里改，正式部署前请务必换掉默认值。</div>'
        + '</div>'
        + '</div>';

      document.getElementById('tab-login').onclick = function () { renderLogin('login'); };
      document.getElementById('tab-register').onclick = function () { renderLogin('register'); };
      document.getElementById('tab-admin').onclick = function () { renderLogin('admin'); };
      document.getElementById('auth-submit').onclick = function () {
        var username = (document.getElementById('auth-user').value || '').trim();
        var password = document.getElementById('auth-pass').value || '';
        if (!username) { UI.toast('填一下管理员账号'); return; }
        if (!password) { UI.toast('填一下管理员口令'); return; }
        state.lastAdmin = username;
        UI.loading(true, '小科正在核对管理员身份…');
        api.adminLogin(username, password)
          .then(function () {
            UI.loading(false, '');
            UI.toast('身份核对通过，正在打开管理端…');
            setTimeout(function () { location.href = '/admin/'; }, 600);
          })
          .catch(function (err) {
            UI.loading(false);
            UI.toast((err && err.message) || '没进去，检查一下账号口令');
          });
      };
      return;
    }

    view.innerHTML = '<div style="max-width:460px;margin:28px auto 0">'
      + '<div class="card" style="text-align:center">'
      + util.mascot('idle', 'lg', '我是小科，先报个到吧')
      + '</div>'
      + '<div class="card">'
      + tabs
      + '  <div class="field"><label>登录名</label>'
      + '    <input id="auth-user" class="input" placeholder="3~20 位字母、数字或下划线，例如 xiaoming" value="' + util.esc(state.lastUsername || '') + '"></div>'
      + '  <div class="field"><label>口令</label>'
      + '    <input id="auth-pass" class="input" type="password" placeholder="6~32 位"></div>'
      + (isRegister
        ? '  <div class="field"><label>昵称（可选）</label>'
          + '    <input id="auth-nick" class="input" placeholder="小科怎么称呼你"></div>'
        : '')
      + '  <div class="field"><label>学段</label>'
      + '    <select id="auth-grade" class="input">'
      + ['primary_low|小学低年级', 'primary_high|小学高年级', 'junior|初中'].map(function (g) {
          var parts = g.split('|');
          return '<option value="' + parts[0] + '"'
            + (parts[0] === state.grade ? ' selected' : '') + '>' + parts[1] + '</option>';
        }).join('')
      + '    </select></div>'
      + '  <button id="auth-submit" class="btn btn-primary btn-block" style="margin-top:6px">'
      + (isRegister ? '注册并开始闯关' : '登录') + '</button>'
      + '  <button id="auth-guest" class="btn btn-ghost btn-block" style="margin-top:10px">先逛逛（游客体验）</button>'
      + '  <div class="muted" style="margin-top:12px;text-align:center">'
      + '    游客也能答题，错题本和经验值先记在这个临时身份上——换设备或清掉浏览器记录就找不回来了；'
      + '注册后小科会把它们并到你的账号里。</div>'
      + '</div>'
      + '<div class="card" style="text-align:left">'
      + '  <div class="h3" style="margin-bottom:8px">老师 / 管理员</div>'
      + '  <div class="muted">在上面点「管理员」页签就能直接登录，进去可以看每个学生的答题记录、维护题库。</div>'
      + '</div>'
      + '</div>';

    document.getElementById('tab-login').onclick = function () { renderLogin('login'); };
    document.getElementById('tab-register').onclick = function () { renderLogin('register'); };
    document.getElementById('tab-admin').onclick = function () { renderLogin('admin'); };
    document.getElementById('auth-guest').onclick = function () {
      UI.loading(true, '小科正在准备…');
      api.loginAsGuest(state.grade)
        .then(function (data) {
          UI.loading(false);
          api.saveSession(data.token, data.user);
          state.guestToken = data.token;
          state.totalXp = 0;
          return reloadProfile();
        })
        .then(function () {
          location.hash = '#/home';
          route();
        })
        .catch(function () { UI.loading(false); });
    };
    document.getElementById('auth-submit').onclick = function () {
      var username = (document.getElementById('auth-user').value || '').trim();
      var password = document.getElementById('auth-pass').value || '';
      var nickEl = document.getElementById('auth-nick');
      var nickname = nickEl ? (nickEl.value || '').trim() : '';
      var grade = document.getElementById('auth-grade').value;
      state.lastUsername = username;
      state.grade = grade;
      try { localStorage.setItem('kepu_grade', grade); } catch (e) {}

      if (!username) { UI.toast('先想一个登录名吧'); return; }
      if (!password) { UI.toast('再设一个口令'); return; }

      var guest = state.guestToken;
      UI.loading(true, isRegister ? '小科正在给你建账号…' : '小科正在核对…');
      var call = isRegister
        ? api.register(username, password, nickname, grade)
        : api.loginWithPassword(username, password);
      call
        .then(function (data) {
          api.saveSession(data.token, data.user);
          state.totalXp = (data.user && data.user.total_xp) || 0;
          // 把游客期间的数据并过来（只在有游客 Token 时做）
          var merge = guest ? api.mergeGuest(guest) : Promise.resolve(null);
          return merge.then(function (res) {
            if (res && res.moved) {
              UI.toast('已把刚才的 ' + res.moved + ' 条记录并到账号里');
            } else {
              UI.toast(isRegister ? '账号建好啦，开始闯关！' : '欢迎回来！');
            }
            return reloadProfile();
          });
        })
        .then(function () {
          UI.loading(false);
          location.hash = '#/home';
          route();
        })
        .catch(function (err) {
          UI.loading(false);
          UI.toast((err && err.message) || '没成功，再试一次吧');
        });
    };
  }

  /* ================= 路由 ================= */
  var routes = {
    login: function () { renderLogin(state.loginMode); },
    home: renderHome,
    quiz: renderQuiz,
    report: renderReport,
    wrong: renderWrong,
    knowledge: renderKnowledge,
    profile: renderProfile
  };

  function route() {
    var hash = (location.hash || '#/home').replace(/^#\//, '');
    var parts = hash.split('?');
    var name = parts[0] || 'home';
    var query = {};
    if (parts[1]) {
      parts[1].split('&').forEach(function (kv) {
        var p = kv.split('=');
        query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || '');
      });
    }
    if (!routes[name]) { name = 'home'; }
    // 需要登录才能用的页面：没登录就直接去登录页。
    // 这样做是为了避免「页面先发请求 → 401 → 显示一句要登录」这种半截状态：
    // 之前错题本就是这样，用户看到的是「答错了但错题本一直是空的」。
    var needLogin = ['wrong', 'profile', 'knowledge'];
    if (needLogin.indexOf(name) !== -1 && !api.getToken()) {
      renderLogin('login');
      return;
    }
    document.querySelectorAll('[data-nav]').forEach(function (a) {
      var on = a.getAttribute('data-nav') === name ||
               (name === 'quiz' || name === 'report') && a.getAttribute('data-nav') === 'home';
      a.classList[on ? 'add' : 'remove']('on');
    });
    window.scrollTo(0, 0);
    routes[name](query);
  }

  /* ================= 1. 去闯关 ================= */
  var askTimer = null;
  var askTick = 0;

  function renderHome() {
    var gs = state.grades.length ? state.grades : [
      { value: 'primary_low', short: '小学低年级', emoji: '🌱' },
      { value: 'primary_high', short: '小学高年级', emoji: '🚀' },
      { value: 'junior', short: '初中', emoji: '🔭' }
    ];
    var emojis = { primary_low: '🌱', primary_high: '🚀', junior: '🔭' };

    var gradeHtml = gs.map(function (g) {
      return '<button class="grade-btn ' + (g.value === state.grade ? 'on' : '') + '" data-grade="' + util.esc(g.value) + '">'
        + '<span class="ge">' + (emojis[g.value] || '📘') + '</span>'
        + '<span class="gn">' + util.esc(g.short || g.label) + '</span></button>';
    }).join('');

    var chipsHtml = util.topicChips.map(function (c) {
      return '<span class="chip" data-topic="' + util.esc(c.topic) + '">' + c.emoji + ' ' + util.esc(c.label) + '</span>';
    }).join('');

    var docCard = state.docId
      ? '<div class="fact-box" style="background:#EAF7FE"><div class="fact-head" style="color:#0288D1">📘 本次将基于《' + util.esc(state.docName) + '》出题</div>'
        + '<div class="muted" style="margin-top:6px">小科会照着这份资料来出题</div></div>'
      : '';

    view.innerHTML = '<div id="home-ask"></div>'
      + '<div id="home-form">'
      + '  <div class="card greet">'
      + '    <div class="greet-text">'
      + '      <h1 class="h1">去闯关</h1>'
      + '      <div class="body">今天想探索什么？你是' + util.esc(gradeLabel()) + '哦</div>'
      + '      <div class="muted">小科负责出题，你只管大胆猜。</div>'
      + '    </div>'
      + util.mascot('idle', 'md', '')
      + '  </div>'
      + '  <div class="card">'
      + '    <div class="card-title">先选一个学段</div>'
      + '    <div class="grade-list">' + gradeHtml + '</div>'
      + '    <div class="muted" style="margin-top:12px">换学段会让题目变难或变简单，随时可以换回来。</div>'
      + '  </div>'
      + '  <div class="card">'
      + '    <div class="card-title">想探索什么主题？</div>'
      + docCard
      + '    <input id="topic" class="input" maxlength="30" placeholder="比如：太阳系、恐龙、彩虹是怎么来的" value="' + util.esc(state.topic) + '">'
      + '    <div class="chips">' + chipsHtml + '</div>'
      + '    <div id="ask-warn" class="muted" style="margin-top:12px">先告诉小科你想学什么吧</div>'
      + '    <button id="start-ask" class="btn btn-primary btn-block off" style="margin-top:14px">开始出题</button>'
      + '  </div>'
      + '</div>';

    view.querySelectorAll('[data-grade]').forEach(function (btn) {
      btn.onclick = function () {
        setGrade(btn.getAttribute('data-grade'));
        renderHome();
      };
    });
    view.querySelectorAll('[data-topic]').forEach(function (chip) {
      chip.onclick = function () {
        var t = chip.getAttribute('data-topic');
        state.topic = t;
        view.querySelector('#topic').value = t;
        syncAskButton();
      };
    });
    var topicInput = view.querySelector('#topic');
    topicInput.oninput = function () {
      state.topic = topicInput.value;
      syncAskButton();
    };
    topicInput.onkeydown = function (e) { if (e.key === 'Enter' && state.topic.trim()) startAsk(); };
    view.querySelector('#start-ask').onclick = function () { startAsk(); };
    syncAskButton();

    function syncAskButton() {
      var btn = view.querySelector('#start-ask');
      var warn = view.querySelector('#ask-warn');
      var has = !!(state.topic || '').trim();
      btn.classList[has ? 'remove' : 'add']('off');
      warn.style.display = has ? 'none' : 'block';
    }
  }

  function startAsk() {
    var topic = (state.topic || '').trim();
    if (!topic) { UI.toast('先告诉小科你想学什么吧'); return; }

    var facts = util.scienceFacts;
    askTick = 0;
    var formBox = view.querySelector('#home-form');
    var askBox = view.querySelector('#home-ask');
    if (formBox) formBox.style.display = 'none';

    function caption() {
      if (askTick < 8) return '小科正在翻书找答案…';
      if (askTick < 20) return '正在认真出题，马上就好…';
      return '快好啦，再等一下下～';
    }
    function paint() {
      askBox.innerHTML = '<div class="card ask-box">'
        + util.mascot('thinking', 'lg', caption())
        + '<div class="fact-box"><div class="fact-head">💡 等一会儿，先看条小知识</div>'
        + '<div class="fact-text">' + util.esc(facts[askTick % facts.length]) + '</div>'
        + '<div class="muted">就这样一条一条看下去，不知不觉题目就好了</div></div>'
        + '<div class="muted">已经等了 ' + askTick + ' 秒，出题一般需要 20—40 秒</div>'
        + '<button id="cancel-ask" class="btn btn-ghost" style="margin-top:14px">先不出了</button></div>';
      askBox.querySelector('#cancel-ask').onclick = function () { cancelAsk(); };
    }
    paint();

    var ticker = setInterval(function () {
      askTick = askTick + 1;
      paint();
    }, 1000);
    var seq = ++askSeq;

    UI.loading(false);
    api.post('/quiz/generate', { topic: topic, grade: state.grade, doc_id: state.docId || undefined }, { timeout: 180000 })
      .then(function (data) {
        clearInterval(ticker);
        if (seq !== askSeq) { return; }         // 用户已经取消了，静默留存结果即可
        state.lastQuiz = data;
        state.lastResult = null;
        location.hash = '#/quiz';
      })
      .catch(function () {
        clearInterval(ticker);
        if (seq !== askSeq) { return; }
        askBox.innerHTML = '';
        if (formBox) formBox.style.display = '';
      });
  }

  var askSeq = 0;
  function cancelAsk() {
    askSeq = askSeq + 1;                        // 作废本次出题，晚到的响应不再跳页
    UI.confirm({ title: '先歇一会儿？', content: '小科会停下出题，你输入的主题还留着。', confirmText: '停下', cancelText: '再等等' })
      .then(function (yes) {
        if (!yes) { return; }
        var askBox = view.querySelector('#home-ask');
        if (askBox) askBox.innerHTML = '';
        var formBox = view.querySelector('#home-form');
        if (formBox) formBox.style.display = '';
        UI.toast('好，想好了随时叫小科');
      });
  }

  /* ================= 2. 答题闯关 ================= */
  var quizState = null;

  function renderQuiz() {
    var quiz = state.lastQuiz;
    if (!quiz || !quiz.questions || !quiz.questions.length) {
      view.innerHTML = '<div class="card empty-box">' + util.mascot('idle', 'md', '还没有题目，先去选一个主题吧')
        + '<div style="margin-top:14px"><a class="btn btn-primary" href="#/home">去选主题</a></div></div>';
      return;
    }
    quizState = {
      quiz: quiz,
      index: 0,
      answers: quiz.questions.map(function () { return -1; }),
      judged: false,
      selected: -1,
      correctCount: 0,
      combo: 0,
      startAt: Date.now(),
      elapsed: 0,
      left: timeLimit(),
      timeOver: false,
      ticker: null
    };
    paintQuiz();
    startTimer();
  }

  function timeLimit() {
    return { primary_low: 45, primary_high: 40, junior: 35 }[state.grade] || 40;
  }

  function startTimer() {
    stopTimer();
    quizState.ticker = setInterval(function () {
      if (!quizState) return;
      if (quizState.judged) {
        quizState.elapsed = quizState.elapsed + 1;
      } else if (!quizState.timeOver) {
        quizState.left = quizState.left - 1;
        if (quizState.left <= 0) { quizState.timeOver = true; }
      }
      var t = document.getElementById('quiz-timer');
      if (t) {
        t.textContent = quizState.judged
          ? ('⏱ 用了 ' + quizState.elapsed + ' 秒')
          : (quizState.timeOver ? '⏳ 想好了就选一个' : ('⏳ ' + quizState.left + ' 秒'));
        t.className = 'timer' + ((quizState.judged || quizState.timeOver) ? ' over' : '');
      }
      // 到点只把小科换成鼓励态，不判负、不扣分
      if (quizState.timeOver && !quizState.judged) {
        var m = document.getElementById('quiz-mascot');
        if (m && !m.dataset.swapped) {
          m.dataset.swapped = '1';
          m.innerHTML = util.mascot('encourage', 'sm', '想好了就选一个吧，小科陪着你');
        }
      }
    }, 1000);
  }

  function stopTimer() {
    if (quizState && quizState.ticker) {
      clearInterval(quizState.ticker);
      quizState.ticker = null;
    }
  }

  function paintQuiz() {
    var qs = quizState.quiz.questions;
    var q = qs[quizState.index];
    var total = qs.length;
    var progress = Math.round((quizState.index + (quizState.judged ? 1 : 0)) / total * 100);

    var optionsHtml = (q.options || []).map(function (text, i) {
      var cls = '';
      if (quizState.judged) {
        if (i === Number(q.answer)) cls = 'correct option-pop';
        else if (i === quizState.selected) cls = 'wrong';
      } else if (i === quizState.selected) {
        cls = 'selected';
      }
      var mark = '';
      if (quizState.judged && i === Number(q.answer)) mark = '<span class="pill pill-green">✓</span>';
      if (quizState.judged && i === quizState.selected && i !== Number(q.answer)) mark = '<span class="pill pill-orange">再想想</span>';
      return '<div class="option ' + cls + (quizState.judged ? ' locked' : '') + '" data-opt="' + i + '">'
        + '<span class="option-key">' + 'ABCDEFGH'.charAt(i) + '</span>'
        + '<span class="grow">' + util.esc(text) + '</span>' + mark + '</div>';
    }).join('');

    var feedback = '';
    if (quizState.judged) {
      var ok = quizState.selected === Number(q.answer);
      feedback = '<div class="card feedback">'
        + '<div id="quiz-mascot">' + util.mascot(ok ? 'correct' : 'wrong', 'sm', ok ? ('答对啦！你把「' + (q.knowledge_point || '这个知识点') + '」抓住了') : '') + '</div>'
        + (quizState.combo >= 2 && ok ? '' : '')
        + (quizState.streakEncourage ? '<div class="encourage">🤝 <span>要不要先看看解析？看懂了再往下走，一点也不急。</span></div>' : '')
        + (q.knowledge_point ? '<div class="pill pill-orange" style="margin-bottom:10px">' + util.esc(q.knowledge_point) + '</div>' : '')
        + '<div class="h3" style="margin-bottom:6px">小科讲讲这道题</div>'
        + '<div class="body">' + util.esc(q.analysis || '先把正确答案记下来，下次就能想起来了') + '</div>'
        + '</div>';
    }

    var isLast = quizState.index === total - 1;
    var btnText = quizState.judged ? (isLast ? '看看我的报告' : '下一题') : '就选这个';

    view.innerHTML = '<div class="card">'
      + '<div class="between" style="margin-bottom:10px">'
      + '  <span class="h3">第 ' + (quizState.index + 1) + ' / ' + total + ' 题</span>'
      + '  <span class="head-right">'
      + '    <span id="quiz-timer" class="timer' + ((quizState.judged || quizState.timeOver) ? ' over' : '') + '">'
      +      (quizState.judged ? ('⏱ 用了 ' + quizState.elapsed + ' 秒')
             : (quizState.timeOver ? '⏳ 想好了就选一个' : ('⏳ ' + quizState.left + ' 秒')))
      + '    </span>'
      + '    <span class="pill">' + util.esc(gradeLabel()) + '</span>'
      + '  </span>'
      + '</div>'
      + '<div class="progress"><div class="progress-inner" style="width:' + progress + '%"></div></div>'
      + '<div class="between" style="margin-top:10px">'
      + '  <span class="muted">' + util.esc(quizState.quiz.title || '科普闯关') + '</span>'
      + '  <span class="tag">' + util.esc(util.sourceText(quizState.quiz.source) + (quizState.quiz.source === 'wrongbook' ? ' · 错题重练' : '')) + '</span>'
      + '</div></div>'
      + (quizState.combo >= 2 && quizState.judged ? '<div class="combo-bar">🔥 ' + comboText(quizState.combo) + '</div>' : '')
      + '<div class="card">'
      + '  <div class="h2">' + util.esc(q.stem) + '</div>'
      + '  <div class="muted" style="margin-top:6px">选出你觉得对的那一个</div>'
      + '</div>'
      + '<div id="options">' + optionsHtml + '</div>'
      + feedback
      + '<button id="quiz-btn" class="btn btn-primary btn-block" style="margin-top:16px">' + btnText + '</button>';

    view.querySelectorAll('[data-opt]').forEach(function (el) {
      el.onclick = function () {
        if (quizState.judged) return;
        var i = Number(el.getAttribute('data-opt'));
        quizState.selected = i;
        paintQuiz();
        sound.tap();
      };
    });
    view.querySelector('#quiz-btn').onclick = function () {
      if (quizState.judged) { nextQuestion(); } else { judge(); }
    };
  }

  function comboText(combo) {
    var words = { 2: '连对两题！', 3: '三连对，稳住！', 4: '四连对，厉害了！', 5: '五连对，太棒了！' };
    return words[combo] || (combo + ' 连对，停不下来！');
  }

  function judge() {
    if (quizState.selected < 0) { UI.toast('选一个你觉得对的，小科再看看'); return; }
    var q = quizState.quiz.questions[quizState.index];
    var ok = quizState.selected === Number(q.answer);
    quizState.judged = true;
    quizState.answers[quizState.index] = quizState.selected;

    if (ok) {
      quizState.correctCount = quizState.correctCount + 1;
      quizState.combo = quizState.combo + 1;
      quizState.streakWrong = 0;
      sound.correct(quizState.combo);
      if (quizState.combo >= 3) sound.combo(quizState.combo);
      flash(quizState.combo >= 2 ? comboText(quizState.combo) : '答对啦 +2');
    } else {
      quizState.combo = 0;
      quizState.streakWrong = (quizState.streakWrong || 0) + 1;
      sound.wrong();
    }
    // 连错两题就给出口，不逼着孩子一直错下去
    quizState.streakEncourage = quizState.streakWrong >= 2;
    paintQuiz();
  }

  function nextQuestion() {
    var total = quizState.quiz.questions.length;
    if (quizState.index === total - 1) { submitQuiz(); return; }
    quizState.index = quizState.index + 1;
    quizState.judged = false;
    quizState.selected = -1;
    quizState.left = timeLimit();
    quizState.timeOver = false;
    quizState.elapsed = 0;
    quizState.streakEncourage = false;
    paintQuiz();
  }

  function submitQuiz() {
    stopTimer();
    var duration = Date.now() - quizState.startAt;
    UI.loading(true, '小科在算分…');
    api.post('/quiz/submit', {
      quiz_id: quizState.quiz.quiz_id,
      answers: quizState.answers,
      duration_ms: duration
    })
      .then(function (data) {
        UI.loading(false);
        state.lastResult = data;
        sound.win();
        // 用服务端的累计经验值刷新等级（比本地累加准）；拉不到就本地累加兜底
        var fallback = function () {
          state.totalXp = state.totalXp + (data.xp_gained || 0);
          renderTop();
        };
        reloadProfile().then(function () {
          if (!state.totalXp) { fallback(); }
          location.hash = '#/report';
          route();
        });
      })
      .catch(function () { UI.loading(false); });
  }

  /* ================= 3. 复盘报告 ================= */
  function renderReport() {
    var r = state.lastResult;
    if (!r) {
      view.innerHTML = '<div class="card empty-box">' + util.mascot('idle', 'md', '还没有这一局的成绩，先去闯一关吧')
        + '<div style="margin-top:14px"><a class="btn btn-primary" href="#/home">去闯关</a></div></div>';
      return;
    }
    var accuracy = Math.round(Number(r.accuracy) || 0);
    var mState = accuracy >= 80 ? 'win' : (accuracy >= 60 ? 'correct' : 'encourage');
    var wrongList = (r.details || []).filter(function (d) { return !d.is_correct; });

    var wrongHtml = wrongList.length ? wrongList.map(function (d) {
      return '<div class="item"><div class="h3">' + util.esc(d.stem) + '</div>'
        + '<div class="meta-row">'
        + '<span class="pill pill-orange">你的答案：' + util.esc(util.optionText(d.options, d.user_answer) || '没作答') + '</span>'
        + '<span class="pill pill-green">正确答案：' + util.esc(util.optionText(d.options, d.correct_answer)) + '</span>'
        + '</div>'
        + '<div class="muted" style="margin-top:8px">' + util.esc(d.analysis || '') + '</div></div>';
    }).join('') : '<div class="empty">这一局没有答错的题，很棒！</div>';

    view.innerHTML = '<div class="card">'
      + '<div class="center">' + util.mascot(mState, 'lg', '') + '</div>'
      + '<div class="score-row">'
      + '  <div><span class="score-num">' + accuracy + '</span><span class="score-unit">%</span></div>'
      + '  <div><div class="h3">这一局的正确率</div><div class="muted">答对 ' + r.correct + ' / ' + r.total + ' 题</div></div>'
      + '</div>'
      + '<div class="progress"><div class="progress-inner" style="width:' + accuracy + '%"></div></div>'
      + '<div class="between" style="margin-top:8px"><span class="muted">掌握度</span><span class="muted">' + accuracy + ' 分</span></div>'
      + '</div>'

      + '<div class="card" id="report-card"><div class="center">' + util.mascot('thinking', 'md', '小科在写复盘报告…') + '</div></div>'

      + '<div class="card"><div class="card-title">这一局的收获</div>'
      + '<div class="settle-grid">'
      + '  <div><div class="settle-num">+' + (r.xp_gained || 0) + '</div><div class="muted">经验值</div></div>'
      + '<div><div class="settle-num">' + (r.wrong_added || 0) + '</div><div class="muted">新收的错题</div></div>'
      + '<div><div class="settle-num">' + (r.mastered || 0) + '</div><div class="muted">已经掌握的题</div></div>'
      + '<div><div class="settle-num">' + (r.wrong_total || 0) + '</div><div class="muted">错题本共</div></div>'
      + '</div>'
      + '<div class="level-box" id="level-box"></div>'
      + '</div>'

      + '<div class="card"><div class="card-title">本次答题回顾（只看答错的）</div>' + wrongHtml + '</div>'

      + '<div class="acts" style="margin-bottom:40px">'
      + '  <a class="btn btn-primary" href="#/home">再来一局</a>'
      + '  <a class="btn btn-ghost" href="#/wrong">去错题本</a>'
      + '</div>';

    paintLevelBox();
    loadReport(r.quiz_id);
  }

  function paintLevelBox() {
    var info = util.levelInfo(state.totalXp);
    var box = document.getElementById('level-box');
    if (!box) return;
    box.innerHTML = '<div class="level-head">'
      + '<span class="row"><span class="level-badge">Lv.' + info.level + '</span>'
      + '<span class="level-title">' + util.levelTitle(info.level) + '</span></span>'
      + '<span class="muted">还差 ' + info.remain + ' 点升级</span></div>'
      + '<div class="progress"><div class="progress-inner" style="width:' + info.percent + '%"></div></div>'
      + '<div class="muted level-tip">每 50 点经验升一级，继续闯关就能升级啦</div>';
  }

  function loadReport(quizId) {
    if (!quizId) return;
    api.post('/report/generate', { quiz_id: quizId }, { silent: true })
      .then(function (data) {
        var rep = (data && data.report) || {};
        var weak = (rep.weak_points || []).map(function (w) {
          return '<span class="pill pill-orange">' + util.esc(w) + '</span>';
        }).join(' ');
        var card = document.getElementById('report-card');
        if (!card) return;
        card.innerHTML = '<div class="between" style="margin-bottom:12px">'
          + '<span class="card-title" style="margin:0">小科的复盘</span>'
          + '<span class="tag">' + (rep.source === 'ai' ? '由 AI 生成' : '本次由学习助手生成') + '</span></div>'
          + '<div class="row" style="gap:18px;flex-wrap:wrap">'
          + '  <div style="text-align:center"><div class="settle-num">' + (rep.mastery === undefined ? '—' : rep.mastery) + '</div><div class="muted">掌握度</div></div>'
          + '  <div class="grow" style="min-width:220px">'
          + '    <div class="body">' + util.esc(rep.summary || '') + '</div>'
          + '    <div class="body" style="margin-top:10px">' + util.esc(rep.suggestion || '') + '</div>'
          + '  </div>'
          + '</div>'
          + (weak ? '<div class="meta-row" style="margin-top:14px">' + weak + '</div>' : '');
      })
      .catch(function () {
        var card = document.getElementById('report-card');
        if (card) card.innerHTML = '<div class="empty">小科这份复盘还没写好，刷新一下再试试</div>';
      });
  }

  /* ================= 4. 错题本（完整增删改查） ================= */
  var wrongCache = [];
  var editingStem = null;

  function renderWrong() {
    view.innerHTML = '<div class="card"><div class="center">' + util.mascot('thinking', 'sm', '小科正在翻错题本…') + '</div></div>';
    api.get('/wrong/questions')
      .then(function (data) {
        wrongCache = (data && data.questions) || [];
        paintWrong(data);
      })
      .catch(function () {
        view.innerHTML = '<div class="card empty-box">' + util.mascot('encourage', 'md', '错题本要登录后才能用哦') + '</div>';
      });
  }

  function paintWrong(data) {
    var total = (data && data.total) || 0;
    var weak = ((data && data.weak_points) || []).map(function (w) {
      return '<span class="pill pill-orange">' + util.esc(w.knowledge_point) + ' · 错 ' + (w.wrong_times || 0) + ' 次</span>';
    }).join(' ');

    var listHtml = wrongCache.length ? wrongCache.map(function (q, i) {
      var expanded = q.__expanded;
      var editing = editingStem === q.stem;
      var detail = '';
      if (expanded) {
        detail = '<div style="margin-top:12px">'
          + '<div class="meta-row">'
          + (q.user_answer >= 0 ? '<span class="pill pill-orange">你的答案：' + util.esc(util.optionText(q.options, q.user_answer)) + '</span>' : '')
          + '<span class="pill pill-green">正确答案：' + util.esc(util.optionText(q.options, q.answer)) + '</span>'
          + '</div>'
          + '<div class="body" style="margin-top:10px">' + util.esc(q.analysis || '') + '</div>';
        if (!editing) {
          detail += '<div class="acts" style="margin-top:14px">'
            + '<button class="btn btn-ghost btn-sm" data-edit="' + i + '">改一改</button>'
            + '<button class="btn btn-danger-ghost btn-sm" data-del="' + i + '">不用留了</button>'
            + '</div>';
        } else {
          detail += '<div class="edit-box">'
            + '<div class="h3" style="margin-bottom:12px">改一改这道题</div>'
            + '<div class="field"><label>题干</label><input class="input" id="e-stem" value="' + util.esc(q.stem) + '"></div>'
            + '<div class="field"><label>知识点</label><input class="input" id="e-kp" value="' + util.esc(q.knowledge_point || '') + '"></div>'
            + '<div class="field"><label>正确答案（点一下就改）</label><div class="chips">'
            + (q.options || []).map(function (o, oi) {
                return '<span class="chip ' + (oi === q.answer ? 'on' : '') + '" data-ans="' + oi + '">'
                  + '<span class="ck">' + 'ABCDEFGH'.charAt(oi) + '</span> ' + util.esc(o) + '</span>';
              }).join('')
            + '</div></div>'
            + '<div class="field"><label>解析</label><textarea class="input" id="e-an" rows="3">' + util.esc(q.analysis || '') + '</textarea></div>'
            + '<div class="acts">'
            + '<button class="btn btn-primary btn-sm" data-save="' + i + '">就改这样</button>'
            + '<button class="btn btn-ghost btn-sm" data-cancel="1">算了</button>'
            + '</div></div>';
        }
        detail += '</div>';
      }
      return '<div class="item">'
        + '<div class="item-head" data-toggle="' + i + '">'
        + '  <div class="h3">' + (i + 1) + '. ' + util.esc(q.stem) + '</div>'
        + '  <div class="meta-row">'
        + '    <span class="pill">' + util.esc(q.knowledge_point || '科普知识') + '</span>'
        + '    <span class="pill pill-orange">错过 ' + (q.wrong_count || 1) + ' 次</span>'
        + '    <span class="muted">' + util.esc(util.shortTime(q.last_wrong_at)) + '</span>'
        + '    <span class="muted">' + (expanded ? '收起讲解' : '看看讲解') + '</span>'
        + '  </div>'
        + '</div>' + detail + '</div>';
    }).join('') : '<div class="empty-box">' + util.mascot('idle', 'sm', '还没有错题，去闯一关吧！')
      + '<div style="margin-top:14px"><a class="btn btn-primary" href="#/home">去闯关</a></div></div>';

    view.innerHTML = '<div class="card">'
      + '<div class="h2" style="text-align:center;font-size:44px;color:var(--c-primary-deep)">' + total + '</div>'
      + '<div class="muted" style="text-align:center">错题本里一共有这么多题</div>'
      + (weak ? '<div class="meta-row" style="margin-top:14px;justify-content:center">' + weak + '</div>' : '')
      + '</div>'
      + '<div class="card">'
      + '<button id="practice" class="btn btn-primary btn-block' + (total ? '' : ' off') + '"' + (total ? '' : ' disabled') + '>只练错题</button>'
      + '<div class="muted" style="text-align:center;margin-top:10px">不用等 AI 出题，马上就能开始</div>'
      + '</div>'
      + '<div class="card"><div class="card-title">错题清单</div>' + listHtml + '</div>'
      + (total ? '<button id="clear-wrong" class="btn btn-ghost" style="margin-bottom:40px">清空错题本</button>' : '');

    // 展开 / 收起
    view.querySelectorAll('[data-toggle]').forEach(function (el) {
      el.onclick = function () {
        var i = Number(el.getAttribute('data-toggle'));
        wrongCache[i].__expanded = !wrongCache[i].__expanded;
        if (!wrongCache[i].__expanded) editingStem = null;
        paintWrong(data);
      };
    });
    // 改
    view.querySelectorAll('[data-edit]').forEach(function (el) {
      el.onclick = function (e) {
        e.stopPropagation();
        editingStem = wrongCache[Number(el.getAttribute('data-edit'))].stem;
        paintWrong(data);
      };
    });
    view.querySelectorAll('[data-cancel]').forEach(function (el) {
      el.onclick = function () { editingStem = null; paintWrong(data); };
    });
    // 编辑态里点选项 = 把它设为正确答案
    var picked = null;
    view.querySelectorAll('[data-ans]').forEach(function (el) {
      el.onclick = function () {
        picked = Number(el.getAttribute('data-ans'));
        view.querySelectorAll('[data-ans]').forEach(function (x) { x.classList.remove('on'); });
        el.classList.add('on');
      };
    });
    // 保存
    view.querySelectorAll('[data-save]').forEach(function (el) {
      el.onclick = function () {
        var i = Number(el.getAttribute('data-save'));
        var q = wrongCache[i];
        var stem = (view.querySelector('#e-stem').value || '').trim();
        var kp = (view.querySelector('#e-kp').value || '').trim();
        var an = (view.querySelector('#e-an').value || '').trim();
        if (!stem) { UI.toast('题干不能空着哦'); return; }
        var payload = { stem: q.stem };
        if (stem !== q.stem) payload.new_stem = stem;
        if (kp !== (q.knowledge_point || '')) payload.knowledge_point = kp;
        if (an !== (q.analysis || '')) payload.analysis = an;
        if (picked !== null && picked !== q.answer) payload.answer = picked;

        UI.loading(true, '小科正在记下改动…');
        api.put('/wrong/questions', payload)
          .then(function () {
            UI.loading(false);
            editingStem = null;
            UI.toast('改好了，这道题更清楚了');
            renderWrong();
          })
          .catch(function () { UI.loading(false); });
      };
    });
    // 删单条
    view.querySelectorAll('[data-del]').forEach(function (el) {
      el.onclick = function (e) {
        e.stopPropagation();
        var q = wrongCache[Number(el.getAttribute('data-del'))];
        UI.confirm({
          title: '这道题不留了？',
          content: '删掉之后这道题就不在错题本里了，练过的记录也跟着一起清掉。',
          confirmText: '删掉', cancelText: '再留着', confirmColor: '#FF8A65'
        }).then(function (yes) {
          if (!yes) return;
          UI.loading(true, '小科正在收拾…');
          api.delBody('/wrong/questions/item', { stem: q.stem })
            .then(function () { UI.loading(false); UI.toast('删掉啦'); renderWrong(); })
            .catch(function () { UI.loading(false); });
        });
      };
    });
    // 只练错题
    var p = view.querySelector('#practice');
    if (p) {
      p.onclick = function () {
        if (!total) return;
        UI.loading(true, '小科正在组卷…');
        api.post('/wrong/practice', { count: 8, grade: state.grade })
          .then(function (data) {
            UI.loading(false);
            state.lastQuiz = data;
            state.lastResult = null;
            location.hash = '#/quiz';
          })
          .catch(function () { UI.loading(false); });
      };
    }
    // 清空
    var c = view.querySelector('#clear-wrong');
    if (c) {
      c.onclick = function () {
        UI.confirm({ title: '清空错题本', content: '确定要清空吗？清空后错题就找不回来了', confirmText: '清空', cancelText: '先留着' })
          .then(function (yes) {
            if (!yes) return;
            UI.loading(true, '小科正在收拾…');
            api.del('/wrong/questions')
              .then(function () { UI.loading(false); UI.toast('清空啦，轻装上阵！'); renderWrong(); })
              .catch(function () { UI.loading(false); });
          });
      };
    }
  }

  /* ================= 5. 知识库（增删查 + 用它出题） ================= */
  function renderKnowledge() {
    view.innerHTML = '<div class="card"><div class="center">' + util.mascot('thinking', 'sm', '小科正在整理资料…') + '</div></div>';
    api.get('/knowledge/documents')
      .then(paintKnowledge)
      .catch(function () { view.innerHTML = '<div class="card empty-box">资料没读出来，刷新一下再试</div>'; });
  }

  function paintKnowledge(data) {
    var docs = (data && data.documents) || [];
    var listHtml = docs.length ? docs.map(function (d, i) {
      return '<div class="doc-row">'
        + '<span style="font-size:22px">📄</span>'
        + '<div class="grow"><div class="h3">' + util.esc(d.filename) + '</div>'
        + '<div class="muted">' + util.esc(d.file_type || 'txt') + ' · ' + util.sizeText(d.size_bytes) + ' · ' + util.esc(util.shortTime(d.created_at)) + '</div></div>'
        + '<button class="btn btn-ghost btn-sm" data-use="' + i + '">用它出题</button>'
        + '<button class="btn btn-danger-ghost btn-sm" data-drop="' + i + '">删除</button>'
        + '</div>';
    }).join('') : '<div class="empty-box">' + util.mascot('idle', 'sm', '还没有资料，贴一份讲义上来试试吧') + '</div>';

    view.innerHTML = '<div class="card">'
      + '<div class="card-title">小科的知识库</div>'
      + '<div class="muted">把讲义或课外读本的文字贴/传上来，小科就能照着它出题——题目只依据这份资料，不会自己编。</div>'
      + '</div>'
      + '<div class="card">'
      + '<div class="card-title">添加一份资料</div>'
      + '<div class="field"><label>资料名称</label><input class="input" id="doc-name" placeholder="比如：水循环讲义.txt" value="我的讲义.txt"></div>'
      + '<div class="field"><label>资料内容（把文字粘进来）</label>'
      + '<textarea class="input" id="doc-text" rows="6" placeholder="水循环是指水在地球上的循环过程。海水受热蒸发变成水蒸气……"></textarea></div>'
      + '<div class="acts"><button class="btn btn-primary" id="doc-add">上传资料</button>'
      + '<label class="btn btn-ghost" style="cursor:pointer">选本地文件<input type="file" id="doc-file" accept=".txt,.md,.csv" style="display:none"></label></div>'
      + '</div>'
      + '<div class="card"><div class="card-title">我的资料（' + docs.length + '）</div>' + listHtml + '</div>'
      + '<div class="muted" style="margin-bottom:40px">支持 txt / md / csv 文本；pdf / docx 需要服务端安装 pypdf、docx2txt 依赖。</div>';

    function addDoc(name, text) {
      if (!text || !text.trim()) { UI.toast('先写点内容再上传吧'); return; }
      UI.loading(true, '小科正在读这份资料…');
      api.uploadText(name || '我的讲义.txt', text)
        .then(function () {
          UI.loading(false);
          UI.toast('资料读进去了，可以拿它出题啦');
          renderKnowledge();
        })
        .catch(function () { UI.loading(false); });
    }

    var addBtn = view.querySelector('#doc-add');
    addBtn.onclick = function () {
      addDoc(view.querySelector('#doc-name').value.trim(), view.querySelector('#doc-text').value);
    };
    var fileInput = view.querySelector('#doc-file');
    fileInput.onchange = function () {
      var f = fileInput.files && fileInput.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        view.querySelector('#doc-name').value = f.name;
        view.querySelector('#doc-text').value = String(reader.result || '');
        UI.toast('文件读进来了，点「上传资料」入库');
      };
      reader.readAsText(f, 'utf-8');
    };

    view.querySelectorAll('[data-use]').forEach(function (el) {
      el.onclick = function () {
        var d = docs[Number(el.getAttribute('data-use'))];
        state.docId = d.doc_id;
        state.docName = d.filename;
        state.topic = d.filename.replace(/\.[^.]+$/, '');
        UI.toast('回到首页，基于《' + d.filename + '》出题');
        location.hash = '#/home';
      };
    });
    view.querySelectorAll('[data-drop]').forEach(function (el) {
      el.onclick = function () {
        var d = docs[Number(el.getAttribute('data-drop'))];
        UI.confirm({ title: '删掉这份资料？', content: '《' + d.filename + '》删掉后就不能拿它出题了。', confirmText: '删掉', cancelText: '先留着' })
          .then(function (yes) {
            if (!yes) return;
            api.del('/knowledge/documents/' + d.doc_id)
              .then(function () { UI.toast('删掉啦'); renderKnowledge(); })
              .catch(function () {});
          });
      };
    });
  }

  /* ================= 6. 我的 ================= */
  function renderProfile() {
    view.innerHTML = '<div class="card"><div class="center">' + util.mascot('thinking', 'sm', '小科正在整理…') + '</div></div>';
    api.get('/user/profile')
      .then(function (data) {
        var user = (data && data.user) || {};
        state.totalXp = user.total_xp || 0;
        renderTop();
        var info = util.levelInfo(state.totalXp);
        var weak = ((data && data.weak_points) || []).map(function (w) {
          return '<span class="pill pill-orange">' + util.esc(w.knowledge_point) + ' · 错 ' + (w.wrong_times || 0) + ' 次</span>';
        }).join(' ');
        var sessions = (data && data.sessions) || [];
        var sessionHtml = sessions.length ? sessions.map(function (s) {
          return '<div class="doc-row"><span style="font-size:20px">🏁</span>'
            + '<div class="grow"><div class="h3">' + util.esc(s.title || '这一局闯关') + '</div>'
            + '<div class="muted">' + util.esc(gradeLabel(s.grade)) + ' · ' + util.esc(util.sourceText(s.source)) + ' · ' + util.esc(util.shortTime(s.created_at)) + '</div></div></div>';
        }).join('') : '<div class="empty">还没有闯关记录，去闯一关吧！</div>';

        view.innerHTML = '<div class="card">'
          + '<h2 class="h2">' + util.esc(user.nickname || '小科学家') + '</h2>'
          + '<div class="row" style="margin:8px 0 14px"><span class="level-badge">Lv.' + info.level + '</span>'
          + '<span class="level-title">' + util.levelTitle(info.level) + '</span></div>'
          + '<div class="progress"><div class="progress-inner" style="width:' + info.percent + '%"></div></div>'
          + '<div class="muted" style="margin-top:8px">再攒 ' + info.remain + ' 点经验就升级啦</div>'
          + '<div class="settle-grid" style="margin-top:18px">'
          + '<div><div class="settle-num">' + state.totalXp + '</div><div class="muted">累计经验值</div></div>'
          + '<div><div class="settle-num">' + (data.wrong_count || 0) + '</div><div class="muted">错题本里的题</div></div>'
          + '<div><div class="settle-num">' + sessions.length + '</div><div class="muted">闯关次数</div></div>'
          + '<div><div class="settle-num" style="font-size:18px">' + util.esc(gradeLabel(user.grade)) + '</div><div class="muted">当前学段</div></div>'
          + '</div></div>'

          + '<div class="card"><div class="card-title">要多看两眼的知识点</div>'
          + (weak || '<div class="body">还没有薄弱知识点，保持这个势头！</div>') + '</div>'

          + '<div class="card"><div class="card-title">历史闯关</div>' + sessionHtml + '</div>'

          + '<div class="card"><div class="between"><div class="grow">'
          + '<div class="h3">闯关音效</div><div class="muted">答对、连对会有轻声提示，安静场合可以关掉</div></div>'
          + '<button class="btn btn-ghost btn-sm" id="sound-toggle">' + (sound.enabled() ? '已开启' : '已关闭') + '</button>'
          + '</div></div>'

          + (state.isGuest
            ? '<div class="card" style="background:#FFF9E8">'
              + '<div class="h3">你正在用游客身份</div>'
              + '<div class="muted" style="margin:6px 0 12px">游客期间的成绩和错题只认这台浏览器——'
              + '清掉浏览器记录或换台设备就找不回来了。注册一个账号（口令随便设，6 位以上），'
              + '小科会把这段时间的记录并过去，不会白玩。</div>'
              + '<button class="btn btn-primary" id="go-register">注册账号，保存记录</button>'
              + '</div>'
            : '')

          + '<div class="acts" style="margin-bottom:40px">'
          + '<button class="btn btn-ghost" id="clear-wrong2">清空错题本</button>'
          + '<button class="btn btn-ghost" id="logout">退出登录</button>'
          + '</div>';

        var regBtn = view.querySelector('#go-register');
        if (regBtn) {
          regBtn.onclick = function () { location.hash = '#/login'; renderLogin('register'); };
        }
        view.querySelector('#sound-toggle').onclick = function () {
          var on = !sound.enabled();
          sound.setEnabled(on);
          this.textContent = on ? '已开启' : '已关闭';
          UI.toast(on ? '音效打开啦' : '好，安静模式');
        };
        view.querySelector('#clear-wrong2').onclick = function () {
          UI.confirm({ title: '清空错题本', content: '确定要清空吗？清空后错题就找不回来了', confirmText: '清空', cancelText: '先留着' })
            .then(function (yes) {
              if (!yes) return;
              api.del('/wrong/questions')
                .then(function () { UI.toast('清空啦'); renderProfile(); })
                .catch(function () {});
            });
        };
        view.querySelector('#logout').onclick = function () {
          api.clearSession();
          UI.toast('已退出，刷新页面会自动建一个新账号');
          setTimeout(function () { location.reload(); }, 800);
        };
      })
      .catch(function () {
        view.innerHTML = '<div class="card empty-box">' + util.mascot('encourage', 'md', '没读到你的资料，刷新一下再试试') + '</div>';
      });
  }

  // 启动：只能放在文件末尾——boot() 会立刻读取 state，
  // 而 state 是用 const 声明的，提前调用会撞上暂时性死区（TDZ）报错。
  boot();
})();
