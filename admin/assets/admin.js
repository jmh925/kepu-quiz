/* 管理端脚本：原生 JS，无构建步骤、无第三方依赖。
   与后端约定：所有请求携带 X-Admin-Token；统一响应体 {code, message, data}。*/
'use strict';

var Admin = (function () {
  var API = '/api/v1/admin';
  var state = { token: '', admin: null, qPage: 1, uPage: 1, sPage: 1, editing: null };

  // ---------- 基础请求 ----------
  function request(method, path, body) {
    var headers = { 'Accept': 'application/json' };
    if (state.token) { headers['X-Admin-Token'] = state.token; }
    var init = { method: method, headers: headers };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json; charset=utf-8';
      init.body = JSON.stringify(body);
    }
    return fetch(API + path, init).then(function (resp) {
      return resp.json().catch(function () { return { code: -1, message: '响应解析失败' }; });
    }).then(function (json) {
      if (json.code === 4011) { logout(); throw new Error(json.message || '登录已失效'); }
      if (json.code !== 0) { throw new Error(json.message || '请求失败'); }
      return json.data;
    });
  }
  function get(p) { return request('GET', p); }
  function post(p, b) { return request('POST', p, b); }
  function put(p, b) { return request('PUT', p, b); }
  function del(p) { return request('DELETE', p); }

  function esc(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function $(id) { return document.getElementById(id); }

  // ---------- 登录 / 退出 ----------
  function login(username, password) {
    return post('/login', { username: username, password: password }).then(function (data) {
      state.token = data.token;
      state.admin = data.admin;
      sessionStorage.setItem('kepu_admin_token', data.token);
      sessionStorage.setItem('kepu_admin_name', data.admin.username);
      showApp();
    });
  }

  function logout() {
    state.token = ''; state.admin = null;
    sessionStorage.removeItem('kepu_admin_token');
    sessionStorage.removeItem('kepu_admin_name');
    $('app').classList.add('hidden');
    $('login-layer').classList.remove('hidden');
  }

  function showApp() {
    $('login-layer').classList.add('hidden');
    $('app').classList.remove('hidden');
    $('admin-name').textContent = (state.admin && state.admin.username) || '';
    route();
  }

  // ---------- 路由 ----------
  var loaded = {};
  function route() {
    var view = (location.hash || '#/dashboard').replace('#/', '') || 'dashboard';
    var views = ['dashboard', 'questions', 'users', 'sessions', 'logs'];
    if (views.indexOf(view) < 0) { view = 'dashboard'; }
    views.forEach(function (v) {
      $('view-' + v).classList.toggle('hidden', v !== view);
    });
    Array.prototype.forEach.call(document.querySelectorAll('.nav a'), function (a) {
      a.classList.toggle('active', a.getAttribute('data-view') === view);
    });
    if (view === 'dashboard') { loadDashboard(); }
    if (view === 'questions') { loadQuestions(1); }
    if (view === 'users') { loadUsers(1); }
    if (view === 'sessions') { loadSessions(1); }
    if (view === 'logs') { loadLogs(); }
  }

  // ---------- 运行看板 ----------
  function loadDashboard() {
    return get('/dashboard').then(function (d) {
      var cards = [
        ['注册用户', d.users.total, '今日新增 ' + d.users.today_new + ' 人'],
        ['闯关次数', d.quizzes.total, '今日 ' + d.quizzes.today + ' 次'],
        ['平均正确率', d.answers.avg_accuracy + '%', '已提交 ' + d.answers.submitted + ' 份答卷'],
        ['错题总量', d.wrongbook.total, '条'],
        ['知识库文档', d.knowledge.docs, '分块 ' + d.knowledge.chunks + ' 个'],
        ['资源池题目', d.pool.total, '启用 ' + d.pool.enabled + ' 道'],
        ['大模型', d.llm.configured ? '已接入' : '未接入', d.llm.configured ? d.llm.model : '当前为题库降级模式']
      ];
      $('cards').innerHTML = cards.map(function (c) {
        return '<div class="card"><div class="k">' + esc(c[0]) + '</div><div class="v">' +
          esc(c[1]) + '</div><div class="s">' + esc(c[2]) + '</div></div>';
      }).join('');
      var src = (d.quizzes.by_source || []).map(function (s) {
        return (s.source === 'ai' ? 'AI 出题' : s.source === 'wrongbook' ? '错题重练' : '题库出题') + ' ' + s.c + ' 次';
      }).join('、');
      $('cards').insertAdjacentHTML('beforeend',
        '<div class="card"><div class="k">出题来源分布</div><div class="v" style="font-size:15px">' +
        esc(src || '暂无数据') + '</div></div>');
      $('weak').innerHTML = (d.wrongbook.top_points || []).map(function (p) {
        return '<span class="chip">' + esc(p.kp || '科普知识') + ' · ' + (p.c || 0) + ' 题 / 错 ' + (p.w || 0) + ' 次</span>';
      }).join('') || '<span class="muted">暂无错题数据</span>';
      return get('/trend?days=7').then(function (t) { renderTrend(t.points || []); });
    }).catch(function (e) { alert(e.message); });
  }

  function renderTrend(points) {
    if (!points.length) { $('trend').innerHTML = '<span class="muted">近 7 天还没有闯关记录</span>'; return; }
    var max = Math.max.apply(null, points.map(function (p) { return p.count; })) || 1;
    $('trend').innerHTML = points.map(function (p) {
      var h = Math.round(p.count / max * 100);
      return '<div class="bar-wrap"><div class="num">' + p.count + '</div>' +
        '<div class="bar" style="height:' + h + '%"></div>' +
        '<div class="lbl">' + esc(p.date.slice(5)) + '</div></div>';
    }).join('');
  }

  // ---------- 题库资源池 ----------
  /** 主题 + 学段筛选（学段很关键：低年级与初中的题不能混用） */
  function loadThemes() {
    return get('/questions/themes').then(function (d) {
      var sel = $('q-theme');
      if (!sel) return;
      var opts = ['<option value="">全部主题</option>'];
      (d.themes || []).forEach(function (t) {
        opts.push('<option value="' + esc(t.theme) + '">' + esc(t.theme) + '（' + t.count + '）</option>');
      });
      sel.innerHTML = opts.join('');
    }).catch(function () {});
  }

  function loadQuestions(page) {
    state.qPage = page || 1;
    var kw = $('q-keyword').value.trim();
    var theme = $('q-theme') ? $('q-theme').value : '';
    var grade = $('q-grade') ? $('q-grade').value : '';
    loadThemes();
    var qs = '/questions?page=' + state.qPage + '&size=10&keyword=' + encodeURIComponent(kw);
    if (theme) qs += '&theme=' + encodeURIComponent(theme);
    if (grade) qs += '&grade=' + encodeURIComponent(grade);
    return get(qs)
      .then(function (d) {
        var rows = (d.items || []).map(function (q) {
          return '<tr>' +
            '<td>' + q.id + '</td>' +
            '<td><span class="tag">' + esc(q.theme) + '</span></td>' +
            '<td><span class="tag tag-grade g-' + esc(q.grade) + '">' + gradeLabel(q.grade) + '</span></td>' +
            '<td class="stem">' + esc(q.stem) + '</td>' +
            '<td>' + esc((q.options || []).join(' / ')) + '</td>' +
            '<td>' + 'ABCD'.charAt(q.answer) + '</td>' +
            '<td>' + esc(q.knowledge_point) + '</td>' +
            '<td>' + (q.enabled ? '<span class="tag tag-ok">启用</span>' : '<span class="tag tag-off">停用</span>') + '</td>' +
            '<td><button class="btn btn-ghost btn-sm" onclick="Admin.openQuestion(' + q.id + ')">编辑</button> ' +
            '<button class="btn btn-danger btn-sm" onclick="Admin.removeQuestion(' + q.id + ')">删除</button></td>' +
            '</tr>';
        }).join('');
        $('q-table').innerHTML = '<tr><th>ID</th><th>主题</th><th>学段</th><th>题干</th><th>选项</th>' +
          '<th>答案</th><th>知识点</th><th>状态</th><th>操作</th></tr>' +
          (rows || '<tr><td colspan="9" class="muted">这个条件下还没有题目，换个筛选或点右上角「新增题目」加一道</td></tr>');
        state.qCache = d.items || [];
        renderPager('q-pager', d.total, d.page, d.size, loadQuestions);
      }).catch(function (e) { alert(e.message); });
  }

  function gradeLabel(g) {
    return { primary_low: '小学低年级', primary_high: '小学高年级', junior: '初中' }[g] || g;
  }

  function renderPager(id, total, page, size, handler) {
    var pages = Math.max(1, Math.ceil(total / size));
    var el = $(id);
    el.innerHTML = '<button ' + (page <= 1 ? 'disabled' : '') + '>上一页</button>' +
      '<span class="muted">第 ' + page + ' / ' + pages + ' 页，共 ' + total + ' 条</span>' +
      '<button ' + (page >= pages ? 'disabled' : '') + '>下一页</button>';
    var buttons = el.querySelectorAll('button');
    buttons[0].onclick = function () { handler(page - 1); };
    buttons[1].onclick = function () { handler(page + 1); };
  }

  function openQuestion(id) {
    state.editing = id || null;
    var q = null;
    if (id) { q = (state.qCache || []).filter(function (x) { return x.id === id; })[0]; }
    $('modal-title').textContent = id ? '编辑题目 #' + id : '新增题目';
    $('f-theme').value = q ? q.theme : '天文';
    $('f-grade').value = q ? q.grade : 'primary_high';
    $('f-difficulty').value = q ? String(q.difficulty) : '2';
    $('f-stem').value = q ? q.stem : '';
    $('f-options').value = q ? (q.options || []).join('\n') : '';
    $('f-kp').value = q ? q.knowledge_point : '';
    $('f-enabled').value = q ? String(q.enabled) : '1';
    $('f-analysis').value = q ? q.analysis : '';
    $('modal-msg').textContent = '';
    refreshAnswerOptions(q ? q.answer : 0);
    $('modal').classList.remove('hidden');
  }

  function refreshAnswerOptions(selected) {
    var lines = $('f-options').value.split('\n').filter(function (s) { return s.trim(); });
    $('f-answer').innerHTML = lines.map(function (_, i) {
      return '<option value="' + i + '"' + (i === selected ? ' selected' : '') + '>' +
        'ABCDEFGH'.charAt(i) + '</option>';
    }).join('') || '<option value="0">A</option>';
  }

  function closeModal() { $('modal').classList.add('hidden'); }

  function saveQuestion() {
    var lines = $('f-options').value.split('\n').filter(function (s) { return s.trim(); });
    var body = {
      theme: $('f-theme').value,
      grade: $('f-grade').value,
      difficulty: parseInt($('f-difficulty').value, 10),
      stem: $('f-stem').value.trim(),
      options: lines,
      answer: parseInt($('f-answer').value, 10),
      knowledge_point: $('f-kp').value.trim() || '科普知识',
      analysis: $('f-analysis').value.trim(),
      enabled: parseInt($('f-enabled').value, 10)
    };
    if (!body.stem) { $('modal-msg').textContent = '题干不能为空'; return; }
    if (body.options.length < 2) { $('modal-msg').textContent = '至少需要 2 个选项'; return; }
    var call = state.editing ? put('/questions/' + state.editing, body) : post('/questions', body);
    call.then(function () {
      closeModal();
      loadQuestions(state.qPage);
    }).catch(function (e) { $('modal-msg').textContent = e.message; });
  }

  function removeQuestion(id) {
    if (!confirm('确定要删除题目 #' + id + ' 吗？删除后不可恢复。')) { return; }
    del('/questions/' + id).then(function () { loadQuestions(state.qPage); })
      .catch(function (e) { alert(e.message); });
  }

  // ---------- 用户管理 ----------
  function loadUsers(page) {
    state.uPage = page || 1;
    var kw = $('u-keyword').value.trim();
    return get('/users?page=' + state.uPage + '&size=10&keyword=' + encodeURIComponent(kw))
      .then(function (d) {
        var rows = (d.items || []).map(function (u) {
          return '<tr><td>' + u.id + '</td><td>' + esc(u.nickname) + '</td>' +
            '<td>' + (u.username ? esc(u.username) : '<span class="muted">游客</span>') + '</td>' +
            '<td>' + gradeLabel(u.grade) + '</td>' +
            '<td>' + u.total_xp + '</td><td>' + u.quiz_count + '</td><td>' + u.wrong_count + '</td>' +
            '<td>' + esc(u.created_at) + '</td>' +
            '<td>' + (u.status ? '<span class="tag tag-ok">正常</span>' : '<span class="tag tag-off">已停用</span>') +
            ' <button class="btn btn-primary btn-sm" onclick="Admin.openUserDetail(' + u.id + ')">答题详情</button>' +
            ' <button class="btn btn-ghost btn-sm" onclick="Admin.toggleUser(' + u.id + ',' +
            (u.status ? 0 : 1) + ')">' + (u.status ? '停用' : '启用') + '</button></td></tr>';
        }).join('');
        $('u-table').innerHTML = '<tr><th>ID</th><th>昵称</th><th>登录名</th><th>学段</th>' +
          '<th>经验值</th><th>闯关数</th><th>错题数</th><th>注册时间</th><th>状态与操作</th></tr>' +
          (rows || '<tr><td colspan="9" class="muted">还没有用户</td></tr>');
        renderPager('u-pager', d.total, d.page, d.size, loadUsers);
      }).catch(function (e) { alert(e.message); });
  }

  /** 单个学生的答题信息分类汇总（这页是老师最常用的） */
  function openUserDetail(userId) {
    var modal = $('user-modal');
    var body = $('user-detail');
    modal.classList.remove('hidden');
    body.innerHTML = '<p class="muted">正在读取该学生的答题记录…</p>';
    get('/users/' + userId).then(function (d) {
      var p = d.profile || {};
      var s = d.stats || {};
      var head = '<div class="detail-head">'
        + '<div><span class="h3">' + esc(p.nickname) + '</span>'
        + (p.username ? ' <span class="tag">' + esc(p.username) + '</span>'
                      : ' <span class="tag tag-off">游客</span>')
        + '<div class="muted">' + gradeLabel(p.grade) + ' · 注册于 ' + esc(p.created_at)
        + (p.last_login_at ? ' · 最近登录 ' + esc(p.last_login_at) : '') + '</div></div>'
        + '</div>';

      var cards = '<div class="cards detail-cards">'
        + card('经验值', p.total_xp, 'Lv.' + (Math.floor((p.total_xp || 0) / 50) + 1))
        + card('闯关次数', s.quiz_count, '已判分 ' + (s.answered_count || 0) + ' 次')
        + card('平均正确率', (s.avg_accuracy || 0) + '%', '按已判分的闯关计算')
        + card('错题数', s.wrong_count || 0, '待复习')
        + '</div>';

      // 1) 逐次闯关记录
      var sessions = (d.sessions || []).map(function (x) {
        var src = x.source === 'ai' ? 'AI 出题' : x.source === 'wrongbook' ? '错题重练' : '题库出题';
        return '<tr><td>' + esc(x.created_at) + '</td><td>' + esc(x.title) + '</td>'
          + '<td>' + gradeLabel(x.grade) + '</td><td><span class="tag">' + src + '</span></td>'
          + '<td>' + (x.total ? (x.correct + ' / ' + x.total) : '未提交') + '</td>'
          + '<td>' + (x.total ? (x.accuracy + '%') : '—') + '</td>'
          + '<td>' + (x.wrong_count || 0) + '</td>'
          + '<td>' + (x.duration_ms ? Math.round(x.duration_ms / 1000) + ' 秒' : '—') + '</td></tr>';
      }).join('');
      var sec1 = '<div class="panel"><div class="panel-head"><h3>一、逐次闯关记录</h3></div>'
        + '<table class="table"><tr><th>时间</th><th>主题</th><th>学段</th><th>来源</th>'
        + '<th>答对/总题</th><th>正确率</th><th>本次错题</th><th>用时</th></tr>'
        + (sessions || '<tr><td colspan="8" class="muted">还没有闯关记录</td></tr>')
        + '</table></div>';

      // 2) 薄弱知识点
      var points = (d.wrong_points || []).map(function (w) {
        return '<span class="chip">' + esc(w.kp || '科普知识') + ' · ' + w.questions + ' 题 / 错 '
          + (w.times || 0) + ' 次</span>';
      }).join('');
      var sec2 = '<div class="panel"><div class="panel-head"><h3>二、薄弱知识点排行</h3></div>'
        + '<div class="chips">' + (points || '<span class="muted">暂无错题</span>') + '</div></div>';

      // 3) 错题明细
      var items = (d.wrong_items || []).map(function (w) {
        return '<tr><td class="stem">' + esc(w.stem) + '</td>'
          + '<td><span class="tag">' + esc(w.knowledge_point || '科普知识') + '</span></td>'
          + '<td>' + (w.wrong_count || 1) + '</td><td>' + esc(w.last_wrong_at) + '</td>'
          + '<td class="stem muted">' + esc((w.analysis || '').slice(0, 60)) + '</td></tr>';
      }).join('');
      var sec3 = '<div class="panel"><div class="panel-head"><h3>三、错题明细</h3></div>'
        + '<table class="table"><tr><th>题干</th><th>知识点</th><th>错次</th><th>最近答错</th><th>解析</th></tr>'
        + (items || '<tr><td colspan="5" class="muted">还没有错题，说明这一轮掌握得不错</td></tr>')
        + '</table></div>';

      // 4) 上传的资料
      var docs = (d.knowledge || []).map(function (x) {
        return '<tr><td>' + esc(x.filename) + '</td><td>' + esc(x.file_type || 'txt') + '</td>'
          + '<td>' + Math.round((x.size_bytes || 0) / 1024) + ' KB</td>'
          + '<td>' + esc(x.created_at) + '</td></tr>';
      }).join('');
      var sec4 = '<div class="panel"><div class="panel-head"><h3>四、知识库资料</h3></div>'
        + '<table class="table"><tr><th>文件名</th><th>类型</th><th>大小</th><th>上传时间</th></tr>'
        + (docs || '<tr><td colspan="4" class="muted">没有上传过资料</td></tr>')
        + '</table></div>';

      body.innerHTML = head + cards + sec1 + sec2 + sec3 + sec4;
    }).catch(function (e) {
      body.innerHTML = '<p class="msg">读取失败：' + esc(e.message) + '</p>';
    });
  }

  function card(k, v, sub) {
    return '<div class="card"><div class="k">' + esc(k) + '</div><div class="v">' + esc(v)
      + '</div><div class="s">' + esc(sub || '') + '</div></div>';
  }

  function closeUserDetail() { $('user-modal').classList.add('hidden'); }

  function toggleUser(id, status) {
    post('/users/' + id + '/status?status=' + status).then(function () { loadUsers(state.uPage); })
      .catch(function (e) { alert(e.message); });
  }

  // ---------- 闯关记录 ----------
  function loadSessions(page) {
    state.sPage = page || 1;
    return get('/sessions?page=' + state.sPage + '&size=10').then(function (d) {
      var rows = (d.items || []).map(function (s) {
        var src = s.source === 'ai' ? 'AI 出题' : s.source === 'wrongbook' ? '错题重练' : '题库出题';
        return '<tr><td class="muted">' + esc(s.quiz_id) + '</td><td>' + esc(s.title) + '</td>' +
          '<td>' + esc(s.nickname) + '</td><td>' + gradeLabel(s.grade) + '</td>' +
          '<td><span class="tag">' + src + '</span></td>' +
          '<td>' + s.wrong_count + '</td><td>' + esc(s.created_at) + '</td></tr>';
      }).join('');
      $('s-table').innerHTML = '<tr><th>闯关 ID</th><th>标题</th><th>用户</th><th>学段</th>' +
        '<th>来源</th><th>错题</th><th>时间</th></tr>' +
        (rows || '<tr><td colspan="7" class="muted">还没有闯关记录</td></tr>');
      renderPager('s-pager', d.total, d.page, d.size, loadSessions);
    }).catch(function (e) { alert(e.message); });
  }

  // ---------- 操作日志 ----------
  function loadLogs() {
    return get('/logs?limit=60').then(function (d) {
      var rows = (d.logs || []).map(function (l) {
        return '<tr><td>' + esc(l.created_at) + '</td><td>' + esc(l.username) + '</td>' +
          '<td><span class="tag">' + esc(l.action) + '</span></td><td>' + esc(l.detail) + '</td></tr>';
      }).join('');
      $('l-table').innerHTML = '<tr><th>时间</th><th>操作人</th><th>动作</th><th>详情</th></tr>' +
        (rows || '<tr><td colspan="4" class="muted">暂无日志</td></tr>');
    }).catch(function (e) { alert(e.message); });
  }

  // ---------- 初始化 ----------
  function init() {
    $('login-form').addEventListener('submit', function (ev) {
      ev.preventDefault();
      $('login-msg').textContent = '';
      login($('username').value.trim(), $('password').value)
        .catch(function (e) { $('login-msg').textContent = e.message; });
    });
    $('logout').addEventListener('click', logout);
    $('f-options').addEventListener('input', function () { refreshAnswerOptions(0); });
    $('q-keyword').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { loadQuestions(1); }
    });
    $('u-keyword').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { loadUsers(1); }
    });
    window.addEventListener('hashchange', route);

    var saved = sessionStorage.getItem('kepu_admin_token');
    if (saved) {
      state.token = saved;
      state.admin = { username: sessionStorage.getItem('kepu_admin_name') || 'admin' };
      // 校验 Token 是否仍有效
      get('/me').then(showApp).catch(function () { logout(); });
    }
  }

  document.addEventListener('DOMContentLoaded', init);

  return {
    loadDashboard: loadDashboard, loadUsers: loadUsers, loadSessions: loadSessions,
    loadLogs: loadLogs, openQuestion: openQuestion, closeModal: closeModal,
    saveQuestion: saveQuestion, removeQuestion: removeQuestion, toggleUser: toggleUser,
    reloadQuestions: function () { loadQuestions(1); },
    openUserDetail: openUserDetail, closeUserDetail: closeUserDetail
  };
})();
