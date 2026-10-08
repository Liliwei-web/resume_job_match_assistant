# 110 实验室 2026 秋季招新考核 · 题目 5：简历与岗位匹配助手
> 简历文本解析，自动匹配岗位要求的工具。

面向求职者的 Web 应用：粘贴自己的简历正文与目标岗位描述，**后端调用真实 DeepSeek 模型**，逐条给出「已体现 / 未体现 / 需要补充确认」的判断与有依据的修改建议；用户自己决定采纳或忽略，编辑并保存修改稿，最后预览、导出 Markdown。

核心约束：结论必须能对应到岗位要求与简历原文；简历没写的内容只能标为「未体现 / 需要补充确认」，**不替用户编造经历、技能、年限、业绩或量化指标**。

## 仓库结构

```
.
├── README.md                 ← 本文件（总入口）
└── resume-matcher/           ← 应用本体（源码 + Dockerfile + Compose + 文档）
    ├── frontend/             React + Vite + TypeScript（nginx 托管，并反代 /api）
    ├── backend/              FastAPI + SQLAlchemy + Alembic
    ├── docker-compose.yml    db(PostgreSQL) + backend + frontend 三个服务
    ├── .env.example          不含真实密钥的环境变量示例
    ├── README.md             ★ 启动说明、模型配置、测试账号与素材、关键取舍、已知限制
    └── docs/                 架构说明、测试与验收记录、题目附件、对照表、示例导出
```

## 启动（三步）

```bash
cd resume-matcher
cp .env.example .env          # Windows: copy .env.example .env
# 打开 .env 填 LLM_API_KEY（DeepSeek 的密钥）；其余可保持默认
docker compose up --build -d
```

首次启动会自动完成：等待数据库就绪 → Alembic 迁移建表 → 灌入测试账号与预置素材。访问 <http://localhost:8080>，测试账号 **`demo1` / `demo1234`**（3 份虚构简历 + 4 份岗位）与 **`demo2` / `demo1234`**（用于验证账号隔离）。宿主机**不需要**安装 Node.js、Python 或 PostgreSQL。

健康检查：`curl http://localhost:8080/api/health`（`llm_configured` 表示密钥是否已配置）；未配置密钥时分析会明确失败并给出提示，不会用固定结果假装调用成功。

密钥只通过服务端环境变量注入：`.env` 已被 `resume-matcher/.gitignore` 忽略，仓库里只有不含真实值的 `.env.example`。

## 文档索引

| 文件 | 内容 |
| --- | --- |
| `resume-matcher/README.md` | 启动、模型配置、测试账号与预置素材、数据模型与关键取舍、已知限制、题目附件说明 |
| `resume-matcher/docs/architecture.md` | 组件、请求流、数据表与关键设计决策 |
| `resume-matcher/docs/test-results.md` | 全部实际执行过的验证步骤与结果（含未实测项与已知波动） |
| `resume-matcher/docs/evidence-comparison.csv` | 「岗位要求—简历证据—修改建议—处理结果」对照表（14 列，与出题方附件逐字节一致） |
| `resume-matcher/docs/example-export.md` | 一次真实分析采纳/忽略后保存 v1，再由导出接口原样导出的 Markdown |
| `resume-matcher/docs/题目附件/` | 出题方附件原件（`index.html` 可离线打开） |

## 关键场景（实测结果见 `resume-matcher/docs/test-results.md`）

1. **明显缺口不被编造**：陈曦（前端简历）× 后端开发工程师（Go）——Go、Docker、Kubernetes、Redis、微服务、gRPC 全判「未体现」，不会自动写进技能栏。
2. **对口组合三态齐全**：陈曦 × 高级前端工程师——React/TypeScript、Vite「已体现」，项目规模与量化指标「需要补充确认」，Node.js「未体现」。
3. **口语化不自动改写**：王强-口语化简历 × 后端开发工程师（初级）——口语化句子只给追问，改写由代码层词表闸门拦下。
4. **采纳 / 忽略 / 重复采纳 + 保存与导出**：采纳只改修改稿、忽略不动正文、重复采纳不重复插入；导出正文与保存稿逐字相等，不夹带分析说明。
5. **账号隔离与持久化**：跨账号 10 个入口全部 404；保留数据卷重建容器后原稿、分析结果、保存稿仍在。