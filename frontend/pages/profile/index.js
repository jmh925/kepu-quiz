/**
 * 我的（pages/profile）
 *
 * 游客模式：只展示一句说明和一个登录按钮，闯关功能不受影响。
 * 登录后：昵称、累计经验值、错题数、当前学段、薄弱知识点、历史闯关。
 *
 * 时间字段 created_at 形如 2026-09-15 17:11:51，直接截字符串显示，不引日期库。
 */
const api = require('../../utils/request');
const app = getApp();

const GRADE_TEXT = {
  primary_low: '小学低年级',
  primary_high: '小学高年级',
  junior: '初中'
};

const SOURCE_TEXT = {
  ai: '由 AI 生成',
  bank: '来自题库',
  wrongbook: '错题重练'
};

/** 学段取值 → 中文短名；优先用后端下发的 grades，拿不到就用本地兜底表 */
function gradeText(value) {
  if (!value) {
    return '';
  }
  const list = app.globalData.grades || [];
  for (let i = 0; i < list.length; i++) {
    if (list[i].value === value) {
      return list[i].short || list[i].label;
    }
  }
  return GRADE_TEXT[value] || '';
}

/** 出题来源据实标注 */
function sourceText(value) {
  return SOURCE_TEXT[value] || '';
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
    nickname: '',
    totalXp: 0,
    wrongCount: 0,
    gradeLabel: '',
    weakPoints: [],
    sessions: []
  },

  onShow: function () {
    // 从登录页 / 答题页回来时状态可能变了，每次显示都对齐一次
    this.refresh();
  },

  onPullDownRefresh: function () {
    this.refresh().then(function () {
      wx.stopPullDownRefresh();
    });
  },

  /** 拉取个人中心数据；返回 Promise，便于下拉刷新收尾 */
  refresh: function () {
    const that = this;
    const logged = app.isLogin();
    this.setData({ isLogin: logged, gradeLabel: app.gradeLabel() });

    if (!logged) {
      this.setData({
        loading: false,
        nickname: '',
        totalXp: 0,
        wrongCount: 0,
        weakPoints: [],
        sessions: []
      });
      return Promise.resolve();
    }

    api.loading('小科正在整理…');
    return api.get('/user/profile')
      .then(function (data) {
        const body = data || {};
        const user = body.user || {};
        const list = body.sessions || [];
        const sessions = [];
        for (let i = 0; i < list.length; i++) {
          const s = list[i];
          sessions.push({
            quizId: s.quiz_id,
            title: s.title || '这一局闯关',
            gradeLabel: gradeText(s.grade),
            sourceLabel: sourceText(s.source),
            timeText: shortTime(s.created_at)
          });
        }
        that.setData({
          loading: false,
          nickname: user.nickname || '小科学家',
          totalXp: user.total_xp || 0,
          gradeLabel: gradeText(user.grade) || app.gradeLabel(),
          wrongCount: body.wrong_count || 0,
          weakPoints: body.weak_points || [],
          sessions: sessions
        });
      })
      .catch(function () {
        // 提示已由 request.js 统一给出，这里只恢复界面
        that.setData({ loading: false, sessions: [], weakPoints: [] });
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

  /** 点历史闯关 → 看那一局的复盘报告 */
  onOpenSession: function (e) {
    const quizId = e.currentTarget.dataset.quizId;
    if (!quizId) {
      return;
    }
    wx.navigateTo({ url: '/pages/report/index?quiz_id=' + quizId });
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
            api.toast('错题本清空啦，重新出发！', 'success');
            that.refresh();
          })
          .catch(function () {
            api.hideLoading();
          });
      }
    });
  }
});
