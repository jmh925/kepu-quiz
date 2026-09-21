# 前端开发规范（微信小程序原生框架）

> 本文件是页面实现的唯一依据。所有页面必须严格遵守，否则会出现风格与接口不一致。
> 后端接口地址：`frontend/config.js` 里的 `BASE_URL`（默认 `http://127.0.0.1:8000/api/v1`）。

---

## 一、硬性约束

1. **技术**：微信小程序原生框架（`app.json` / `.wxml` / `.wxss` / `.js`）。**不使用** npm、不使用 Taro/React/Vue、不引入任何第三方库、不引入任何图片资源（图标一律用 emoji 或 CSS 绘制）。
2. **模块化**：使用 CommonJS（`require` / `module.exports`）。可用 `let/const`、箭头函数、模板字符串、Promise。**禁止**使用可选链 `?.` 和空值合并 `??`（兼容性考虑）。
3. **请求**：一律走 `utils/request.js`，**禁止**在页面里直接调用 `wx.request`：
   ```js
   const api = require('../../utils/request');
   api.get('/grades');
   api.post('/quiz/generate', { topic: '太阳系', grade: 'primary_high' });
   api.del('/knowledge/documents/' + docId);
   api.upload('/knowledge/documents', tempFilePath, 'file');
   ```
   `request` 已统一处理 JWT 附加、响应拆包、错误 toast。成功时 Promise 直接 resolve 业务 `data`，失败时 reject 并已弹出提示（页面只需 `catch` 里恢复 loading 状态即可，不要重复 toast）。
4. **全局状态**：`const app = getApp();` 使用 `app.globalData.grade`（当前学段）、`app.globalData.grades`（学段选项）、`app.setGrade(v)`、`app.gradeLabel()`、`app.isLogin()`、`app.globalData.lastQuiz`、`app.globalData.lastResult`。
5. **每个页面 4 个文件**：`index.js` / `index.wxml` / `index.wxss` / `index.json`。`index.json` 若用到吉祥物组件需声明：
   ```json
   { "usingComponents": { "mascot": "../../components/mascot/mascot" } }
   ```
   不使用时写 `{ "usingComponents": {} }`。

---

## 二、视觉规范（面向中小学生）

**只用 `app.wxss` 里定义的 CSS 变量，不要写死颜色值。**

| 变量 | 值 | 用途 |
| --- | --- | --- |
| `--c-primary` | #4FC3F7 | 主色（天蓝） |
| `--c-primary-deep` | #0288D1 | 主色深（文字/描边） |
| `--c-yellow` | #FFCA28 | 强调 |
| `--c-green` | #66BB6A | 答对 |
| `--c-orange` | #FF8A65 | **答错（不用纯红）** |
| `--c-text` | #2F3E4E | 主文字 |
| `--c-sub` | #7B8A99 | 次要文字 |
| `--c-line` | #E3EEF7 | 分隔线 |
| `--c-bg` | #F7FBFF | 页面背景 |
| `--r-card` | 24rpx | 卡片圆角 |
| `--r-pill` | 999rpx | 胶囊圆角 |

**可直接复用的全局类**：`.page` `.card` `.card-title` `.btn` `.btn-primary` `.btn-ghost` `.btn-warm` `.btn-sm` `.pill` `.pill-yellow` `.pill-green` `.pill-orange` `.tag` `.empty` `.divider` `.input` `.option` `.option-key` `.option.selected` `.option.correct` `.option.wrong` `.progress` `.progress-inner` `.row` `.between` `.center` `.wrap` `.grow` `.h1` `.h2` `.h3` `.body` `.muted`。

**尺寸底线**：
- 题干字号 ≥ `36rpx`（建议 38rpx），正文 ≥ `32rpx`，次要信息 ≥ `28rpx`
- 可点按元素高度 ≥ `88rpx`（按钮建议 96rpx），点按区域不足时用 padding 撑开
- 卡片圆角 ≥ `20rpx`，**禁止直角卡片和直角按钮**
- 答错反馈用暖橙 `--c-orange`，**禁止用纯红 `#FF0000` 之类的颜色**
- 页面左右内边距 `28rpx`

