/**
 * 错题本（pages/wrong）
 *
 * 未登录：一句话说明 + 登录按钮。
 * 已登录：错题总数 + 薄弱知识点 + 「只练错题」 + 错题列表（可展开看解析）+ 清空。
 * 所有请求走 utils/request，时间字段直接截字符串显示，不引日期库。
 */
const api = require('../../utils/request');
const app = getApp();

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];

/** 选项下标 → 「B． 木星」；拿不到下标就返回空串，界面上不显示这一行 */
function optionText(options, index) {
  const list = options || [];
  const i = Number(index);
  if (isNaN(i) || i < 0 || i >= list.length) {
    return '';
  }
  return (LETTERS[i] || String(i + 1)) + '． ' + list[i];
}

/** 「2026-09-15 17:11:51」→「2026-09-15 17:11」 */
function shortTime(value) {
  const text = value ? String(value) : '';
  if (!text) {
    return '';
  }
  return text.length >= 16 ? text.substring(0, 16) : text;
}

Page({
  data: {
    isLogin: false,
    loading: true,
    logging: false,
    practicing: false,
    total: 0,
    weakPoints: [],
    questions: [],

    // 编辑态（错题本里的「改」）：一次只改一道
    editingIndex: -1,
    editStem: '',
    editKnowledge: '',
    editAnalysis: '',
    editAnswer: 0,
    editOptions: [],
    editKeys: LETTERS,
    saving: false
  },

  onShow: function () {
    // 答完题回到错题本时错题可能变了，每次显示都重新对一次
    this.refresh();
  },

  onPullDownRefresh: function () {
    this.refresh().then(function () {
      wx.stopPullDownRefresh();
    });
  },

  /** 拉取错题本总览；返回 Promise，便于下拉刷新收尾 */
  refresh: function () {
    const that = this;
    const logged = app.isLogin();
    this.setData({ isLogin: logged });

    if (!logged) {
      this.setData({ loading: false, total: 0, weakPoints: [], questions: [] });
      return Promise.resolve();
    }

    api.loading('小科正在翻错题本…');
    return api.get('/wrong/questions')
      .then(function (data) {
        const body = data || {};
        const list = body.questions || [];
        const questions = [];
        for (let i = 0; i < list.length; i++) {
          const q = list[i];
          questions.push({
            stem: q.stem || '这道题',
            knowledgePoint: q.knowledge_point || '科普知识',
            wrongCount: q.wrong_count || 1,
            rightAnswer: optionText(q.options, q.answer),
            yourAnswer: optionText(q.options, q.user_answer),
            analysis: q.analysis || '小科还在想更清楚的讲法，先把正确答案记下来吧',
            lastAt: shortTime(q.last_wrong_at),
            expanded: false,
            // 编辑时要回填的原始数据（选项要留完整列表，不能只留文字）
            options: q.options || [],
            answerIndex: typeof q.answer === 'number' ? q.answer : 0
          });
        }
        that.setData({
          loading: false,
          total: body.total === undefined ? questions.length : body.total,
          weakPoints: body.weak_points || [],
          questions: questions
        });
      })
      .catch(function () {
        // 提示已由 request.js 统一给出，这里只把界面收成空态
        that.setData({ loading: false, questions: [], weakPoints: [] });
      })
      .then(function () {
        api.hideLoading();
      });
  },

  /** 登录：wx.login 拿 code → 换 token → 存会话 → 刷新 */
  onLogin: function () {
    if (this.data.logging) {
      return;
    }
    const that = this;
    this.setData({ logging: true });

    wx.login({
      success: function (res) {
        if (!res.code) {
          that.setData({ logging: false });
          api.toast('没拿到登录凭证，要不要再试一次？');
          return;
        }
        api.post('/user/login', {
          code: res.code,
          nickname: '小科学家',
          grade: app.globalData.grade
        })
          .then(function (data) {
            const body = data || {};
            api.saveSession(body.token, body.user);
            app.globalData.user = body.user || null;
            that.setData({ logging: false, isLogin: true });
            api.toast('欢迎回来，小科学家！', 'success');
            that.refresh();
          })
          .catch(function () {
            that.setData({ logging: false });
          });
      },
      fail: function () {
        that.setData({ logging: false });
        api.toast('没成功，要不要再试一次？');
      }
    });
  },

  /** 展开 / 收起一道错题的讲解 */
  onToggleItem: function (e) {
    const index = Number(e.currentTarget.dataset.index);
    if (isNaN(index) || !this.data.questions[index]) {
      return;
    }
    const patch = {};
    patch['questions[' + index + '].expanded'] = !this.data.questions[index].expanded;
    this.setData(patch);
  },

  /** 只练错题：不用等大模型，秒级组一套练习卷 */
  onPractice: function () {
    if (!this.data.total || this.data.practicing) {
      return;
    }
    const that = this;
    this.setData({ practicing: true });
    wx.showLoading({ title: '小科正在组卷…', mask: true });

    api.post('/wrong/practice', { count: 8, grade: app.globalData.grade })
      .then(function (data) {
        app.globalData.lastQuiz = data;
        app.globalData.lastResult = null;
        that.setData({ practicing: false });
        api.hideLoading();
        wx.navigateTo({ url: '/pages/quiz/index' });
      })
      .catch(function () {
        that.setData({ practicing: false });
        api.hideLoading();
      });
  },

  /** 清空错题本：二次确认 */
  onClearWrong: function () {
    const that = this;
    wx.showModal({
      title: '清空错题本',
      content: '确定要清空吗？清空后错题就找不回来了',
      confirmText: '清空',
      cancelText: '先留着',
      success: function (res) {
        if (!res.confirm) {
          return;
        }
        wx.showLoading({ title: '小科正在收拾…', mask: true });
        api.del('/wrong/questions')
          .then(function () {
            api.hideLoading();
            api.toast('清空啦，轻装上阵！', 'success');
            that.refresh();
          })
          .catch(function () {
            api.hideLoading();
          });
      }
    });
  },

  /** 去闯关：回首页挑一个想探索的主题 */
  onGoQuiz: function () {
    wx.switchTab({ url: '/pages/index/index' });
  },

  /* ---------------- 错题本的「改」 ---------------- */

  /** 进入编辑态：把这道题当前的内容填进表单 */
  onStartEdit: function (e) {
    const index = Number(e.currentTarget.dataset.index);
    const item = this.data.questions[index];
    if (!item) {
      return;
    }
    this.setData({
      editingIndex: index,
      editStem: item.stem,
      editKnowledge: item.knowledgePoint,
      editAnalysis: item.analysis,
      editAnswer: item.answerIndex,
      editOptions: item.options
    });
  },

  /** 输入框变化：按 data-field 写回对应字段 */
  onEditInput: function (e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value || '';
    if (field === 'stem') {
      this.setData({ editStem: value });
    } else if (field === 'knowledge_point') {
      this.setData({ editKnowledge: value });
    } else if (field === 'analysis') {
      this.setData({ editAnalysis: value });
    }
  },

  /** 点某个选项 = 把它设为正确答案（错题本里常见要修的就是这个） */
  onPickAnswer: function (e) {
    const index = Number(e.currentTarget.dataset.index);
    if (!isNaN(index)) {
      this.setData({ editAnswer: index });
    }
  },

  onCancelEdit: function () {
    this.setData({ editingIndex: -1 });
  },

  /** 保存修改 */
  onSaveEdit: function () {
    const index = this.data.editingIndex;
    const item = this.data.questions[index];
    if (!item || this.data.saving) {
      return;
    }
    const stem = (this.data.editStem || '').trim();
    if (!stem) {
      api.toast('题干不能空着哦');
      return;
    }

    const that = this;
    this.setData({ saving: true });
    api.loading('小科正在记下改动…');

    const payload = { stem: item.stem, answer: Number(this.data.editAnswer) };
    if (stem !== item.stem) {
      payload.new_stem = stem;
    }
    if (this.data.editKnowledge !== item.knowledgePoint) {
      payload.knowledge_point = this.data.editKnowledge;
    }
    if (this.data.editAnalysis !== item.analysis) {
      payload.analysis = this.data.editAnalysis;
    }

    api.put('/wrong/questions', payload)
      .then(function () {
        api.hideLoading();
        that.setData({ saving: false, editingIndex: -1 });
        api.toast('改好了，这道题更清楚了', 'success');
        return that.refresh();
      })
      .catch(function () {
        api.hideLoading();
        that.setData({ saving: false });
      });
  },

  /** 删除单条错题：二次确认，避免手滑 */
  onDeleteItem: function (e) {
    const index = Number(e.currentTarget.dataset.index);
    const item = this.data.questions[index];
    if (!item) {
      return;
    }
    const that = this;
    wx.showModal({
      title: '这道题不留了？',
      content: '删掉之后这道题就不在错题本里了，练过的记录也跟着一起清掉。',
      confirmText: '删掉',
      cancelText: '再留着',
      confirmColor: '#FF8A65',
      success: function (res) {
        if (!res.confirm) {
          return;
        }
        api.loading('小科正在收拾…');
        // 题干里有中文与问号，走请求体传更稳妥，不依赖 URL 转义
        api.delBody('/wrong/questions/item', { stem: item.stem })
          .then(function () {
            api.hideLoading();
            api.toast('删掉啦', 'success');
            if (that.data.editingIndex === index) {
              that.setData({ editingIndex: -1 });
            }
            return that.refresh();
          })
          .catch(function () {
            api.hideLoading();
          });
      }
    });
  }
});
