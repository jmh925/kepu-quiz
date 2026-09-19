/**
 * 小科 —— 纯 CSS 绘制的吉祥物组件。
 * 不引用任何图片资源；用圆形脑袋 + 两只眼睛 + 一张嘴，
 * 通过 state 改变眼睛与嘴的形状/配色来传达情绪。
 *
 * 用法：<mascot state="thinking" size="md" caption=""></mascot>
 * caption 留空时自动使用该状态的默认台词，保证语气统一。
 */
const DEFAULT_CAPTIONS = {
  idle: '我是小科，陪你一起探索科学',
  thinking: '小科正在思考…',
  correct: '答对啦，你真棒！',
  wrong: '差一点点，再看看解析？',
  encourage: '别着急，慢慢来～',
  win: '这一关通过啦！'
};

const DEFAULT_STATE = 'idle';

Component({
  options: {
    addGlobalClass: true
  },

  properties: {
    // idle / thinking / correct / wrong / encourage / win
    state: {
      type: String,
      value: DEFAULT_STATE
    },
    // sm / md / lg
    size: {
      type: String,
      value: 'md'
    },
    // 留空则使用该状态的默认台词
    caption: {
      type: String,
      value: ''
    }
  },

  data: {
    shownCaption: DEFAULT_CAPTIONS[DEFAULT_STATE]
  },

  lifetimes: {
    attached: function () {
      this.refreshCaption();
    }
  },

  observers: {
    'state, caption': function () {
      this.refreshCaption();
    }
  },

  methods: {
    /** 依据 state 与 caption 计算最终台词 */
    refreshCaption: function () {
      const state = this.data.state || DEFAULT_STATE;
      const own = this.data.caption;
      const fallback = DEFAULT_CAPTIONS[state] || DEFAULT_CAPTIONS[DEFAULT_STATE];
      const text = (typeof own === 'string' && own.length) ? own : fallback;
      if (text !== this.data.shownCaption) {
        this.setData({ shownCaption: text });
      }
    }
  }
});