---

## 三、文案规范（这是「性格」的核心，必须遵守）

App 的性格是：**一个叫「小科」的科学小伙伴**，耐心、爱鼓励、从不说教。

| 规则 | ❌ 不要这样写 | ✅ 要这样写 |
| --- | --- | --- |
| 人称 | 「用户未登录」「系统提示」 | 「你来啦」「小科提醒你」 |
| 加载 | 「加载中…」 | 「小科正在翻书找答案…」 |
| 答错 | 「回答错误」「错误」 | 「差一点点！」「再试一次？」 |
| 称呼孩子 | 「该用户」「学生」 | 「你」「小科学家」 |
| 失败 | 「操作失败」 | 「没成功，要不要再试一次？」 |
| 排名 | 「你排第 87 名」 | 「你比上次多答对 2 题，继续加油！」 |
| 按钮 | 「提交」「确定」 | 「就选这个」「看看我的报告」 |
| 空状态 | 「暂无数据」 | 「还没有错题，去闯一关吧！」 |

- 反馈公式：**先具体肯定 → 再讲知识点 → 最后给下一步**。
- 全篇不出现「错误」「失败」「倒数」「排名」这类词。
- 连续答错要有出口（提示「要不要先看看解析？」），绝不逼着孩子一直错下去。

---

## 四、吉祥物组件用法

```xml
<mascot state="thinking" size="md" caption=""></mascot>
```
- `state`：`idle` 待机 / `thinking` 思考中 / `correct` 答对 / `wrong` 差一点点 / `encourage` 鼓励 / `win` 通关
- `size`：`sm` / `md` / `lg`
- `caption`：留空则自动使用该状态的默认台词（推荐留空，保证语气统一）

---

## 五、后端接口契约（必须严格按此调用）

统一响应体：`{ code, message, data }`；`code === 0` 为成功。`request.js` 已拆包，页面拿到的是 `data`。

| 方法 | 路径 | 入参 | 返回 data |
| --- | --- | --- | --- |
| GET | `/grades` | — | `{ grades: [{value,label,short,count}], default }` |
| POST | `/user/login` | `{code?, nickname?, grade?}` | `{ token, user:{id,nickname,avatar_url,total_xp,grade} }` |
| GET | `/user/profile` | — | `{ user:{id,nickname,avatar_url,total_xp,grade}, sessions:[{quiz_id,title,grade,source,created_at}], wrong_count, weak_points:[{knowledge_point,questions,wrong_times}] }` |
| POST | `/quiz/generate` | `{topic, count?, doc_id?, grade?}` | `{ quiz_id, title, source, grade, grade_label, count, hit_chunks, dropped_unsafe, dropped_long, questions:[...] }` |
| POST | `/quiz/submit` | `{quiz_id, answers:[int], duration_ms?}` | `{ quiz_id, total, correct, accuracy, xp_gained, wrong_added, mastered, wrong_total, weak_points:[string], details:[...] }` |
| POST | `/report/generate` | `{quiz_id}` | `{ quiz_id, total, correct, accuracy, report:{mastery,level?,weak_points:[string],summary,suggestion,source,grade} }` |
| POST | `/knowledge/documents` | multipart，字段名 `file` | `{ doc_id, filename, chunks, file_type, size_bytes }` |
| GET | `/knowledge/documents` | — | `{ documents:[{doc_id,filename,file_type,size_bytes,status,created_at}] }` |
| DELETE | `/knowledge/documents/{doc_id}` | — | `{ deleted }` |
| GET | `/wrong/questions` | — | `{ questions:[{stem,options,answer,analysis,knowledge_point,wrong_count,last_wrong_at}], weak_points:[{knowledge_point,questions,wrong_times}], total }` |
| POST | `/wrong/practice` | `{count?, grade?}` | 与 `/quiz/generate` 同结构，`source` 为 `wrongbook` |
| PUT | `/wrong/questions` | `{stem, new_stem?, options?, answer?, analysis?, knowledge_point?, wrong_count?}` | `{ stem }` |
| DELETE | `/wrong/questions/item` | `{stem}` | `{ deleted }` |
| DELETE | `/wrong/questions` | — | `{ cleared: true }` |

