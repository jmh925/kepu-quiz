/**
 * 首页 —— 去闯关
 *
 * 一条主线：选学段 → 写主题（或从快捷入口点一个）→ 开始出题
 * → 出题过程中用小科的分档台词 + 科普小知识轮播把等待变成学习
 * → 拿到题目后跳答题页。
 *
 * 大模型出题可能要 20—40 秒，所以「出题中」这一段必须有过程反馈，
 * 并且随时可以取消，不让孩子对着一个转圈干等。
 */
const api = require('../../utils/request');

const app = getApp();

/** 学段兜底项：拿不到 /grades 时也能正常选 */
const FALLBACK_GRADES = [
  { value: 'primary_low', short: '小学低年级', label: '小学低年级（1—3 年级）', emoji: '🌱' },
  { value: 'primary_high', short: '小学高年级', label: '小学高年级（4—6 年级）', emoji: '🚀' },
  { value: 'junior', short: '初中', label: '初中', emoji: '🔭' }
];

/** 主题快捷入口 */
const TOPIC_CHIPS = [
  { label: '天文', emoji: '🪐', topic: '太阳系' },
  { label: '地理', emoji: '🌏', topic: '地球的构造' },
  { label: '生物', emoji: '🌿', topic: '植物的光合作用' },
  { label: '物理', emoji: '🧲', topic: '力和运动' },
  { label: '化学', emoji: '⚗️', topic: '水的三态变化' },
  { label: '科技', emoji: '🤖', topic: '人工智能' }
];

/** 科普小知识：出题等待时轮播，把等待时间变成学习时间 */
const SCIENCE_FACTS = [
  '太阳的表面大约有 5500℃，而它核心的温度能超过 1500 万℃。',
  '蜂蜜几乎不会变质，考古学家在古埃及墓里找到过还能吃的蜂蜜。',
  '香蕉其实是有小种子的浆果，我们平时说的"籽"就是退化的种子。',
  '彩虹是阳光在水滴里折射又反射形成的，所以它永远是圆的。',
  '人类的鼻子能记住大约一万亿种不同的气味。',
  '章鱼有三颗心脏，游泳的时候主心脏会停下来，所以它更喜欢爬着走。',
  '竹子是世界上长得最快的植物之一，一天最多能长高将近一米。',
  '月亮每年都在慢慢远离地球，大约一年 3.8 厘米。',
  '闪电的温度能到 3 万℃，比太阳表面还要热好几倍。',
  '水熊虫小到看不见，却能在太空里活下来，是出了名的"生存高手"。'
];

/** 出题等待的三档台词（按等待时长切换，让孩子知道"在动、快好了"） */
const ASK_STAGES = [
  { seconds: 0, caption: '小科正在翻书找答案…' },
  { seconds: 8, caption: '正在认真出题，马上就好…' },
  { seconds: 20, caption: '快好啦，再等一下下～' }
];

/** 每 4 秒换一条科普小知识 */
const FACT_INTERVAL_MS = 4000;

