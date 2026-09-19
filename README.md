# 科普闯关系统（中小学生）

> 本科毕业设计成品：《中小学生科普知识闯关系统的设计与实现》
> **一套开箱可用的完整系统**：网页版学生端 ＋ Web 管理端 ＋ FastAPI 服务端 ＋ 论文与插图，
> 另附一套同功能的微信小程序端（`frontend/`）。

---

## 〇、最快看到成品

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后打开浏览器：

| 地址 | 是什么 |
| --- | --- |
| http://127.0.0.1:8000/ | **学生端（网页版）** —— 自动跳到 `/app/`，开箱可点 |
| http://127.0.0.1:8000/admin/ | 管理端（账号 `admin` / 口令 `kepu@2026`，**对外开之前必须先换掉，见下**） |
| http://127.0.0.1:8000/docs | 接口文档（Swagger，可现场试调） |

> 也可以直接双击 `scripts\run_server.cmd`（Windows 一键启动）。
> 网页版**不需要任何构建步骤**，也**不需要微信开发者工具**，打开就能用。
>
> `/app/` 未登录时是入口页，三个页签分别是「学生登录」「学生注册」「管理员」：
> 学生用登录名（3~20 位字母、数字或下划线）与口令（6~32 位）注册登录，
> 也可以点「先逛逛」以游客身份直接体验，注册后游客期间的闯关记录、错题与经验值会并到正式账号；
> 「管理员」页签直接调用管理端登录接口，成功后跳 `/admin/`，不用手敲地址。

### ⚠️ 只在本机跑的话，不需要做任何额外配置

服务默认监听 `127.0.0.1`（回环地址），**除本机之外的设备都连不上** ——
同一 WiFi 下的手机、同学的电脑都访问不到，这是内核层面没对外监听，不是防火墙问题。

**一旦要让别人访问（局域网、公网隧道、正式部署），先做这一步：**

```bash
python tools/gen_secrets.py     # 生成 backend/.env，把管理员口令、JWT 密钥、管理端令牌换成随机值
```

原因：仓库是公开的，`config.py` 里的默认口令 `kepu@2026`、开发用 JWT 密钥与管理端令牌
任何人都看得到，而管理端能看全部学生的答题记录、也能改题库。
生成后口令会打印到终端，**重启服务生效**；`backend/.env` 已 gitignore，不会被提交。
（`python tools/gen_secrets.py --show` 可以随时查看当前生效的值。）

要让老师远程点开看，用免费临时隧道最省事，不需要账号：

```bash
cloudflared tunnel --url http://127.0.0.1:8000    # 另一个窗口，保持开着
python tools/verify_tunnel.py https://拿到的地址    # 验证外网真的能用
```

完整步骤、注意事项与"这个地址是临时的"的如实说明见
[`docs/repo/部署与答辩说明.md`](docs/repo/部署与答辩说明.md) 第四节。

---

## 一、这个仓库是什么

一个面向中小学生的科普学习系统。孩子输入想学的主题（例如「太阳系」「彩虹是怎么来的」），
系统现场出题、逐题讲解、给出复盘报告，并把答错的题沉淀成错题本；
教师或家长可以把讲义贴进知识库，让出题**只依据这份资料**；
管理员可以在 Web 后台维护题库资源池、查看用户与闯关数据。

功能上做成完整的**增删改查**，不是只能看的演示壳：

| 对象 | 增 | 删 | 改 | 查 |
| --- | --- | --- | --- | --- |
| 错题（学生端） | 答错自动入库 | 删单条 / 清空 | 改题干、选项、正确答案、解析、知识点 | 错题本列表 + 薄弱知识点排行 |
| 知识库资料（学生端） | 贴文本或选本地文件 | 删单条 | — | 文档列表 + 用它出题 |
| 题库资源池（管理端） | 新增题目 | 删单条 | 改题干、选项、答案、难度、启用状态 | 分页 + 关键词搜索 |
| 用户（管理端） | — | — | 启用 / 停用 | 分页 + 关键词搜索 |
| 运行数据（管理端） | — | — | — | 看板、趋势、闯关记录、操作日志 |

**趣味化设计**（面向小朋友，而不是给成人看的表单）：

- 每题**倒计时**给节奏感，但到点**不判负、不扣分**，只把小科换成鼓励态
- **连对**会累计并喝彩（「三连对，稳住！」），答对的音高随连对次数升高
- **等级 + 进度条**：每 50 点经验升一级，称号从「科学小新芽」到「科学小博士」
- **音效与震动**：答对、连对、通关各有提示音，可一键关闭（安静场合不打扰别人）
- **吉祥物「小科」**纯 CSS 绘制，六种状态（待机 / 思考 / 答对 / 差点 / 鼓励 / 通关）
- 全篇文案不出现「错误 / 失败 / 排名」；答错用暖橙而不是纯红

