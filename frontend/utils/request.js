/**
 * 统一请求封装：自动附带 JWT、统一拆包、统一错误提示。
 * 页面里不要直接调用 wx.request，一律走这里，便于集中处理鉴权与错误。
 */
const { BASE_URL } = require('../config');

const TOKEN_KEY = 'token';
const USER_KEY = 'user';

function getToken() {
  try {
    return wx.getStorageSync(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
}

function saveSession(token, user) {
  try {
    if (token) wx.setStorageSync(TOKEN_KEY, token);
    if (user) wx.setStorageSync(USER_KEY, user);
  } catch (e) {}
}

function clearSession() {
  try {
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(USER_KEY);
  } catch (e) {}
}

function toast(message, icon) {
  wx.showToast({
    title: message || '没成功，要不要再试一次？',
    icon: icon || 'none',
    duration: 2000
  });
}

function loading(title) {
  wx.showLoading({ title: title || '小科正在准备…', mask: true });
}

function hideLoading() {
  wx.hideLoading();
}

/**
 * 发起请求
 * @param {string} method  GET/POST/PUT/DELETE
 * @param {string} url     以 / 开头，例如 /quiz/generate
 * @param {object} data    请求体
 * @param {object} options { silent: 不弹错误提示, timeout: 超时毫秒 }
 */
function request(method, url, data, options) {
  const opts = options || {};
  return new Promise(function (resolve, reject) {
    const header = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) {
      header.Authorization = 'Bearer ' + token;
    }
    wx.request({
      url: BASE_URL + url,
      method: method,
      data: data || {},
      header: header,
      timeout: opts.timeout || 60000,
      success: function (res) {
        const body = res.data || {};
        if (res.statusCode >= 200 && res.statusCode < 300 && body.code === 0) {
          resolve(body.data);
          return;
        }
        const err = new Error(body.message || ('这一步没走通（' + res.statusCode + '），再试一次吧'));
        err.code = body.code;
        err.statusCode = res.statusCode;
        if (res.statusCode === 401) {
          clearSession();
        }
        if (!opts.silent) {
          toast(err.message);
        }
        reject(err);
      },
      fail: function () {
        const err = new Error('连不上服务器，检查一下后端是否已启动～');
        err.code = -1;
        if (!opts.silent) {
          toast(err.message);
        }
        reject(err);
      }
    });
  });
}

/** 上传文件（知识库用），返回 Promise */
function upload(url, filePath, name, formData) {
  return new Promise(function (resolve, reject) {
    const header = {};
    const token = getToken();
    if (token) {
      header.Authorization = 'Bearer ' + token;
    }
    wx.uploadFile({
      url: BASE_URL + url,
      filePath: filePath,
      name: name || 'file',
      formData: formData || {},
      header: header,
      timeout: 120000,
      success: function (res) {
        let body = {};
        try {
          body = JSON.parse(res.data);
        } catch (e) {
          body = {};
        }
        if (res.statusCode >= 200 && res.statusCode < 300 && body.code === 0) {
          resolve(body.data);
          return;
        }
        const err = new Error(body.message || '这份资料小科没读进去，换个小一点的文本文件试试');
        err.code = body.code;
        toast(err.message);
        reject(err);
      },
      fail: function () {
        const err = new Error('上传没成功，检查一下网络～');
        toast(err.message);
        reject(err);
      }
    });
  });
}

/** 删除但需要带请求体（题干里有中文与问号时比塞进 URL 稳妥） */
function delBody(url, data, options) {
  return new Promise(function (resolve, reject) {
    const header = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) {
      header.Authorization = 'Bearer ' + token;
    }
    wx.request({
      url: BASE_URL + url,
      method: 'DELETE',
      data: data || {},
      header: header,
      timeout: (options && options.timeout) || 60000,
      success: function (res) {
        const body = res.data || {};
        if (res.statusCode >= 200 && res.statusCode < 300 && body.code === 0) {
          resolve(body.data);
          return;
        }
        const err = new Error(body.message || '没删成，要不要再试一次？');
        err.code = body.code;
        if (!(options && options.silent)) {
          toast(err.message);
        }
        reject(err);
      },
      fail: function () {
        const err = new Error('连不上服务器，检查一下后端是否已启动～');
        err.code = -1;
        if (!(options && options.silent)) {
          toast(err.message);
        }
        reject(err);
      }
    });
  });
}

module.exports = {
  get: function (url, options) {
    return request('GET', url, null, options);
  },
  post: function (url, data, options) {
    return request('POST', url, data, options);
  },
  put: function (url, data, options) {
    return request('PUT', url, data, options);
  },
  del: function (url, options) {
    return request('DELETE', url, null, options);
  },
  delBody: delBody,
  upload: upload,
  getToken: getToken,
  saveSession: saveSession,
  clearSession: clearSession,
  toast: toast,
  loading: loading,
  hideLoading: hideLoading
};