**题目对象（questions 数组元素）**：
```js
{ id: 1, type: 'single', stem: '题干', options: ['A','B','C','D'],
  answer: 1, analysis: '解析', knowledge_point: '知识点' }
```
> 注意：`answer` 是正确选项的**下标**（0 起）。这是现有后端设计，前端据此做即时讲解。

**判题明细（details 数组元素）**：
```js
{ id, stem, options, user_answer, correct_answer, is_correct, analysis, knowledge_point }
```

**错误码**（`err.code` 可读取）：`4000` 参数错误 · `4001` 文档解析失败 · `4002` 内容不合规 · `4003` 错题本为空 · `4010` 未登录 · `5000` 服务器错误。
> `4002` 时用户输入了不适合未成年人的主题，此时直接用后端给的 `err.message` 提示即可。

**学段取值**：`primary_low`（小学低年级 1—3 年级，默认 5 题）· `primary_high`（小学高年级 4—6 年级，默认 8 题）· `junior`（初中，默认 10 题）。

**出题来源（source）**：`ai` 表示由大模型生成；`bank` 表示题库降级；`wrongbook` 表示错题重练。
> 界面上要**据实标注**：「由 AI 生成」/「来自题库」/「错题重练」，不要谎称是 AI 生成的。

---

## 六、各页面要求

### 1. `pages/index/index` —— 去闯关（首页）
- 顶部：`<mascot state="idle" size="md">` + 问候语（含当前学段，如「今天想探索什么？你是小学高年级哦」）。
- **学段选择**：三个胶囊按钮（小学低年级 / 小学高年级 / 初中），数据来自 `app.globalData.grades`（拿不到时用三个写死的兜底项，值同上学段取值）。当前项高亮，点击调用 `app.setGrade(value)` 并更新界面。
- **主题输入**：`<input class="input">` 占位提示「比如：太阳系、恐龙、彩虹是怎么来的」，配一个大按钮「开始出题」（`btn btn-primary`，宽度撑满）。输入为空时按钮置灰并提示「先告诉小科你想学什么吧」。
- **主题快捷入口**：天文 / 地理 / 生物 / 物理 / 化学 / 科技 六个胶囊，点击直接填入输入框。
- **来自知识库的出题**：若 `onLoad` 带 `options.doc_id` 和 `options.topic`，则在输入框上方显示一张提示卡「本次将基于《xxx》出题」，并把 doc_id 记下来一起提交。
- **出题中（关键体验，务必实现）**：因为大模型出题可能需要 20—40 秒，必须给过程反馈，禁止只显示一个转圈：
  - `<mascot state="thinking" size="lg">`，台词随阶段变化：0—8 秒「小科正在翻书找答案…」；8—20 秒「正在认真出题，马上就好…」；20 秒以上「快好啦，再等一下下～」
  - 下方轮播**科普小知识**（本地常量数组，至少 6 条，每 4 秒换一条）。用它把等待时间变成学习时间。
  - 提供「取消」入口（用 `wx.showModal` 确认后清除定时器并回到表单态）。
- 成功：把返回数据存到 `app.globalData.lastQuiz`，`wx.navigateTo({url:'/pages/quiz/index'})`。
- 失败：回到表单态，保留用户已输入的主题。

