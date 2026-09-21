# 接口冒烟测试报告

| 项目 | 内容 |
| --- | --- |
| 被测服务 | http://127.0.0.1:8000 |
| 测试时间 | 2026-09-21 12:40:24 |
| 测试耗时 | 2.6 秒 |
| 测试脚本 | `backend/tests/smoke_test.py`（仅标准库，可重复运行） |
| 用例构成 | 40 条功能用例 + 7 条性能用例 + 9 条降级用例 |
| 通过情况 | 49 / 49（通过率 100.0%） |

> 本报告由脚本自动生成，表中数据均为本机实测值，可直接用于论文第 6 章。

## 表 6-1 接口功能测试用例及结果

| 编号 | 测试用例 | 请求 | 预期结果 | 实际结果 | 结论 |
| --- | --- | --- | --- | --- | --- |
| TC-01 | 服务健康检查 | GET /api/v1/health | code=0 且 status=up | code=0 status=up | 通过 |
| TC-02 | 学段选项拉取 | GET /api/v1/grades | code=0 且返回 3 个学段 | code=0 学段数=3 | 通过 |
| TC-03 | 游客模式出题（未登录） | POST /api/v1/quiz/generate topic=恐龙 | code=0 且题量≥3 | code=0 题量=5 来源=bank | 通过 |
| TC-04 | 空主题入参校验 | POST /api/v1/quiz/generate topic=空格 | code=4000 | code=4000 message=请输入想学习的主题 | 通过 |
| TC-05 | 超长主题入参校验 | POST /api/v1/quiz/generate topic=80字 | code=4000 | code=4000 | 通过 |
| TC-06 | 内容安全前置校验 | POST /api/v1/quiz/generate topic=制造炸弹 | code=4002 | code=4002 message=这个主题不太适合小朋友哦，换一个科学小知识试试看吧 | 通过 |
| TC-07 | 学段题量收敛 | 小学低年级请求 99 题 | 题量收敛到 8 题 | 题量=8 | 通过 |
| TC-08 | 题目字段完整性 | 检查首题字段 | 含题干/选项/答案下标/解析/知识点 | 字段=9 选项数=4 answer=1 | 通过 |
| TC-09 | 答题提交与判题 | POST /api/v1/quiz/submit | code=0 且题数一致 | 题数=8 答对=4 正确率=50.0 | 通过 |
| TC-10 | 经验值结算规则 | 完成闯关+10、答对每题+2 | xp=18 | xp=18 | 通过 |
| TC-11 | 错题自动入库 | 答错题写入错题本 | 新增错题=4 | 新增错题=4 | 通过 |
| TC-12 | 无效 quiz_id 容错 | POST /api/v1/quiz/submit 不存在的ID | code=4000 | code=4000 | 通过 |
| TC-13 | 复盘报告生成 | POST /api/v1/report/generate | code=0 且含掌握度/总结/建议 | 来源=rule 掌握度=50 档位=及格 | 通过 |
| TC-14 | 未提交先取报告容错 | POST /api/v1/report/generate 不存在的ID | code=4000 | code=4000 | 通过 |
| TC-15 | 错题本总览 | GET /api/v1/wrong/questions | code=0 且错题数与提交一致 | 错题数=4 薄弱知识点=4 | 通过 |
| TC-16 | 只练错题（不调用大模型） | POST /api/v1/wrong/practice count=5 | code=0 且来源=wrongbook | 来源=wrongbook 题量=4 | 通过 |
| TC-17 | 个人中心数据 | GET /api/v1/user/profile | code=0 且含经验值与历史 | 经验值=18 历史闯关=2 | 通过 |
| TC-18 | 未登录访问个人中心 | GET /api/v1/user/profile 无 Token | code=4010 | code=4010 | 通过 |
| TC-19 | 未登录访问错题本 | GET /api/v1/wrong/questions 无 Token | code=4010 | code=4010 | 通过 |
| TC-20 | 空错题本练习容错 | POST /api/v1/wrong/practice 错题本为空 | code=4003 | code=4003 | 通过 |
| TC-21 | 知识库文档上传 | POST /api/v1/knowledge/documents (txt) | code=0 且返回分块数 | 文档ID=33ec3515b868 分块=1 | 通过 |
| TC-22 | 知识库列表 | GET /api/v1/knowledge/documents | code=0 且包含刚上传文档 | 文档数=1 | 通过 |
| TC-23 | 检索增强（RAG）出题 | POST /api/v1/quiz/generate 带 doc_id | code=0 且返回命中片段数 | 命中片段=1 来源=bank | 通过 |
| TC-24 | 不支持的文件格式 | 上传 .exe 文件 | code=4001 | code=4001 | 通过 |
| TC-25 | 空文档容错 | 上传只含空白的 txt | code=4001 | code=4001 | 通过 |
| TC-26 | 知识库文档删除 | DELETE /api/v1/knowledge/documents/{doc_id} | code=0 | code=0 | 通过 |
| TC-27 | 清空错题本 | DELETE /api/v1/wrong/questions | code=0 且错题数归零 | 残留错题=0 | 通过 |
| TC-28 | 管理端登录 | POST /api/v1/admin/login | code=0 且返回 Token | code=0 | 通过 |
| TC-29 | 管理端口令错误 | POST /api/v1/admin/login 错误口令 | code=4011 | code=4011 message=账号或口令不正确 | 通过 |
| TC-30 | 管理端未授权访问 | GET /api/v1/admin/dashboard 无 Token | code=4011 | code=4011 | 通过 |
| TC-31 | 管理端运行看板 | GET /api/v1/admin/dashboard | code=0 且含用户/闯关/错题统计 | 用户数=223 闯关数=593 平均正确率=54.6 | 通过 |
| TC-32 | 管理端新增题目 | POST /api/v1/admin/questions | code=0 且返回新题 ID | 新题ID=21 | 通过 |
| TC-33 | 管理端题库查询 | GET /api/v1/admin/questions?keyword=月球绕地球一周 | code=0 且能搜到刚新增的题 | 命中=1 条，包含新题=True | 通过 |
| TC-34 | 管理端题目参数校验 | answer 下标越界 | code=4000 | code=4000 message=正确答案下标超出选项范围 | 通过 |
| TC-35 | 管理端修改题目 | PUT /api/v1/admin/questions/{id} | code=0 | code=0 | 通过 |
| TC-36 | 资源池题目参与出题 | 连续出题 6 轮，看是否命中管理端资源池的题 | 至少命中一次 | 命中=True | 通过 |
| TC-37 | 管理端删除题目 | DELETE /api/v1/admin/questions/{id} | code=0 | code=0 | 通过 |
| TC-38 | 管理端用户列表 | GET /api/v1/admin/users | code=0 且含闯关数统计 | 用户数=223 | 通过 |
| TC-39 | 管理端闯关记录 | GET /api/v1/admin/sessions | code=0 | 记录数=5 总数=594 | 通过 |
| TC-40 | 管理端操作日志留痕 | GET /api/v1/admin/logs | code=0 且包含题库操作记录 | 日志条数=20 | 通过 |

