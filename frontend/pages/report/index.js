/**
 * 复盘报告页（pages/report）
 *
 * 两种进入方式：
 *   1) 答题页跳过来：直接读 app.globalData.lastResult（含判题明细，可以展示「本次答题回顾」）
 *   2) 从「我的」历史记录跳过来：带 quiz_id，只调 /report/generate 拿报告，隐藏「本次答题回顾」
 *
 * 请求一律走 utils/request，页面里不出现 wx.request。
 */
const api = require('../../utils/request');
const app = getApp();

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];

/** 选项下标 → 「B． 木星」这样的可读文案 */
function optionText(options, index) {
  const list = options || [];
  const i = Number(index);
  if (isNaN(i) || i < 0 || i >= list.length) {
    return '这题先空着啦';
  }
  return (LETTERS[i] || String(i + 1)) + '． ' + list[i];
}

/** 正确率、掌握度统一成 0—100 的整数（后端给的是百分数，也兼容 0—1 的小数） */
function toScore(value) {
  let num = Number(value);
  if (!num || isNaN(num)) {
    return 0;
  }
  if (num <= 1) {
    num = num * 100;
  }
  num = Math.round(num);
  if (num < 0) {
    return 0;
  }
  if (num > 100) {
    return 100;
  }
  return num;
}

/** 按正确率切换吉祥物状态：≥80 通关 / ≥60 答对 / 其余 鼓励 */
function mascotByScore(score) {
  if (score >= 80) {
    return 'win';
  }
  if (score >= 60) {
    return 'correct';
  }
  return 'encourage';
}

/** 报告来源据实标注：ai → 由 AI 生成；rule → 本次由学习助手生成 */
function sourceText(source) {
  if (source === 'ai') {
    return '由 AI 生成';
  }
  if (source === 'rule') {
    return '本次由学习助手生成';
  }
  return '';
}

Page({
  data: {
    noData: false,          // 手上既没有判题结果，也没有报告可看
    fromHistory: false,     // 从历史记录进入
    hasResult: false,       // 有本次判题明细
    loading: false,         // 正在等复盘报告
    reportReady: false,     // 报告已经拿到
    quizId: '',
    accuracy: 0,            // 正确率（0—100）
    correct: 0,
    total: 0,
    mastery: 0,             // 掌握度（0—100）
    level: '',
    mascotState: 'encourage',
    summary: '',
    suggestion: '',
    weakPoints: [],
    reportSourceLabel: '',
    xpGained: 0,
    wrongAdded: 0,
    mastered: 0,
    wrongTotal: 0,
    wrongList: [],          // 本次答错的题，用于「本次答题回顾」
    reviewOpen: false
  },

  onLoad: function (options) {
    const opts = options || {};
    const quizId = opts.quiz_id ? String(opts.quiz_id) : '';

    if (quizId) {
      // 历史记录进来的：没有明细，只拿报告
      this.setData({ fromHistory: true, quizId: quizId });
      this.loadReport(quizId);
      return;
    }

    const result = app.globalData.lastResult;
    if (!result) {
      this.setData({ noData: true, mascotState: 'encourage' });
      return;
    }
    this.useResult(result);
    this.loadReport(result.quiz_id);
  },

  /** 把答题页留下的判题结果铺开：得分区 + 结算区 + 答错回顾 */
  useResult: function (result) {
    const details = result.details || [];
    const wrongList = [];
    for (let i = 0; i < details.length; i++) {
      const d = details[i];
      if (d.is_correct) {
        continue;
      }
      wrongList.push({
        key: 'w' + i + '_' + (d.id === undefined ? i : d.id),
        index: i + 1,
        stem: d.stem || '这道题',
        knowledgePoint: d.knowledge_point || '科普知识',
        yourAnswer: optionText(d.options, d.user_answer),
        rightAnswer: optionText(d.options, d.correct_answer),
        analysis: d.analysis || '先把正确答案记在小本本上，下次就能想起来啦'
      });
    }

    const accuracy = toScore(result.accuracy);
    this.setData({
      hasResult: true,
      noData: false,
      quizId: result.quiz_id || this.data.quizId,
      accuracy: accuracy,
      correct: result.correct || 0,
      total: result.total || 0,
      mastery: accuracy,
      mascotState: mascotByScore(accuracy),
      xpGained: result.xp_gained || 0,
      wrongAdded: result.wrong_added || 0,
      mastered: result.mastered || 0,
      wrongTotal: result.wrong_total || 0,
      wrongList: wrongList
    });
  },

  /** 请求复盘报告（可能较慢，界面上用小科思考的吉祥物陪着等） */
  loadReport: function (quizId) {
    const id = quizId || this.data.quizId;
    if (!id) {
      this.setData({ loading: false, reportReady: false });
      return;
    }
    const that = this;
    this.setData({ loading: true, reportReady: false });

    api.post('/report/generate', { quiz_id: id })
      .then(function (data) {
        const body = data || {};
        const report = body.report || {};
        const patch = {
          loading: false,
          reportReady: true,
          mastery: toScore(report.mastery),
          level: report.level || '',
          summary: report.summary || '',
          suggestion: report.suggestion || '',
          weakPoints: report.weak_points || [],
          reportSourceLabel: sourceText(report.source)
        };
        if (!that.data.hasResult) {
          // 从历史记录进来的：得分也从这份报告里取
          const accuracy = toScore(body.accuracy);
          patch.accuracy = accuracy;
          patch.correct = body.correct || 0;
          patch.total = body.total || 0;
          patch.mascotState = mascotByScore(accuracy);
        }
        if (!patch.summary) {
          patch.summary = '这一局的题目你已经过了一遍，把喜欢的知识点留在心里啦。';
        }
        that.setData(patch);
      })
      .catch(function () {
        // 提示已由 request.js 统一给出，这里只把界面状态恢复
        that.setData({ loading: false, reportReady: false });
      });
  },

  /** 报告没拿到时的重试入口 */
  onRetryReport: function () {
    this.loadReport(this.data.quizId);
  },

  /** 折叠 / 展开本次答题回顾 */
  onToggleReview: function () {
    this.setData({ reviewOpen: !this.data.reviewOpen });
  },

  /** 再来一局：回到首页重新选主题 */
  onAgain: function () {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  /** 去错题本：把这次答错的题再练一练 */
  onGoWrong: function () {
    wx.switchTab({ url: '/pages/wrong/index' });
  }
});