### 2. `pages/quiz/index` —— 答题闯关
- `onLoad`：从 `app.globalData.lastQuiz` 取题目。若为空 → 提示「还没有题目，先去选一个主题吧」并 `wx.navigateBack()`。
- 顶部：进度条（`.progress`，宽度 = 已答题数/总题数）+ 「第 X / N 题」+ 学段胶囊（用 `app.gradeLabel()`）。
- 题干用 `.h2`（≥36rpx），下方是选项列表（用全局 `.option` `.option-key`）。
- **交互**：点击选项即选中（选中态 `.option.selected`）；未点「就选这个」前可以改选。
- 点「就选这个」后**立即本地判分并讲解**（后端题目数据已含 `answer` 与 `analysis`）：
  - 正确 → 该选项加 `.option.correct`，`<mascot state="correct" size="sm">`
  - 错误 → 用户选项加 `.option.wrong`，同时把正确选项标成 `.option.correct`，`<mascot state="wrong" size="sm">`
  - 无论对错都展示解析卡：知识点胶囊 + `analysis` 正文
  - 此后本题选项锁定，按钮变成「下一题」；最后一题变为「看看我的报告」
- **连续答错 2 题**时，mascot 换成 `encourage`，并给一句「要不要先看看解析？」的提示（体现「不逼孩子一直错下去」）。
- 全部答完后：`api.post('/quiz/submit', {quiz_id, answers, duration_ms})`，`answers` 是按题序的选项下标数组（未作答的记 `-1`）。成功后把结果存 `app.globalData.lastResult`，`wx.navigateTo('/pages/report/index')`。
- 提交时要 `wx.showLoading`（文案「小科在算分…」），`finally` 里务必 `api.hideLoading()`。
- 要兼容来自错题本的练习卷（`source === 'wrongbook'`），逻辑完全一致，只是标题显示「错题重练」。

### 3. `pages/report/index` —— 复盘报告
- 两种进入方式：
  1. 答题完进入：读 `app.globalData.lastResult`（含 `accuracy`、`xp_gained`、`wrong_added`、`mastered`、`wrong_total`、`details`、`quiz_id`）。
  2. 从个人中心的历史记录进入：`onLoad` 带 `options.quiz_id`，此时**没有** `details`，只调用 `/report/generate` 展示报告部分，并隐藏「本次答题回顾」。
- 先展示**得分区**：大号正确率数字 + 掌握度进度条 + `<mascot state="win|correct|encourage">`（按正确率 ≥80 / ≥60 / 其余 三档切换）。
- 再请求 `api.post('/report/generate', {quiz_id})` 拿复盘报告（可能较慢，用 mascot `thinking` + 「小科在写复盘报告…」）。
- 报告内容：掌握度评分、`summary`（三句话知识总结）、`suggestion`（下一步建议）、`weak_points` 作为胶囊列表。
- **来源要据实标注**：`report.source === 'ai'` 显示「由 AI 生成」；`source === 'rule'` 显示「本次由学习助手生成」。不要谎称是 AI 生成的。
- 结算区：经验值 `+{{xp_gained}}`、本次新增错题 `wrong_added` 题、已掌握 `mastered` 题、错题本共 `wrong_total` 题。
- 「本次答题回顾」：遍历 `details`，只展示答错的题（题干 + 你的答案 + 正确答案 + 解析），可折叠展开。
- 底部按钮：「再来一局」（`wx.reLaunch('/pages/index/index')`）、「去错题本」（`wx.switchTab('/pages/wrong/index')`）。

### 4. `pages/profile/index` —— 我的
- **未登录**（`app.isLogin()` 为 false）：显示 `<mascot state="encourage" size="lg">` + 「登录后才有经验值和错题本哦，现在也能正常闯关」+ 「登录」按钮（调用 `wx.login` 拿 code → `api.post('/user/login',{code,nickname:'小科学家',grade:app.globalData.grade})` → `api.saveSession` → 刷新页面）。
- **已登录**：昵称、累计经验值（大字）、错题数、当前学段。
- 薄弱知识点排行：`weak_points` 列表，展示知识点 + 错题数 + 错误次数，用 `.pill-orange`。
- 历史闯关：`sessions` 列表（标题 + 学段 + 来源 + 时间），点击 → `wx.navigateTo('/pages/report/index?quiz_id=' + quiz_id)`。
  - 时间字段 `created_at` 形如 `2026-09-15 17:11:51`，直接截取显示即可，不要引第三方日期库。
