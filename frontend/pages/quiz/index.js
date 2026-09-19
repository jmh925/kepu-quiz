/**
 * 答题闯关页
 *
 * 一次一道题，点选项先选中，点「就选这个」才判分：
 * 判分、讲解全部在本地做（后端题目里已经带了 answer 下标与 analysis），
 * 所以孩子点完就能马上知道对错和原因，不用等网络。
 * 只有全部答完才把整份答卷交给后端算分。
 */
const api = require('../../utils/request');
const sound = require('../../utils/sound');

const app = getApp();

/** 选项字母：A B C D …（最多支持到 H） */
const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

/** 来源标签：据实标注，不谎称是 AI 生成的 */
const SOURCE_LABELS = {
  ai: '由 AI 生成',
  bank: '来自题库',
  wrongbook: '错题重练'
};

/** 连错两题就先安抚一下，不逼着孩子一直错下去 */
const STREAK_LIMIT = 2;

/** 连对几题开始给「连对」的额外奖励感 */
const COMBO_MIN = 2;

/**
 * 每题的建议思考时间（秒）。到点**不判负、不扣分**，只是把小科换成鼓励态、
 * 把倒计时改成累计用时，提醒一下可以作答了。
 * 这样既有游戏的节奏感，又不会给小朋友压力。
 */
const TIME_LIMIT = {
  primary_low: 45,
  primary_high: 40,
  junior: 35
};

/** 提交算分时按钮上的提示（和 wx.showLoading 的文案保持一致） */
const SUBMIT_TIP = '小科在算分…';

const nextTick = (function () {
  if (typeof wx !== 'undefined' && typeof wx.nextTick === 'function') {
    return wx.nextTick;
  }
  return function (fn) {
    setTimeout(fn, 0);
  };
})();

/** 逐题对比，算出当前连错了几题（结尾未作答的题不算） */
function computeStreak(questionStates) {
  let streak = 0;
  for (let i = 0; i < questionStates.length; i++) {
    const state = questionStates[i];
    if (!state || !state.judged || state.selected === -1) {
      continue;
    }
    if (state.isCorrect) {
      streak = 0;
    } else {
      streak = streak + 1;
    }
  }
  return streak;
}

/** 逐题对比，算出当前连对了几题（用于「连对」奖励） */
function computeCombo(questionStates) {
  let combo = 0;
  for (let i = questionStates.length - 1; i >= 0; i--) {
    const state = questionStates[i];
    if (!state || !state.judged || state.selected === -1) {
      continue;
    }
    if (state.isCorrect) {
      combo = combo + 1;
    } else {
      break;
    }
  }
  return combo;
}

/** 连对时的喝彩语，越连越热闹 */
function comboText(combo) {
  const words = {
    2: '连对两题！',
    3: '三连对，稳住！',
    4: '四连对，厉害了！',
    5: '五连对，太棒了！'
  };
  return words[combo] || (combo + ' 连对，停不下来！');
}

