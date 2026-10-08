# 架构说明

## 1. 组件

```
浏览器
  │  http://localhost:8080
  ▼
frontend (nginx:1.27-alpine, 端口 80)
  │  /            → React 构建产物（SPA）
  │  /api/*       → 反向代理到 backend:8000
  ▼
backend (FastAPI + Uvicorn, 端口 8000)
  ├─ SQLAlchemy ──► db (postgres:16-alpine, 命名卷 pgdata)
  └─ openai SDK ──► DeepSeek（OpenAI 兼容，密钥来自环境变量）
```

三个服务都在 `docker-compose.yml` 中声明；只有 `frontend` 对外暴露端口，数据库只在内部网络可达。

## 2. 主要请求流

1. `POST /api/auth/login` 校验账号口令，下发 `HttpOnly` JWT Cookie。
2. `POST /api/resumes` 保存**原稿**（`resumes.original_text`，此后只读）并创建同内容的工作稿（`resume_drafts`）。
3. `POST /api/analyses` 用**当前工作稿 + 岗位**建立分析任务快照，状态 `pending`。
4. `POST /api/analyses/{id}/run` 触发后台任务：
   - 状态置为 `running`；
   - 调用模型（DeepSeek，JSON 输出）；
   - 通过 `grounding.normalize_items()` 逐条校验引文；
   - 写入 `analysis_items` + `suggestions`，状态置为 `succeeded`；异常则置 `failed` 并记录可读错误。
5. 前端轮询 `GET /api/analyses/{id}` 直到终态。
6. `POST /api/suggestions/{id}/decision` 采纳/忽略；采纳时对**工作稿**做一次精确替换（幂等）。
7. `POST /api/supplement` 为「未体现 / 需要补充确认」的条目补写真实经历：模型只做措辞润色，
   `grounding.supplement_violations()` 以**用户本次输入**为唯一事实基准校验，越界重试一次后仍越界即拒绝（422）；
   采纳后把润色稿插入**工作稿**并记下“实际插入的那一段”（`item_supplements`），重复采纳不重复插入，撤销按字面还原。
8. `POST /api/resumes/{id}/revisions` 显式把工作稿保存为一个新版本（`revisions`）。
9. `GET /api/resumes/{id}/export` 导出：工作稿若与最近保存版本不一致，先自动存出一版（备注「导出前自动保存」）再返回其 Markdown；响应里的 `draft_dirty` 恒为 `false`。
10. `GET /api/resumes/{id}/deletion-preview`、`GET /api/jobs/{id}/deletion-preview` 给删除确认弹窗提供计数；`DELETE /api/resumes/{id}` 级联删除简历及其全部从属数据，`DELETE /api/jobs/{id}` 只删岗位、把历史分析的 `job_id` 置空。

## 3. API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录，写入 HttpOnly Cookie |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/me` | 当前账号 |
| GET/POST | `/api/resumes` | 列表 / 新建（原稿） |
| GET/PUT | `/api/resumes/{id}` | 详情（含版本与分析摘要）/ 重命名 |
| PUT | `/api/resumes/{id}/draft` | 保存工作稿 |
| GET/POST | `/api/resumes/{id}/revisions` | 版本列表 / 保存新版本 |
| GET | `/api/resumes/{id}/export` | 导出最新修改稿的 Markdown（工作稿有未保存改动时先自动存一版） |
| GET | `/api/resumes/{id}/deletion-preview` | 删除确认弹窗的计数（采纳建议数、分析数、版本数、进行中任务数） |
| DELETE | `/api/resumes/{id}` | 删除简历并级联删除从属数据（进行中任务时 409） |
| GET/POST | `/api/jobs` | 目标岗位列表 / 新建 |
| GET/DELETE | `/api/jobs/{id}` | 岗位详情 / 删除（历史分析保留，`job_id` 置空） |
| GET | `/api/jobs/{id}/deletion-preview` | 删除岗位弹窗的计数（关联分析数、涉及简历数） |
| GET/POST | `/api/analyses` | 分析任务列表 / 新建 |
| POST | `/api/analyses/{id}/run` | 触发（或重试）分析 |
| GET | `/api/analyses/{id}` | 任务状态、条目与建议 |
| POST | `/api/suggestions/{id}/decision` | 采纳 / 忽略 / 撤销 |
| POST | `/api/supplement` | 为「未体现 / 需要补充确认」条目补写真实经历并润色（越界返回 422，不落库） |
| POST | `/api/supplements/{id}/decision` | 采纳 / 忽略 / 撤销一条补充 |
| GET | `/api/health` | 健康检查与模型是否已配置 |

## 4. 数据表

- `users`：测试账号（口令 bcrypt 哈希）。
- `resumes`：原稿，创建后只读。
- `resume_drafts`：工作稿（每个简历一行）。
- `jobs`：目标岗位。
- `analysis_tasks`：每次分析任务 + 简历/岗位快照 + 状态机 + 模型名。`resume_id` 外键 `ON DELETE CASCADE`，`job_id` 外键 `ON DELETE SET NULL` 且可空（迁移 `0003_analysis_job_set_null`），所以删岗位不会带走历史分析。
- `analysis_items`：一条岗位要求 ↔ 简历证据 ↔ 判断 ↔ 原因 ↔ 待确认问题。
- `suggestions`：改写建议或补充问题，含 `decision` 与 `applied_at`。
- `item_supplements`：用户为某条分析条目补写的经历（用户原文、模型润色稿、`decision`、实际插入片段与锚点），用于幂等与撤销。
- `revisions`：显式保存的修改稿版本（`resume_id + version` 唯一）。