## 表 6-2 接口响应时间测试结果

| 接口 | 功能 | 重复次数 | 平均响应时间(ms) | 最小(ms) | 最大(ms) |
| --- | --- | --- | --- | --- | --- |
| GET /api/v1/grades | 学段选项查询 | 3 | 17 | 16 | 19 |
| POST /api/v1/user/login | 用户登录 | 3 | 25 | 14 | 35 |
| POST /api/v1/quiz/generate | 出题（题库降级路径） | 3 | 24 | 16 | 33 |
| POST /api/v1/quiz/submit | 判题与结算 | 3 | 29 | 20 | 37 |
| POST /api/v1/report/generate | 复盘报告（规则降级路径） | 3 | 36 | 35 | 37 |
| GET /api/v1/wrong/questions | 错题本查询 | 3 | 17 | 15 | 22 |
| POST /api/v1/wrong/practice | 只练错题组卷 | 3 | 18 | 11 | 28 |

> 说明：以上为题库降级路径（未配置大模型 Key）的实测值，不含大模型网络往返时间。配置 DeepSeek Key 后，出题接口耗时主要由模型推理决定，通常在 10～40 秒；因此小程序端设计了分档等待台词与科普轮播，把等待时间转化为学习时间（见 4.9、5.8 节）。

## 表 6-3 降级与异常测试结果

| 测试场景 | 做法 | 预期结果 | 实际结果 | 结论 |
| --- | --- | --- | --- | --- |
| 无大模型 Key 时出题降级 | 不配置 DEEPSEEK_API_KEY 直接出题 | source=bank 且题量满足学段要求 | source=bank 题量=8 | 通过 |
| 无大模型 Key 时报告降级 | 提交后生成复盘报告 | source=rule 且给出分档结论 | source=rule level=待加强 | 通过 |
| 降级题目可正常判题 | 对题库降级生成的题全部选正确答案 | code=0 且正确率 100% | 正确率=100.0 | 通过 |
| 检索无命中时的容错 | 上传无关资料后基于它出题 | code=0 且正常返回题目 | code=0 命中片段=0 题量=8 | 通过 |
| 非法 JSON 请求体 | POST 非法 JSON 字符串 | code=4000，不暴露堆栈 | code=4000 | 通过 |
| 不存在的文档 ID | doc_id 指向不存在的文档 | code=0 且退化为普通出题 | code=0 命中片段=0 | 通过 |
| 伪造管理端 Token | 使用伪造 X-Admin-Token 访问看板 | code=4011 | code=4011 | 通过 |
| 同一会话重复提交 | 连续提交两次相同答案 | 两次均 code=0 且结果一致 | 两次正确率=100.0 / 100.0 | 通过 |
| 答案数组长度不足 | 只提交 1 个答案 | code=0，未作答按未答处理 | code=0 答对=1/8 | 通过 |

## 结论

全部用例通过。系统在正常路径、异常路径与降级路径下均给出符合预期的响应；大模型不可用时，出题、判题、复盘报告、只练错题四条链路仍保持可用，说明三层降级机制达到了设计目标。