系统的核心设计取向是**「大模型不可用时也必须能用」**，因此实现了三层降级：

| 链路 | 首选方案 | 降级方案 |
| --- | --- | --- |
| 出题 | 调用 DeepSeek 生成题目 | 内置 150 题科普题库 / 管理端题库资源池（按主题匹配 + 随机抽样） |
| 复盘报告 | 大模型生成掌握度与建议 | 按正确率分档的规则模板 |
| 复习 | —— | 「只练错题」直接用错题重组练习卷，不调用大模型，毫秒级返回 |

答辩演示时即使没有网络、没有付费额度，全部功能依然可以完整走通。

---

## 二、目录结构

```
kepu-quiz/
├── backend/                服务端（Python + FastAPI + SQLite）
│   ├── app/                应用代码
│   │   ├── main.py             应用入口：路由装配、统一异常处理、CORS、静态托管
│   │   ├── routers.py          学生端 19 个接口
│   │   ├── admin.py            管理端 14 个接口
│   │   ├── services.py         业务服务层（注册登录 / 出题 / 判题 / 报告 / 检索 / 错题本）
│   │   ├── admin_db.py         管理端数据访问（账号、题库资源池、统计、日志、单学生答题详情）
│   │   ├── database.py         SQLite 数据访问层（10 张表、自动建表与迁移）
│   │   ├── llm.py              大模型调用与降级
│   │   ├── question_bank.py    内置科普题库载入（150 题 / 6 大主题，每主题 25 题）
│   │   ├── bank_part_a.json    题库数据：天文 / 地理 / 生物（75 题）
│   │   ├── bank_part_b.json    题库数据：物理 / 化学 / 科技（75 题）
│   │   ├── grades.py           学段适配参数
│   │   ├── safety.py           内容安全过滤
│   │   ├── wrongbook.py        错题本
│   │   ├── schemas.py          Pydantic 请求 / 响应模型
│   │   └── config.py           配置（全部可用环境变量覆盖）
│   ├── tests/              接口冒烟测试（仅标准库，可重复运行）
│   └── requirements.txt    运行依赖（不含数据库，SQLite 用标准库）
├── web/                    ★ 学生端网页版（原生 HTML/CSS/JS，零构建，主力交付）
│   ├── index.html              单页入口（六个页面由 hash 路由切换）
│   ├── assets/app.css          视觉规范（与小程序端同一套设计令牌）
│   ├── assets/app.js           请求封装、音效合成、等级换算、吉祥物渲染
│   ├── assets/main.js          六个页面与全部增删改查交互
│   └── shots/                  端到端验收自动产生的界面截图
├── frontend/               微信小程序版（附加交付，功能同网页版）
│   ├── app.js / app.json / app.wxss / config.js
│   ├── pages/              index 首页 · quiz 答题 · report 复盘 · wrong 错题本 ·
│   │                       knowledge 知识库 · profile 我的
│   ├── components/mascot/  吉祥物「小科」（纯 CSS 绘制，六种状态）
│   ├── utils/sound.js      音效（WebAudio 合成，不引入音频文件）
│   └── FRONTEND_SPEC.md    前端开发规范（也是论文 4.9 / 5.8 节的依据）
├── admin/                  Web 管理端（原生 HTML/CSS/JS，零构建）
├── demo/                   小程序版的浏览器预览（由 tools/make_demo.js 生成）
├── docs/
│   ├── thesis/             论文写作素材、分章 Markdown、合并稿与 .docx
│   ├── figures/            论文插图（由脚本生成，可一键重画）
│   └── repo/               接口清单、数据库字典、部署与答辩说明
├── scripts/                Windows 一键脚本（启动、测试、打包）
└── tools/                  辅助脚本（插图生成、论文转 Word、数据库重置、各项验收）
```

---

## 三、五分钟跑起来

### 1. 启动服务端

先安装依赖（见第四节），然后双击 `scripts\run_server.cmd`
（或在该目录执行 `.\scripts\run_server.cmd`）。启动后：

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:8000/ | **学生端网页版**（自动跳到 `/app/`，开箱可点） |
| http://127.0.0.1:8000/admin/ | **管理端**（默认账号 `admin`，口令 `kepu@2026`；对外开之前请先跑 `tools/gen_secrets.py`） |
| http://127.0.0.1:8000/docs | 接口文档（Swagger UI，答辩演示很好用） |

首次启动会自动建库、建表、创建默认管理员，并打印数据库路径与大模型状态。

### 2. 跑验收（可选，但强烈建议）

一键跑完全部验收项（10 组）：