所有业务表都带 `user_id`（或可通过关联表回溯到用户），后端每个查询都强制按当前用户过滤。级联链：`resumes → resume_drafts / revisions / analysis_tasks`，`analysis_tasks → analysis_items / suggestions / item_supplements`，删简历时由数据库外键一次性清完，不手写递归，避免漏表。

## 5. 关键设计决策

| 决策 | 原因 |
| --- | --- |
| 引文必须在快照中逐字存在，否则丢弃/降级 | 把“忠于输入材料”做成**代码约束**，而不是提示词里的愿望；题目要求不能在导出阶段才做事实检查 |
| 改写建议要过“数字 + 实体”闸门 | 只校验数字不够：模型可能写“用 Kubernetes 部署”而不带任何数字。因此英文词元、中文技术词、机构／系统名、中文数量词都要能在简历原文里找到，否则降级为补充问题 |
| 与岗位无关的“表达优化建议”单独一路（模型输出的 `polish`） | 建议若只挂岗位要求，不对应任何要求的句子永远拿不到改写机会（实测某句 5/5 轮未被覆盖）；两路共用同一套校验与去重 |
| 模型温度设为 0 | 同一输入重复执行时建议条数波动明显（曾出现 5 轮中 1 轮 0 条），降低温度后 5 轮结果一致 |
| `suggestion.action` 区分“改写／补充”，且不落库 | “补充”只允许提问题，带文本即被强制降级；落库时映射为已有的 `is_question`，因此不需要新增字段和迁移 |
| 原稿不可修改 | 便于核对“原稿不变”，也避免分析快照与保存稿互相污染 |
| 分析快照在任务创建时冻结 | 保证“每次分析保留当时的简历和岗位内容”，新分析不覆盖旧保存稿 |
| 采纳采用精确字符串替换并记录状态 | 幂等、可解释；重复点击不会重复插入 |
| 补充流程把“事实基准”换成**用户本次的输入** | 用户补写的是新事实，不能拿简历原文当基准；以他这次说的话为准，用户自己提到的技术栈可以写进简历，模型自己加的会被拦下并重试 |
| 补充记录“实际插入的片段”，而不只是正文 | 插入时会补换行（走兜底还会补 `## 补充信息` 标题）；记下整段才能保证撤销**逐字还原**，不留下空行或空标题 |
| 原稿栏的悬停操作先“定位”再动作（`frontend/src/matching.ts`） | 原稿与修改稿不是一一对应：采纳改写、补充插入都会让两者分叉。所以「编辑 / 删除」两个按钮只做确定性定位——逐字唯一命中才删除；该行已被采纳的改写替换掉时先退回建议再删；定位不唯一（重复行、标题行、已被手改）就禁用按钮并在提示里说明原因，不猜 |
| 越权返回 404 而非 403 | 不泄露其他账号资源是否存在 |
| 分析任务状态机 + 启动时清理 `running` | 模型可能超时，服务可能重启；用户需要看到明确状态并能重试 |
| 导出取“当前修改稿”，必要时先自动存一版 | 导出的内容必须与屏幕上一致；代价是导出会写库并可能多出一个版本记录（备注「导出前自动保存」），所以状态机里没有“未保存就不能导出”的死路 |
| 删简历级联、删岗位置空 | 简历没了，它的分析／建议／补充／版本也就没有上下文，一起删才不留孤儿数据；岗位只是分析的输入之一，历史分析仍有复核价值，因此保留并让岗位名走快照 |
| 删除语句都带 `user_id` | 与其它接口同一套越权策略：`DELETE ... WHERE id=? AND user_id=?`，`rowcount != 1` 即 404，不会误删别的账号 |
| 模型密钥只走服务端环境变量 | 满足题目对密钥管理的要求 |

## 6. 失败与边界处理

| 情况 | 表现 |
| --- | --- |
| 未配置 `LLM_API_KEY` | 任务立即失败，页面提示“尚未配置模型密钥……” |
| 模型超时 / 返回非 JSON | 自动重试 `LLM_MAX_RETRIES` 次后失败，保留输入与已保存修改稿 |
| 模型编造引文 | 该条被丢弃或降级为“需要补充确认”，不会进入修改稿 |
| 改写里出现简历没有的技术栈／机构名／数量 | 不生成建议，自动改为补充问题，并在理由里列出命中的词 |
| 标成“补充”却带了改写文本 | 丢弃文本，强制转为 `is_question` 的补充问题 |
| 润色结果里出现用户没说过的技术栈／数字 | 把命中的词回喂给模型重试一次；仍越界则返回 422，不落库、不动修改稿 |
| 补充内容已被手动编辑，定位不唯一 | 撤销返回 409，提示手动处理 |
| 建议的原段落已被手动改掉 | 采纳返回 409，提示手动处理 |
| 工作稿有未保存改动就导出 | 先自动存出一版（备注「导出前自动保存」）再导出，导出的就是当前修改稿；只有修改稿为空时才返回 409 |
| 删除简历时还有进行中的分析 | 返回 409 并提示等任务结束，避免删到一半留下跑不完的任务 |
| 删除别的账号的简历／岗位 | 404（删除语句带 `user_id`，一行都匹配不到），对方数据不受影响 |
| 删除岗位 | 只删岗位行；历史分析保留，`job_id` 置空、岗位名走快照，旧分析页面照常可读 |
| 服务重启时任务处于 `running` | 启动时标记为失败并提示重试 |
| 空输入 | 前端即时提示；后端返回 400 |