Page({
  data: {
    // 学段
    grades: FALLBACK_GRADES,
    gradeValue: 'primary_high',
    gradeLabel: '小学高年级',

    // 主题输入
    topic: '',
    canAsk: false,

    // 来自知识库页：本次基于某份资料出题
    docId: '',
    docName: '',

    // 快捷入口
    chips: TOPIC_CHIPS,

    // 出题中
    asking: false,
    askElapsed: 0,
    askCaption: ASK_STAGES[0].caption,
    facts: SCIENCE_FACTS,
    factIndex: 0,
    currentFact: SCIENCE_FACTS[0]
  },

  // 计时器句柄不放进 data，避免无谓的 setData
  askTimers: [],
  askTicks: 0,

  onLoad: function (options) {
    const opts = options || {};
    const docId = opts.doc_id ? String(opts.doc_id) : '';
    const topic = opts.topic ? String(opts.topic) : '';
    this.setData({
      docId: docId,
      docName: topic,
      topic: topic,
      canAsk: topic.length > 0
    });
    this.syncGrade();
  },

  onShow: function () {
    // grades 是异步拉的，回来时再对齐一次
    this.syncGrade();
  },

  onUnload: function () {
    this.clearAskTimers();
  },

  onHide: function () {
    this.clearAskTimers();
    if (this.data.asking) {
      this.setData({
        asking: false,
        askElapsed: 0,
        askCaption: ASK_STAGES[0].caption
      });
    }
  },

  /* ---------------- 学段 ---------------- */

  /** 用 app.globalData.grades 刷新学段选项与当前标签 */
  syncGrade: function () {
    const fromApp = app.globalData.grades;
    const grades = (fromApp && fromApp.length) ? fromApp : FALLBACK_GRADES;
    let current = app.globalData.grade;
    if (!current) {
      current = grades[0].value;
    }
    this.setData({
      grades: grades,
      gradeValue: current,
      gradeLabel: app.gradeLabel()
    });
  },

  onPickGrade: function (e) {
    const value = e.currentTarget.dataset.value;
    if (!value || value === this.data.gradeValue) {
      return;
    }
    app.setGrade(value);
    this.setData({
      gradeValue: value,
      gradeLabel: app.gradeLabel()
    });
  },

  /* ---------------- 主题输入 ---------------- */

  onTopicInput: function (e) {
    const value = e.detail.value || '';
    this.setData({
      topic: value,
      canAsk: value.length > 0
    });
  },

  onTapChip: function (e) {
    const topic = e.currentTarget.dataset.topic || '';
    this.setData({
      topic: topic,
      canAsk: topic.length > 0
    });
  },

  /* ---------------- 出题 ---------------- */

  onStartAsk: function () {
    const topic = (this.data.topic || '').trim();
    if (!topic) {
      api.toast('先告诉小科你想学什么吧');
      this.setData({ canAsk: false });
      return;
    }

    this.setData({
      asking: true,
      askElapsed: 0,
      askCaption: ASK_STAGES[0].caption,
      currentFact: SCIENCE_FACTS[0],
      factIndex: 0
    });

    this.startAskTimers(0);

    const payload = {
      topic: topic,
      grade: app.globalData.grade
    };
    if (this.data.docId) {
      payload.doc_id = this.data.docId;
    }

    // 大模型出题可能较慢，给足 3 分钟；失败提示由 request.js 统一弹出
    api.post('/quiz/generate', payload, { timeout: 180000 })
      .then((data) => {
        this.clearAskTimers();
        app.globalData.lastQuiz = data;
        this.setData({
          asking: false,
          askElapsed: 0,
          askCaption: ASK_STAGES[0].caption
        });
        wx.navigateTo({ url: '/pages/quiz/index' });
      })
      .catch(() => {
        // 回到表单态，主题保留在输入框里，方便孩子改一改再来
        this.clearAskTimers();
        this.setData({
          asking: false,
          askElapsed: 0,
          askCaption: ASK_STAGES[0].caption
        });
      });
  },

  /** 启动两个定时器：分档台词（1 秒一跳）+ 科普轮播（4 秒一条） */
  startAskTimers: function (fromTicks) {
    this.clearAskTimers();
    const self = this;
    this.askTicks = (typeof fromTicks === 'number') ? fromTicks : this.askTicks;

    this.askTimers.push(setInterval(function () {
      self.askTicks = self.askTicks + 1;
      self.setData({ askElapsed: self.askTicks });
      let caption = ASK_STAGES[0].caption;
      for (let i = 0; i < ASK_STAGES.length; i++) {
        if (self.askTicks >= ASK_STAGES[i].seconds) {
          caption = ASK_STAGES[i].caption;
        }
      }
      if (caption !== self.data.askCaption) {
        self.setData({ askCaption: caption });
      }
    }, 1000));

    this.askTimers.push(setInterval(function () {
      const next = (self.data.factIndex + 1) % SCIENCE_FACTS.length;
      self.setData({
        factIndex: next,
        currentFact: SCIENCE_FACTS[next]
      });
    }, FACT_INTERVAL_MS));
  },

  clearAskTimers: function () {
    for (let i = 0; i < this.askTimers.length; i++) {
      clearInterval(this.askTimers[i]);
    }
    this.askTimers = [];
  },

  /** 取消出题：二次确认后回到表单态，输入的主题原样保留 */
  onCancelAsk: function () {
    const self = this;
    wx.showModal({
      title: '先歇一会儿？',
      content: '小科会停下出题，你输入的主题还留着。',
      confirmText: '停下',
      cancelText: '再等等',
      confirmColor: '#FF8A65',
      success: function (res) {
        if (res.confirm) {
          self.clearAskTimers();
          self.setData({
            asking: false,
            askElapsed: 0,
            askCaption: ASK_STAGES[0].caption
          });
          api.toast('好，想好了随时叫小科');
          return;
        }
        // 选择继续等待：把计时器重新接上，从已等待的秒数接着往下走
        self.startAskTimers(self.askTicks);
      },
      fail: function () {
        self.startAskTimers(self.askTicks);
      }
    });
  }
});
