/**
 * 小程序入口：静默登录、学段偏好、跨页数据中转。
 * 设计原则：未登录也能完整体验（游客模式），登录后才有经验值与错题本。
 */
const api = require('./utils/request');

App({
  globalData: {
    user: null,            // 登录用户信息
    grade: 'primary_high', // 当前学段：primary_low / primary_high / junior
    grades: [],            // 学段选项（来自后端 /grades）
    lastQuiz: null,        // 出题结果，供答题页读取
    lastResult: null       // 判题结果，供报告页读取
  },

  onLaunch: function () {
    this.restore();
    this.silentLogin();
    this.loadGrades();
  },

  /** 恢复本地缓存的会话与学段偏好 */
  restore: function () {
    try {
      const user = wx.getStorageSync('user');
      const grade = wx.getStorageSync('grade');
      if (user) {
        this.globalData.user = user;
      }
      if (grade) {
        this.globalData.grade = grade;
      }
    } catch (e) {
      // 缓存读取失败不影响启动
    }
  },

  /**
   * 静默登录：wx.login 拿 code 换 token。
   * 失败（未配置微信登录 / 网络异常）时进入游客模式，核心功能照常可用。
   */
  silentLogin: function () {
    const self = this;
    wx.login({
      success: function (res) {
        if (!res.code) {
          return;
        }
        api.post('/user/login', { code: res.code, nickname: '小科学家' }, { silent: true })
          .then(function (data) {
            api.saveSession(data.token, data.user);
            self.globalData.user = data.user;
          })
          .catch(function () {
            // 游客模式：不阻断任何页面
          });
      },
      fail: function () {
        // 游客模式
      }
    });
  },

  /** 拉取学段选项，供首页选择 */
  loadGrades: function () {
    const self = this;
    api.get('/grades', { silent: true })
      .then(function (data) {
        self.globalData.grades = (data && data.grades) || [];
        let saved = '';
        try {
          saved = wx.getStorageSync('grade');
        } catch (e) {
          saved = '';
        }
        if (saved) {
          self.globalData.grade = saved;
        } else if (data && data.default) {
          self.globalData.grade = data.default;
        }
      })
      .catch(function () {
        // 拉不到就用默认学段，不影响使用
      });
  },

  /** 设置并持久化学段 */
  setGrade: function (grade) {
    this.globalData.grade = grade;
    try {
      wx.setStorageSync('grade', grade);
    } catch (e) {}
  },

  /** 学段的中文短名，用于界面展示 */
  gradeLabel: function () {
    const list = this.globalData.grades || [];
    for (let i = 0; i < list.length; i++) {
      if (list[i].value === this.globalData.grade) {
        return list[i].short || list[i].label;
      }
    }
    return '小学高年级';
  },

  /** 是否已登录（游客模式下为 false） */
  isLogin: function () {
    return !!api.getToken();
  },

  /* ---------------- 成长体系：把经验值换算成小朋友看得懂的「等级 + 进度」 ----------------
   * 只做本地换算，不改后端协议：经验值来自 /user/profile 与 /quiz/submit 的 total_xp。
   * 每 50 点一级，进度条满就升一级，给孩子一个一直够得着的短期目标。
   */
  LEVEL_XP: 50,

  /** 由累计经验值算出等级与当前进度 */
  levelInfo: function (totalXp) {
    const unit = this.LEVEL_XP;
    const xp = Math.max(0, Number(totalXp) || 0);
    const level = Math.floor(xp / unit) + 1;
    const inLevel = xp % unit;
    return {
      level: level,
      inLevel: inLevel,
      need: unit,
      remain: unit - inLevel,
      percent: Math.round((inLevel / unit) * 100)
    };
  },

  /** 等级称号：让「升到几级」有意义，而不是干巴巴一个数字 */
  levelTitle: function (level) {
    const titles = ['科学小新芽', '好奇心学徒', '问题小侦探', '实验小助手',
                    '知识小达人', '探索小队长', '科学小博士'];
    const index = Math.max(0, Math.min(titles.length - 1, (Number(level) || 1) - 1));
    return titles[index];
  },

  /** 音效开关（在「我的」页可切换） */
  soundOn: function () {
    try {
      const saved = wx.getStorageSync('sound_on');
      return saved === '' || saved === undefined ? true : !!saved;
    } catch (e) {
      return true;
    }
  },

  setSoundOn: function (on) {
    try {
      wx.setStorageSync('sound_on', !!on);
    } catch (e) {
      // 存不上也不影响本次使用
    }
  }
});
