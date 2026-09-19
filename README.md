# 中小学生科普知识闯关小程序

> 本科毕业设计成品：《中小学生科普知识闯关小程序的设计与实现》
> 一套**可直接运行**的完整系统：微信小程序（学生端）＋ Web 管理端 ＋ FastAPI 服务端 ＋ 论文与插图。

---

## 一、这个仓库是什么

一个面向中小学生的科普学习小程序。孩子说一句想学的主题（例如「太阳系」「彩虹是怎么来的」），
系统现场出题、逐题讲解、给出复盘报告，并把答错的题沉淀成错题本；
教师或家长可以把讲义上传到知识库，让出题**只依据这份资料**；
管理员可以在 Web 后台维护题库资源池、查看用户与闯关数据。

系统的核心设计取向是**「大模型不可用时也必须能用」**，因此实现了三层降级：

| 链路 | 首选方案 | 降级方案 |
| --- | --- | --- |
| 出题 | 调用 DeepSeek 生成题目 | 内置 60 题科普题库 / 管理端题库资源池（按主题匹配 + 随机抽样） |
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
│   │   ├── routers.py          学生端 13 个接口
│   │   ├── admin.py            管理端 13 个接口
│   │   ├── services.py         业务服务层（出题 / 判题 / 报告 / 检索 / 错题本）
│   │   ├── admin_db.py         管理端数据访问（账号、题库资源池、统计、日志）
│   │   ├── database.py         SQLite 数据访问层（10 张表、自动建表与迁移）
│   │   ├── llm.py              大模型调用与降级
│   │   ├── question_bank.py    内置科普题库 60 题 / 6 大主题
│   │   ├── grades.py           学段适配参数
│   │   ├── safety.py           内容安全过滤
│   │   ├── wrongbook.py        错题本
│   │   ├── schemas.py          Pydantic 请求 / 响应模型
│   │   └── config.py           配置（全部可用环境变量覆盖）
│   ├── tests/              接口冒烟测试（仅标准库，可重复运行）
│   └── requirements.txt    运行依赖（不含数据库，SQLite 用标准库）
├── frontend/               微信小程序（学生端，原生框架）
│   ├── app.js / app.json / app.wxss / config.js
│   ├── pages/              index 首页 · quiz 答题 · report 复盘 · wrong 错题本 ·
│   │                       knowledge 知识库 · profile 我的
│   ├── components/mascot/  吉祥物「小科」（纯 CSS 绘制，六种状态）
│   └── FRONTEND_SPEC.md    前端开发规范（也是论文 4.9 / 5.8 节的依据）
├── admin/                  Web 管理端（原生 HTML/CSS/JS，零构建）
├── demo/                   浏览器演示页（由 tools/make_demo.js 生成）+ 界面截图
├── docs/
│   ├── thesis/             论文写作素材、分章 Markdown、合并稿与 .docx
│   ├── figures/            论文插图（由脚本生成，可一键重画）
│   └── repo/               接口清单、数据库字典、部署与答辩说明
├── scripts/                Windows 一键脚本（启动、测试、打包）
└── tools/                  辅助脚本（插图生成、论文转 Word、数据库重置）
```

---

## 三、五分钟跑起来

### 1. 启动服务端

先安装依赖（见第四节），然后双击 `scripts\run_server.cmd`
（或在该目录执行 `.\scripts\run_server.cmd`）。启动后：

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:8000/ | 服务索引 |
| http://127.0.0.1:8000/docs | 接口文档（Swagger UI，答辩演示很好用） |
| http://127.0.0.1:8000/admin/ | **管理端**（默认账号 `admin`，口令 `kepu@2026`） |

首次启动会自动建库、建表、创建默认管理员，并打印数据库路径与大模型状态。

### 2. 跑接口测试（可选，但强烈建议）

另开一个窗口执行 `scripts\run_smoke_test.cmd`。脚本会自动跑完 40 条功能用例、
7 条性能用例、9 条降级用例，并生成 `backend/tests/smoke_report.md`
—— 这份报告就是论文第 6 章表 6-1～表 6-3 的实测数据来源。

### 3. 打开小程序（两种方式）

**方式 A：浏览器里先看（不用装任何工具，推荐先走这条）**

双击 `scripts\make_demo.cmd`，它会生成并打开 `demo/index.html`。
这是一个带手机外框的可交互页面：**加载的是 `frontend/` 里真实的 WXML / WXSS / 页面 JS**，
数据打真实后端接口，六个页面都能点。同时会把九张界面截图输出到 `demo/shots/`，
可以直接用作答辩材料里的界面图。

> 说明：这个演示页只是「没有微信开发者工具时的替代观察方式」，
> 最终交付物仍然是标准微信小程序工程，验收与上线都以 `frontend/` 目录为准。

**方式 B：标准流程（交付与答辩用这个）**

1. 用**微信开发者工具**导入 `frontend` 目录（AppID 选「测试号」即可）。
2. 在「详情 → 本地设置」中勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书**。
3. 编译运行。首页即可选学段、输主题、开始闯关。

> 真机预览时请把 `frontend/config.js` 里的 `BASE_URL` 改成电脑的局域网 IP（例如
> `http://192.168.1.10:8000/api/v1`），并保证手机与电脑在同一网络。

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

关键配置项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | 留空即启用题库降级 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DB_PATH` | `data/kepu.db` | SQLite 文件路径（相对 backend/） |
| `JWT_SECRET` | 开发用默认值 | **上线必须改** |
| `ADMIN_PASSWORD` | `kepu@2026` | **上线必须改** |
| `MAX_UPLOAD_BYTES` | 2097152 | 知识库单文件上限（2 MB） |

---

## 六、接口一览

统一前缀 `/api/v1`，统一响应 `{code, message, data}`（`code = 0` 为成功）。

**学生端（13 个）**：`GET /health`、`GET /grades`、
`POST /quiz/generate`、`POST /quiz/submit`、`POST /report/generate`、
`POST /user/login`、`GET /user/profile`、
`POST /knowledge/documents`、`GET /knowledge/documents`、`DELETE /knowledge/documents/{doc_id}`、
`GET /wrong/questions`、`POST /wrong/practice`、`DELETE /wrong/questions`。

**管理端（13 个，请求头 `X-Admin-Token`）**：`POST /admin/login`、`GET /admin/me`、
`GET /admin/dashboard`、`GET /admin/trend`、`GET /admin/users`、`POST /admin/users/{id}/status`、
`GET /admin/questions`、`GET /admin/questions/themes`、`POST /admin/questions`、
`PUT /admin/questions/{id}`、`DELETE /admin/questions/{id}`、
`GET /admin/sessions`、`GET /admin/logs`。

**错误码**：`4000` 参数错误 · `4001` 文档解析失败 · `4002` 内容不合规 · `4003` 错题本为空 ·
`4010` 学生端未登录 · `4011` 管理端未认证 · `5000` 服务器内部错误。

完整的字段级说明见 `docs/repo/接口清单.md` 与 `/docs` 在线文档。

---

## 七、数据库（10 张表）

`users` 用户 · `quiz_sessions` 闯关会话 · `answer_records` 答题记录 · `reports` 复盘报告 ·
`knowledge_docs` 知识库文档 · `knowledge_chunks` 知识库分块 · `wrong_questions` 错题本 ·
`admins` 管理端账号 · `question_pool` 题目资源池 · `admin_logs` 操作日志。

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
4. 微信登录为**预留接入点**：当前 `POST /api/v1/user/login` 以本地账号实现，
   接入 `jscode2session` 时只需替换 `services.login()` 内部实现。

---

## 十一、许可

MIT License，见 `LICENSE`。