```bash
python tools/acceptance.py
```

覆盖：后端冒烟、管理端接口联通性、前端静态检查、错题本增删改查、题库完整性与学段分离、
学段分级出题、论文成稿检查、网页版端到端（真实 Chrome + 截图）、学生注册登录与错题收录、
管理端答题详情分类面板。

它同时会产出论文第 6 章要用的实测数据：`backend/tests/smoke_report.md`
（40 条功能用例 + 7 条性能用例 + 9 条降级用例）。

要验证**公网地址**（隧道或已部署域名）能不能真的用起来：

```bash
python tools/verify_tunnel.py https://你的地址
```

### 3. 微信小程序端（附加交付，可选）

小程序端与网页版功能一致，代码在 `frontend/`，**但必须用微信开发者工具运行**：

1. 用**微信开发者工具**导入 `frontend` 目录（AppID 选「测试号」即可）。
2. 在「详情 → 本地设置」中勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书**。
3. 编译运行。首页即可选学段、输主题、开始闯关。

> 真机预览时请把 `frontend/config.js` 里的 `BASE_URL` 改成电脑的局域网 IP（例如
> `http://192.168.1.10:8000/api/v1`），并保证手机与电脑在同一网络。
>
> 如果手边没有微信开发者工具，可以先跑 `scripts\make_demo.cmd`：
> 它把小程序端真实的 WXML / WXSS / 页面 JS 转成 `demo/index.html`，
> 在浏览器里带手机外框预览（**这只是小程序的预览，不是主力交付**，
> 主力交付是上面的网页版 `/app/`）。

---

## 四、安装依赖

```bash
cd backend
pip install -r requirements.txt
```

依赖只有 FastAPI、Uvicorn、Pydantic、httpx、PyJWT，加上知识库解析用的 pypdf、docx2txt，
全部是纯 Python 包，不需要编译环境；SQLite 用的是标准库，无需安装数据库。

> 如果目标是「换一台没联网的机器也要能演示」，可以在装好依赖后把 `site-packages`
> 复制到 `backend/deps/`，启动脚本会自动把它加入模块搜索路径（脚本里已留好这一行）。
> 平时不必这么做，仓库不提交依赖副本，保持体积干净。

---

## 五、配置大模型（可选）

不配置也能完整体验（自动走题库降级）。要接入真实 AI 出题：

```bash
cd backend
copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

关键配置项（放在 `backend/.env` 里最方便，服务启动时会自动读取；文件不存在则用默认值）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | 留空即启用题库降级 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DB_PATH` | `data/kepu.db` | SQLite 文件路径（相对 backend/） |
| `JWT_SECRET` | 开发用默认值 | **上线/对外必须改** |
| `ADMIN_PASSWORD` | `kepu@2026` | **上线/对外必须改**（改完重启即生效） |
| `ADMIN_TOKEN` | `kepu-admin-token-dev` | 脚本直连用的固定令牌，**对外必须改** |
| `APP_HOST` | `127.0.0.1` | 改成 `0.0.0.0` 才能被同网段的其他设备访问 |
| `MAX_UPLOAD_BYTES` | 2097152 | 知识库单文件上限（2 MB） |

`python tools/gen_secrets.py` 会把上面三个"必须改"的项一次性换成随机值并写进 `backend/.env`。

> 注意一个原先的坑：早期版本改了 `ADMIN_PASSWORD` 重启**并不生效**，因为
> `ensure_default_admin()` 只判"管理员账号是否已存在"，存在就直接返回，库里还是老口令的哈希。
> 现在配置里的口令是权威来源，和库里的哈希对不上就重算写回，"改配置 → 重启 → 生效"才成立。

---

## 六、接口一览

统一前缀 `/api/v1`，统一响应 `{code, message, data}`（`code = 0` 为成功）。

**学生端（19 个）**：`GET /health`、`GET /grades`、
`POST /quiz/generate`、`POST /quiz/submit`、`POST /report/generate`、
`POST /user/register`、`POST /user/login`、`POST /user/guest`、`POST /user/merge-guest`、`GET /user/profile`、
`POST /knowledge/documents`、`GET /knowledge/documents`、`DELETE /knowledge/documents/{doc_id}`、
`GET /wrong/questions`、`POST /wrong/practice`、`DELETE /wrong/questions`、
`PUT /wrong/questions`、`DELETE /wrong/questions/item`、`DELETE /wrong/questions/{stem}`。