Page({
  data: {
    // 考卷
    hasQuiz: false,
    quizId: '',
    title: '',
    source: 'ai',
    sourceLabel: '由 AI 生成',
    gradeLabel: '',

    // 题目
    questions: [],
    total: 0,
    current: 0,
    currentQuestion: null,
    options: [],
    answered: 0,
    progress: 0,

    // 当前题作答状态
    selected: -1,
    judged: false,
    isCorrect: false,

    // 小科的状态与台词
    mascotState: 'idle',
    mascotCaption: '',
    encourage: false,

    // 闯关趣味层：倒计时 / 连对 / 奖励动画
    leftSeconds: 0,
    timeOver: false,
    elapsedSeconds: 0,
    combo: 0,
    comboShow: false,
    comboText: '',
    flash: '',

    // 提交
    submitting: false,
    submitTip: ''
  },

  // 内部状态：每题的选择与判分结果，以及整份答卷的下标数组
  questionStates: [],
  answers: [],
  streak: 0,
  startTime: 0,
  advanceDelay: 700,
  tickTimer: null,
  tickLeft: 0,
  tickElapsed: 0,
  flashTimer: null,
  comboHit: 0,

  onLoad: function () {
    this.startTime = Date.now();

    const quiz = app.globalData.lastQuiz;
    if (!quiz || !quiz.questions || quiz.questions.length === 0) {
      api.toast('还没有题目，先去选一个主题吧');
      setTimeout(function () {
        wx.navigateBack();
      }, 1200);
      return;
    }

    const questions = quiz.questions;
    const states = [];
    const answers = [];
    for (let i = 0; i < questions.length; i++) {
      states.push({ selected: -1, isCorrect: false, judged: false });
      answers.push(-1);
    }
    this.questionStates = states;
    this.answers = answers;
    this.streak = 0;

    this.setData({
      hasQuiz: true,
      quizId: quiz.quiz_id,
      title: quiz.title || '科普闯关',
      source: quiz.source || 'ai',
      sourceLabel: SOURCE_LABELS[quiz.source] || '由 AI 生成',
      gradeLabel: app.gradeLabel(),
      questions: questions,
      total: questions.length,
      current: 0,
      answered: 0,
      progress: 0,
      submitTip: SUBMIT_TIP
    });

    this.showQuestion(0);
  },

  /** 把第 index 题渲染出来（未作答状态） */
  showQuestion: function (index) {
    const question = this.data.questions[index];
    if (!question) {
      return;
    }
    const optionList = question.options || [];
    const options = [];
    for (let i = 0; i < optionList.length; i++) {
      options.push({
        text: optionList[i],
        key: LETTERS[i] || String(i + 1),
        state: '',
        no: i,
        chosen: false
      });
    }
    this.setData({
      current: index,
      currentQuestion: question,
      options: options,
      selected: -1,
      judged: false,
      isCorrect: false,
      mascotState: 'idle',
      mascotCaption: '',
      encourage: false,
      // 换题时把上一题的连对徽标与奖励气泡收掉
      comboShow: false,
      comboText: '',
      flash: ''
    });
    this.startTick();
  },

  /* ---------------- 每题计时：给节奏感，但不给压力 ----------------
   * 倒计时走完不判负、不扣分，只把小科换成鼓励态并把显示切换成累计用时。
   * 这是「游戏化」和「不吓到孩子」之间的取舍，宁可少一点紧张感。
   */
  timeLimit: function () {
    const rule = TIME_LIMIT[app.globalData.grade];
    return rule || TIME_LIMIT.primary_high;
  },

  startTick: function () {
    this.stopTick();
    this.tickLeft = this.timeLimit();
    this.tickElapsed = 0;
    this.setData({
      leftSeconds: this.tickLeft,
      timeOver: false,
      elapsedSeconds: 0
    });
    const self = this;
    this.tickTimer = setInterval(function () {
      if (self.data.judged) {
        // 判分之后只累计用时，不再倒计时
        self.tickElapsed = self.tickElapsed + 1;
        self.setData({ elapsedSeconds: self.tickElapsed });
        return;
      }
      self.tickLeft = self.tickLeft - 1;
      if (self.tickLeft > 0) {
        self.setData({ leftSeconds: self.tickLeft });
        return;
      }
      // 到点了：换成鼓励，不打断作答
      self.setData({
        leftSeconds: 0,
        timeOver: true,
        elapsedSeconds: 0
      });
      if (self.data.mascotState === 'idle') {
        self.setData({
          mascotState: 'encourage',
          mascotCaption: '想好了就选一个吧，小科陪着你'
        });
      }
    }, 1000);
  },

  stopTick: function () {
    if (this.tickTimer) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
  },

  onUnload: function () {
    this.stopTick();
    if (this.flashTimer) {
      clearTimeout(this.flashTimer);
      this.flashTimer = null;
    }
  },

  /** 奖励动画：让一个「+分 / 连对」小气泡飞一下 */
  playFlash: function (text) {
    const self = this;
    this.comboHit = this.comboHit + 1;
    const key = 'flash-' + this.comboHit;
    this.setData({ flash: '' }, function () {
      self.setData({ flash: text, flashKey: key });
    });
    if (this.flashTimer) {
      clearTimeout(this.flashTimer);
    }
    this.flashTimer = setTimeout(function () {
      self.setData({ flash: '' });
    }, 1100);
  },

  /** 选中一个选项；没点「就选这个」之前可以随便改 */
  onSelectOption: function (e) {
    if (this.data.judged) {
      return;
    }
    const index = Number(e.currentTarget.dataset.index);
    const options = this.data.options;
    if (!options || index < 0 || index >= options.length) {
      return;
    }
    const next = [];
    for (let i = 0; i < options.length; i++) {
      const item = options[i];
      next.push({
        text: item.text,
        key: item.key,
        no: item.no,
        chosen: i === index,
        state: i === index ? 'selected' : ''
      });
    }
    this.setData({
      options: next,
      selected: index
    });
    sound.tap();
  },

  /** 就地判分 + 立刻讲解 */
  onJudge: function () {
    if (this.data.judged) {
      this.onNext();
      return;
    }
    if (this.data.selected < 0) {
      api.toast('选一个你觉得对的，小科再看看');
      return;
    }

    const question = this.data.currentQuestion;
    if (!question) {
      return;
    }
    const correctIndex = Number(question.answer);
    const chosen = this.data.selected;
    const ok = chosen === correctIndex;

    // 先把判分结果落到内部状态，这样连错计数不会因为延迟而漏算
    const states = this.questionStates;
    states[this.data.current] = {
      selected: chosen,
      isCorrect: ok,
      judged: true
    };
    this.answers[this.data.current] = chosen;
    this.streak = computeStreak(states);
    const combo = computeCombo(states);

    const options = this.data.options;
    const next = [];
    for (let i = 0; i < options.length; i++) {
      const item = options[i];
      let cls = '';
      let chosenFlag = false;
      if (ok && i === correctIndex) {
        // 答对：直接展示解析，不必再重复一遍选项
        cls = 'correct';
        chosenFlag = true;
      } else if (!ok && i === chosen) {
        cls = 'wrong';
        chosenFlag = true;
      } else if (!ok && i === correctIndex) {
        cls = 'correct';
      }
      next.push({
        text: item.text,
        key: item.key,
        no: item.no,
        chosen: chosenFlag,
        state: cls
      });
    }

    this.setData({
      options: next,
      judged: true,
      isCorrect: ok,
      mascotState: ok ? 'correct' : 'wrong',
      mascotCaption: ok ? this.buildCorrectCaption(question) : '',
      encourage: this.streak >= STREAK_LIMIT,
      combo: combo,
      comboShow: ok && combo >= COMBO_MIN,
      comboText: ok && combo >= COMBO_MIN ? comboText(combo) : ''
    }, () => {
      this.refreshProgress();
    });

    // 即时反馈：声音 + 抖动 + 飞一个奖励气泡
    if (ok) {
      sound.correct(combo);
      if (combo >= 3) {
        sound.combo(combo);
      }
      this.playFlash(combo >= COMBO_MIN ? comboText(combo) : '答对啦 +2');
    } else {
      sound.wrong();
    }

    // 连错两题：换成鼓励态并给出出口
    if (this.streak >= STREAK_LIMIT) {
      const self = this;
      nextTick(function () {
        self.setData({
          mascotState: 'encourage',
          mascotCaption: '要不要先看看解析？'
        });
      });
    }
  },

  buildCorrectCaption: function (question) {
    const point = question && question.knowledge_point ? question.knowledge_point : '';
    if (point) {
      return '答对啦！你把「' + point + '」抓住了';
    }
    return '';
  },

  /** 进度按「已经判过的题数」推进 */
  refreshProgress: function () {
    let done = 0;
    for (let i = 0; i < this.questionStates.length; i++) {
      if (this.questionStates[i] && this.questionStates[i].judged) {
        done = done + 1;
      }
    }
    const total = this.data.total || 0;
    const percent = total ? Math.round((done / total) * 100) : 0;
    this.setData({
      answered: done,
      progress: percent
    });
  },

  /** 「下一题」/「看看我的报告」 */
  onNext: function () {
    if (this.data.submitting) {
      return;
    }
    const index = this.data.current;
    if (index < this.data.total - 1) {
      this.showQuestion(index + 1);
      return;
    }
    this.submitQuiz();
  },

  /** 交卷：把整份答卷和本次耗时交给后端算分 */
  submitQuiz: function () {
    if (this.data.submitting) {
      return;
    }
    const self = this;
    const duration = Date.now() - this.startTime;

    this.setData({
      submitting: true,
      submitTip: SUBMIT_TIP
    });
    api.loading(SUBMIT_TIP);

    api.post('/quiz/submit', {
      quiz_id: this.data.quizId,
      answers: this.answers,
      duration_ms: duration
    })
      .then(function (data) {
        app.globalData.lastResult = data;
        // 成功：loading 交给 onUnload 关掉，避免在「小科在算分…」还写着的时候
        // 屏幕上先空一下再跳页；submitting 保持 true 也挡住重复点击
        wx.navigateTo({ url: '/pages/report/index' });
      })
      .catch(function () {
        // 判分没成：关闭 loading、恢复按钮；答案全留着，直接再点一次就行。
        // 具体原因 request.js 已经用小科的口气提示过了，这里不重复弹。
        api.hideLoading();
        self.setData({ submitting: false });
      });
  },

  onUnload: function () {
    // 离开本页时把 loading 收干净，不留一个转圈卡在上一屏
    api.hideLoading();
  }
});
