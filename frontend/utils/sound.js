/**
 * 声音与震动反馈（纯代码合成，不引入任何音频文件）
 *
 * 为什么不用 mp3：仓库里没有音频资源，而「答对/答错给个声音」对小朋友的
 * 即时反馈很重要。小程序提供 wx.createWebAudioContext()（基础库 2.19+），
 * 可以直接用振荡器合成短音，省掉资源文件，音量与音色也可控。
 *
 * 三道保险，任何一道不满足就静默降级，绝不影响答题：
 * 1. 环境不支持 WebAudio → 只留震动；
 * 2. 合成过程抛异常 → 静默吞掉（声音是锦上添花，不能让它把流程搞挂）；
 * 3. 用户在「我的」页关掉音效 → 不再出声。
 */
const MUTE_KEY = 'sound_on';

let ctx = null;
let ctxFailed = false;

function isSupported() {
  return typeof wx !== 'undefined' && typeof wx.createWebAudioContext === 'function';
}

/** 是否开启音效（默认开启；关掉后连振动也一起关，避免在课堂上尴尬） */
function enabled() {
  try {
    const saved = wx.getStorageSync(MUTE_KEY);
    return saved === '' || saved === undefined ? true : !!saved;
  } catch (e) {
    return true;
  }
}

function setEnabled(on) {
  try {
    wx.setStorageSync(MUTE_KEY, !!on);
  } catch (e) {
    // 存不上就算了，下次仍按默认开启
  }
}

function context() {
  if (ctx || ctxFailed) {
    return ctx;
  }
  if (!isSupported()) {
    ctxFailed = true;
    return null;
  }
  try {
    ctx = wx.createWebAudioContext();
  } catch (e) {
    ctxFailed = true;
    ctx = null;
  }
  return ctx;
}

/**
 * 播放一个音（正弦/三角波 + 指数衰减包络）
 * @param {number} freq  频率 Hz
 * @param {number} start 相对现在的开始时间（秒）
 * @param {number} dur   持续时长（秒）
 * @param {number} gain  音量 0~1
 * @param {string} type  波形
 */
function tone(freq, start, dur, gain, type) {
  const ac = context();
  if (!ac) {
    return;
  }
  const t0 = ac.currentTime + (start || 0);
  const osc = ac.createOscillator();
  const amp = ac.createGain();
  osc.type = type || 'sine';
  osc.frequency.setValueAtTime(freq, t0);
  // 指数衰减，听起来像「叮」而不是「嘟——」
  amp.gain.setValueAtTime(0.0001, t0);
  amp.gain.exponentialRampToValueAtTime(gain || 0.18, t0 + 0.012);
  amp.gain.exponentialRampToValueAtTime(0.0001, t0 + (dur || 0.18));
  osc.connect(amp);
  amp.connect(ac.destination);
  osc.start(t0);
  osc.stop(t0 + (dur || 0.18) + 0.02);
}

function vibrate(kind) {
  if (!enabled() || typeof wx === 'undefined' || typeof wx.vibrateShort !== 'function') {
    return;
  }
  try {
    wx.vibrateShort({ type: kind || 'light' });
  } catch (e) {
    // 部分机型不支持 type 参数，忽略
  }
}

/** 点选选项：很轻的一下「嗒」 */
function tap() {
  if (!enabled()) {
    return;
  }
  tone(660, 0, 0.06, 0.07, 'triangle');
  vibrate('light');
}

/**
 * 答对：向上两个音（大三度），连对越多音越高，形成「越来越爽」的正反馈。
 * @param {number} combo 当前连对次数（1 起）
 */
function correct(combo) {
  if (!enabled()) {
    vibrate('light');
    return;
  }
  const step = Math.max(0, Math.min(4, (combo || 1) - 1));
  const base = 660 * Math.pow(1.122, step);       // 每连对一次升约两个半音
  tone(base, 0, 0.12, 0.16, 'sine');
  tone(base * 1.25, 0.09, 0.18, 0.14, 'sine');
  vibrate('light');
}

/** 差一点点：一声柔和的下行音，不用刺耳的声音 */
function wrong() {
  if (!enabled()) {
    vibrate('medium');
    return;
  }
  tone(392, 0, 0.16, 0.12, 'triangle');
  tone(311, 0.12, 0.22, 0.10, 'triangle');
  vibrate('medium');
}

/** 整关通过：小段上行琶音 */
function win() {
  if (!enabled()) {
    vibrate('light');
    return;
  }
  const notes = [523.25, 659.25, 783.99, 1046.5];
  for (let i = 0; i < notes.length; i++) {
    tone(notes[i], i * 0.11, 0.26, 0.15, 'sine');
  }
  vibrate('light');
}

/** 连对 3 题以上额外来一声，给「连击」一个听觉标记 */
function combo(level) {
  if (!enabled() || !level || level < 3) {
    return;
  }
  tone(1200, 0, 0.09, 0.10, 'sine');
  tone(1600, 0.07, 0.12, 0.09, 'sine');
}

module.exports = {
  enabled: enabled,
  setEnabled: setEnabled,
  tap: tap,
  correct: correct,
  wrong: wrong,
  win: win,
  combo: combo,
  isSupported: isSupported
};