**管理端（14 个，请求头 `X-Admin-Token`）**：`POST /admin/login`、`GET /admin/me`、
`GET /admin/dashboard`、`GET /admin/trend`、`GET /admin/users`、`GET /admin/users/{user_id}`、
`POST /admin/users/{user_id}/status`、
`GET /admin/questions`、`GET /admin/questions/themes`、`POST /admin/questions`、
`PUT /admin/questions/{qid}`、`DELETE /admin/questions/{qid}`、
`GET /admin/sessions`、`GET /admin/logs`。

**错误码**：`4000` 参数错误 · `4001` 文档解析失败 · `4002` 内容不合规 · `4003` 错题本为空 ·
`4010` 学生端未登录 · `4011` 管理端未认证 · `5000` 服务器内部错误。

完整的字段级说明见 `docs/repo/接口清单.md` 与 `/docs` 在线文档。

---

## 七、数据库（10 张表）

`users` 用户 · `quiz_sessions` 闯关会话 · `answer_records` 答题记录 · `reports` 复盘报告 ·
`knowledge_docs` 知识库文档 · `knowledge_chunks` 知识库分块 · `wrong_questions` 错题本 ·
`admins` 管理端账号 · `question_pool` 题目资源池 · `admin_logs` 操作日志。

`users` 表含 `username`、`password_hash`、`salt` 三个学生账号字段，并为 `username` 建唯一索引；
旧库由 `_MIGRATIONS` 自动补列。

表结构字典见 `docs/repo/数据库字典.md`。系统启动时自动建表，并对旧版本数据库做补列迁移
（`CREATE TABLE IF NOT EXISTS` 不会补列，因此额外实现了 `_migrate`）。
重置数据库：`python tools/reset_db.py`。

---

## 八、论文相关

| 文件 | 说明 |
| --- | --- |
| `docs/thesis/01_论文大纲_修订版.md` | 论文大纲（章节、字数、图表清单、规范核对） |
| `docs/thesis/00_事实清单.md` | 写作口径：技术栈、表、接口、图表编号、可引用的实测数据 |
| `docs/thesis/05_论文全文.md` | 合并后的论文全文（Markdown） |
| `docs/thesis/论文正文.docx` | 按学校规范排版导出的 Word 稿 |
| `docs/figures/*.png` | 图 3-1、图 4-1～4-4、图 5-1，全部由脚本生成 |
| `backend/tests/smoke_report.md` | 第 6 章测试数据（实测，非编造） |

重新生成插图与 Word：

```bash
python tools/make_figures.py     # 重画全部插图
python tools/md2docx.py          # 合并分章 Markdown 并导出 Word
```

---

## 九、常见问题

**Q：启动时报 `ModuleNotFoundError: No module named 'fastapi'`。**
说明依赖没装。请在 `backend` 目录下执行 `pip install -r requirements.txt` 后重试。

**Q：小程序里点「开始出题」一直转圈。**
多半是后端没启动或域名未放行。检查 http://127.0.0.1:8000/api/v1/health 是否可访问，
并确认开发者工具里已勾选「不校验合法域名」。

**Q：上传 pdf / docx 提示读不懂。**
`pypdf`、`docx2txt` 是可选依赖，缺失时只有 txt / md / csv 可用。安装后重启即可：
`pip install pypdf docx2txt`。

**Q：管理端登录一直提示口令不正确。**
连续 5 次失败会锁定 60 秒，属于设计要求（防口令爆破）。等待后重试，或通过环境变量
`ADMIN_PASSWORD` 重新指定口令后重建数据库。

**Q：为什么题目只有单选题？**
这是本项目的实际情况，论文第 7 章「研究存在的不足」中已据实说明；
多题型属于后续工作。

---

## 十、安全说明（上线前必读）

1. 源码中不含任何真实密钥；`JWT_SECRET`、`ADMIN_PASSWORD`、`DEEPSEEK_API_KEY`
   都通过环境变量注入，仓库只提交 `.env.example`。
2. 管理端口令使用 PBKDF2-HMAC-SHA256（12 万次迭代 + 每账号随机盐）存储，不存明文。
3. 内容安全目前是**最小可用实现**（敏感词表 + 长度校验），生产环境应替换为
   微信内容安全接口或更完整的词库；接口设计已预留，替换时无需改动调用方。
4. 微信登录为**预留接入点**：`POST /api/v1/user/login` 收到小程序 `code` 时以本地账号实现，
   接入微信服务端校验（换取 openid）时只需替换 `services.login()` 内部实现。
   学生账号本身已可用——`POST /api/v1/user/register` 用「登录名 + 口令」注册，
   口令以 PBKDF2-HMAC-SHA256（12 万次迭代 + 每账号随机盐）存储，不存明文；
   游客账号由 `POST /api/v1/user/guest` 建立，其数据可经 `POST /api/v1/user/merge-guest` 并入正式账号。

---

## 十一、许可

MIT License，见 `LICENSE`。
