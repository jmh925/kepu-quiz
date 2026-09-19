/**
 * 知识库（pages/knowledge）
 *
 * 把讲义或课外读本传上来，小科就能照着它出题。
 * 上传走 api.upload，列表 / 删除 / 照着资料出题都走统一的 api.*。
 */
const api = require('../../utils/request');
const app = getApp();

/** 文件后缀 → 展示用的类型名 */
function typeText(fileType, filename) {
  let t = fileType ? String(fileType).toLowerCase() : '';
  if (!t && filename && filename.indexOf('.') > -1) {
    t = filename.substring(filename.lastIndexOf('.') + 1).toLowerCase();
  }
  if (t === 'markdown') {
    t = 'md';
  }
  return t ? t.toUpperCase() : '资料';
}

/** 字节数 → B / KB / MB */
function sizeText(bytes) {
  const n = Number(bytes);
  if (!n || isNaN(n) || n <= 0) {
    return '大小还不清楚';
  }
  if (n < 1024) {
    return n + ' B';
  }
  if (n < 1024 * 1024) {
    return (Math.round(n / 1024 * 10) / 10) + ' KB';
  }
  return (Math.round(n / 1024 / 1024 * 10) / 10) + ' MB';
}

/** 文档状态 → 友好的说法 */
function statusText(status) {
  const s = status ? String(status).toLowerCase() : '';
  if (s === 'ready' || s === 'done' || s === 'parsed') {
    return '已经备好啦';
  }
  if (s === 'pending' || s === 'processing' || s === 'reading') {
    return '小科正在读';
  }
  return '已经收好';
}

function statusClass(status) {
  const s = status ? String(status).toLowerCase() : '';
  if (s === 'ready' || s === 'done' || s === 'parsed') {
    return 'pill pill-green';
  }
  if (s === 'pending' || s === 'processing' || s === 'reading') {
    return 'pill pill-yellow';
  }
  return 'pill';
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
    loading: true,
    uploading: false,
    usingId: '',        // 正在用它出题的文档，避免重复点击
    documents: [],
    loadOk: true        // 列表有没有顺利拿到
  },

  onShow: function () {
    this.loadDocuments();
  },

  onPullDownRefresh: function () {
    this.loadDocuments().then(function () {
      wx.stopPullDownRefresh();
    });
  },

  /** 拉取资料列表 */
  loadDocuments: function () {
    const that = this;
    this.setData({ loading: true });
    return api.get('/knowledge/documents')
      .then(function (data) {
        const list = (data && data.documents) || [];
        const documents = [];
        for (let i = 0; i < list.length; i++) {
          const d = list[i];
          documents.push({
            docId: d.doc_id,
            filename: d.filename || '这份资料',
            typeText: typeText(d.file_type, d.filename),
            sizeText: sizeText(d.size_bytes),
            statusText: statusText(d.status),
            statusClass: statusClass(d.status),
            timeText: shortTime(d.created_at)
          });
        }
        that.setData({ loading: false, loadOk: true, documents: documents });
      })
      .catch(function () {
        // 提示已由 request.js 统一给出，这里只把列表收成空态
        that.setData({ loading: false, loadOk: false, documents: [] });
      });
  },

  /** 上传资料：从聊天记录里挑一个文件 */
  onUpload: function () {
    const that = this;
    if (this.data.uploading) {
      return;
    }
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['txt', 'md', 'markdown', 'csv', 'pdf', 'docx'],
      success: function (res) {
        const files = res.tempFiles || [];
        if (!files.length) {
          return;
        }
        const file = files[0];
        if (!file.path) {
          api.toast('没拿到这份资料，要不要再试一次？');
          return;
        }
        that.setData({ uploading: true });
        wx.showLoading({ title: '小科正在读这份资料…', mask: true });
        api.upload('/knowledge/documents', file.path, 'file')
          .then(function () {
            api.hideLoading();
            that.setData({ uploading: false });
            api.toast('资料收好啦，可以拿它出题了', 'success');
            that.loadDocuments();
          })
          .catch(function (err) {
            api.hideLoading();
            that.setData({ uploading: false });
            if (err && err.code === 4001) {
              api.toast('这份资料小科读不懂，先试试 txt 或 md 文本文件吧');
            }
          });
      },
      fail: function () {
        // 用户自己取消了选择，不打扰
      }
    });
  },

  /** 用它出题：拿这份资料当参考资料生成一套题 */
  onUseDoc: function (e) {
    const docId = e.currentTarget.dataset.docId;
    const filename = e.currentTarget.dataset.docName || '这份资料';
    if (!docId || this.data.usingId) {
      return;
    }
    const that = this;
    this.setData({ usingId: docId });
    wx.showLoading({ title: '小科正在出题…', mask: true });

    api.post('/quiz/generate', {
      topic: filename,
      doc_id: docId,
      grade: app.globalData.grade
    })
      .then(function (data) {
        app.globalData.lastQuiz = data;
        app.globalData.lastResult = null;
        that.setData({ usingId: '' });
        api.hideLoading();
        wx.navigateTo({ url: '/pages/quiz/index' });
      })
      .catch(function () {
        that.setData({ usingId: '' });
        api.hideLoading();
      });
  },

  /** 删除一份资料：二次确认 */
  onDeleteDoc: function (e) {
    const docId = e.currentTarget.dataset.docId;
    const that = this;
    if (!docId) {
      return;
    }
    wx.showModal({
      title: '把这份资料拿走',
      content: '拿走之后就找不回来啦，确定吗？',
      confirmText: '拿走',
      cancelText: '先留着',
      success: function (res) {
        if (!res.confirm) {
          return;
        }
        wx.showLoading({ title: '小科正在收拾…', mask: true });
        api.del('/knowledge/documents/' + docId)
          .then(function () {
            api.hideLoading();
            api.toast('已经拿走啦', 'success');
            that.loadDocuments();
          })
          .catch(function () {
            api.hideLoading();
          });
      }
    });
  },

  /** 列表没拿到时的重试 */
  onRetry: function () {
    this.loadDocuments();
  }
});