- 「清空错题本」按钮：`wx.showModal` 二次确认 → `api.del('/wrong/questions')` → 刷新。文案用「确定要清空吗？清空后错题就找不回来了」。
- 下拉刷新（`onPullDownRefresh`）。

### 5. `pages/knowledge/index` —— 知识库
- 顶部说明卡：一句话讲清用途——「把讲义或课外读本传上来，小科就能照着它出题」。
- 上传按钮：「上传资料」→ `wx.chooseMessageFile({count:1, type:'file', extension:['txt','md','markdown','csv','pdf','docx']})` → `api.upload('/knowledge/documents', res.tempFiles[0].path, 'file')`。
  - 上传中 `wx.showLoading('小科正在读这份资料…')`，成功后刷新列表。
  - 上传失败（如 `code === 4001`）时提示：「这份资料小科读不懂，先试试 txt 或 md 文本文件吧」。
- 列表：文件名 + 类型/大小 + 状态胶囊 + 上传时间；每项两个操作：
  - 「用它出题」→ `api.post('/quiz/generate', { topic: 文件名, doc_id, grade: app.globalData.grade })` → 存 `app.globalData.lastQuiz` → 跳答题页
  - 「删除」→ `wx.showModal` 确认 → `api.del('/knowledge/documents/' + doc_id)`
- 空态：`<mascot state="idle" size="sm">` + 「还没有资料，传一份上来试试吧」。
- 底部加一条诚实的说明：「当前直接支持 txt / md 文本；pdf / docx 需要服务端安装 pypdf、docx2txt 依赖」。
- 文件大小展示：把 `size_bytes` 转成 KB / MB 显示。

### 6. `pages/wrong/index` —— 错题本
- 未登录：`<mascot state="encourage" size="lg">` + 「登录后才能把错题存下来哦」+ 登录按钮（同上）。
- 已登录：`api.get('/wrong/questions')`，展示：
  - 顶部统计卡：错题总数 + 「薄弱知识点」胶囊列表
  - 「只练错题」大按钮（`btn btn-primary`，宽度撑满）→ `api.post('/wrong/practice', { count: 8, grade: app.globalData.grade })` → 存 `app.globalData.lastQuiz` → 跳答题页。按钮下方小字提示「不用等 AI 出题，马上就能开始」。错题数为 0 时按钮置灰。
  - 错题列表：题干 + 知识点胶囊 + 「错过 N 次」+ 点击展开（正确答案、你的答案、解析）
  - **每条错题可以改、可以删**（错题本自己也要能维护，不然攒久了就没法用）：
  - 展开讲解后出现两个按钮：「改一改」进入内联编辑（题干 / 知识点 / 解析 + 点选项胶囊设正确答案），
    保存走 `api.put('/wrong/questions', {stem, new_stem?, knowledge_point?, analysis?, answer?})`；
  - 「不用留了」删除单条：二次确认后走 `api.delBody('/wrong/questions/item', {stem})`
    （题干是长中文，走请求体比塞进 URL 稳妥）；
  - 删除后刷新列表。
- 「清空错题本」文字按钮（二次确认）
- 空态：`<mascot state="idle" size="sm">` + 「还没有错题，去闯一关吧！」+ 「去闯关」按钮（`wx.switchTab('/pages/index/index')`）。
- 下拉刷新（`onPullDownRefresh`）。

---

## 七、每个页面交付前必须自检

1. `index.js` 能被 `node --check` 通过（无语法错误）。
2. `index.json` 是合法 JSON（无注释、无尾逗号）。
3. 所有 `api.xxx()` 调用的路径与**第五节表格完全一致**。
4. WXML 里用到的变量都在 `data` 里初始化过（避免 undefined 渲染空白）。
5. `wx.showLoading` 与 `wx.hideLoading`（或 `api.hideLoading()`）必须成对，且失败分支也要关闭。
6. 颜色只来自 CSS 变量；答错一律用暖橙。
7. 文案遵守第三节的语气规则，不出现「错误」「失败」「暂无数据」。
