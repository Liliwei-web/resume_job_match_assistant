"""Idempotent seed: preconfigured test accounts plus the fictional task materials.

素材是按验收场景设计的，不是随手写的样例：

* ``陈曦-前端工程师简历`` × ``高级前端工程师`` —— 三态齐全组合：React／TypeScript／
  Vite 与大型项目经历已体现；性能优化只有定性描述、拿不出量化指标，判“需要补充确认”；
  Node.js 服务端经验完全没有，判“未体现”。
* ``陈曦-前端工程师简历`` × ``后端开发工程师（Go）`` —— 明显缺口组合：Go、Docker、
  Kubernetes、MySQL、Redis 全部没写，用来验证“未体现”不会被编造；只有前后端联调
  这类“参与／配合”的模糊线索会落到“需要补充确认”。
* ``刘洋-Go后端简历`` × ``后端开发工程师（Go）`` —— 较匹配组合：Go/Gin/MySQL/Redis
  已体现，Docker 与 Kubernetes 未体现，SQL 优化、性能提升只有定性描述，用来验证
  “已体现 / 未体现 / 需要补充确认”三态同时出现。
* ``王强-口语化简历`` × ``后端开发工程师（初级）`` —— 项目经历刻意口语化，
  用来触发“只改措辞、不新增事实”的改写建议，演示采纳 / 忽略流程。
* 三份简历都**没有任何量化结果**（“优化了页面加载性能”“接口响应速度有所提升”
  后面不跟数字），用来验证系统不会自行补出“提升 30%”这类指标；同时每份简历都
  留了口语化／含糊的句子，保证每次分析都拿得到有实质改动的逐条建议。
"""
import logging

from sqlalchemy import select

from .db import SessionLocal
from .models import Job, Resume, ResumeDraft, User
from .security import hash_password

logger = logging.getLogger(__name__)

TEST_ACCOUNTS = [
    {"username": "demo1", "password": "demo1234", "display_name": "测试账号 A"},
    {"username": "demo2", "password": "demo1234", "display_name": "测试账号 B"},
]

# 前端工程师，本人求职意向就是前端：既用来匹配对口的「高级前端工程师」（三态齐全），
# 也用来匹配跨岗的「后端开发工程师（Go）」（技术栈几乎完全不重叠）。
# 刻意不含 Go、Kubernetes、Docker、MySQL、Redis、微服务、gRPC。
RESUME_FRONTEND = """# 陈曦

## 个人信息
- 求职意向：前端开发工程师
- 工作年限：3年
- 邮箱：chenxi@example.com
- 城市：重庆

## 教育背景
- 2017.09 - 2021.06 某大学 软件工程 本科

## 工作经历
### 某科技有限公司（2021.07 - 至今）
- 负责企业级后台管理系统的前端开发与维护，参与需求评审与页面还原
- 使用 React 与 TypeScript 开发权限管理、报表展示等模块
- 负责前端工程化配置维护，使用 Vite 完成构建与打包
- 与产品、设计同事沟通需求细节，输出页面实现方案
- 优化了页面加载性能，改善了首屏的交互体验
- 提升了团队开发效率，推动组件复用与代码规范落地
- 参与前端代码评审，维护团队公共组件与样式规范
- 帮运营改过页面配置，也帮忙排查了一些线上样式问题

## 项目经历
### 企业级后台管理系统
- 使用 React、TypeScript 与 HTML5、CSS3 完成管理端页面开发，覆盖权限管理、报表展示等多个业务模块
- 使用 Vue 开发内部运营配置页面
- 负责公共组件抽取与前端构建配置维护
- 参与前后端接口联调，配合排查线上页面问题
- 配合测试完成功能验证，修复页面兼容性问题

### 某科技有限公司官网改版
- 使用 HTML5 与 CSS3 完成页面布局与动效
- 使用 Vue 完成页面交互逻辑与表单校验
- 配合运营调整页面配置，跟进上线后的样式问题

## 技能
- React、Vue、TypeScript、HTML5、CSS3
"""

# Go 后端工程师，唯一缺口是容器化与微服务；性能相关表述刻意保持定性。
RESUME_GO = """# 刘洋

## 个人信息
- 求职意向：后端开发工程师（Go 方向）
- 工作年限：2年
- 邮箱：liuyang@example.com
- 城市：重庆

## 教育背景
- 2019.09 - 2023.06 某大学 计算机科学与技术 本科

## 工作经历
### 某互联网公司（2023.07 - 至今）
- 负责电商订单系统的后端开发与维护，参与需求评审与技术方案讨论
- 使用 Go 与 Gin 开发订单相关的后端接口
- 优化了慢查询 SQL，改善了数据库访问效率
- 参与代码评审，并推动接口规范统一
- 帮忙排查了一些线上报错，改完就恢复正常了
- 和前端同学一起对接口，有改动就顺手同步下文档
- 负责线上问题的排查与修复，跟进发布后的运行情况
- 与前端同事协作完成接口联调

## 项目经历
### 电商订单系统
- 使用 Go 与 Gin 实现订单创建、查询与状态流转接口
- 使用 MySQL 存储订单与商品数据，负责表结构调整与索引维护
- 使用 Redis 缓存商品详情与订单查询结果
- 负责线上问题的排查与修复，接口响应速度有所提升
- 参与订单数据表结构调整，配合排查慢查询
- 配合测试完成接口联调与问题修复
- 参与订单系统的接口文档维护与联调支持

## 技能
- Go、Gin、MySQL、Redis
"""

# 目标岗位：Go 后端。第 4、5 条是刘洋简历里完全没写的部分（未体现）；
# 第 6 条要求“能说明优化前后的效果”，而简历只有定性描述（需要补充确认）。
JOB_GO = """岗位名称：后端开发工程师（Go）

岗位职责：
1. 负责公司核心业务系统的后端接口开发与维护
2. 参与系统性能优化与线上问题排查
3. 与前端同学协作完成接口联调与上线

任职要求：
1. 熟悉 Go 语言，了解 Gin 等 Web 框架
2. 熟悉 MySQL，具备 SQL 优化经验
3. 熟悉 Redis 缓存的使用
4. 熟悉 Docker 与 Kubernetes，能够完成服务容器化部署
5. 了解微服务架构与 gRPC 通信
6. 有线上性能调优经验，能够说明优化前后的效果对比
"""

# 前端岗位，用于让「陈曦-前端工程师简历」也能跑出三态。
# 注意第 1、2 条必须分开写：把“精通 React、TypeScript”和“有大型项目经验”合成一条时，
# 模型只能按最弱的那半句判定，整条会被拖进“需要补充确认”，结果一条“已体现”都没有。
JOB_FRONTEND = """岗位名称：高级前端工程师

任职要求：
1. 精通 React、TypeScript
2. 有大型前端项目经验
3. 熟悉前端性能优化，能给出量化指标
4. 熟悉前端工程化工具 Vite/Webpack
5. 有 Node.js 服务端开发经验优先
"""

# 王强：项目经历刻意口语化，用来触发“只改措辞、不新增事实”的改写建议。
RESUME_COLLOQUIAL = """# 王强

## 教育背景
- 2020.09 - 2024.06 重庆邮电大学 软件工程 本科

## 技能
- Python、MySQL、Git

## 项目经历
### 实验室设备借用平台（后端）
- 用 Python 和 FastAPI 弄了个设备借还的接口
- 数据库表是我和同学一起建的，后面改过几次
- 帮忙看了一下接口慢的问题，做了一些调整
"""

JOB_PY_BACKEND = """岗位名称：后端开发工程师（初级）

岗位职责：
1. 负责公司业务系统的后端接口开发与维护
2. 参与数据库表结构设计与优化
3. 与前端同学协作完成联调与上线

任职要求：
1. 熟悉 Python，了解 FastAPI 或 Django 等 Web 框架
2. 熟悉 PostgreSQL 或 MySQL 等关系型数据库
3. 了解 Docker，能够使用容器部署服务
"""

JOB_DATA = """岗位名称：数据工程师

岗位职责：
1. 负责数据仓库建设与 ETL 任务开发
2. 负责数据质量监控与问题排查

任职要求：
1. 熟悉 Python 与 SQL
2. 熟悉 Spark 或 Flink 等大数据处理框架
3. 熟悉 Kubernetes 与 CI/CD 流程
4. 有数据仓库建模经验
"""

RESUME_ANALYST = """# 王芳

## 教育背景
- 2020.09 - 2024.06 某大学 信息管理 本科

## 技能
- Excel、SQL

## 项目经历
### 校园问卷调查
- 使用问卷星收集并整理问卷数据
"""


def _ensure_user(db, username: str, password: str, display_name: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, display_name=display_name, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        logger.info("seeded test account %s", username)
    return user


def _ensure_resume(db, user: User, title: str, text: str) -> None:
    existing = db.scalar(select(Resume).where(Resume.user_id == user.id, Resume.title == title))
    if existing is not None:
        return
    resume = Resume(user_id=user.id, title=title, original_text=text)
    resume.draft = ResumeDraft(content_md=text)
    db.add(resume)


def _ensure_job(db, user: User, title: str, description: str) -> None:
    existing = db.scalar(select(Job).where(Job.user_id == user.id, Job.title == title))
    if existing is not None:
        return
    db.add(Job(user_id=user.id, title=title, description=description))


def seed() -> None:
    db = SessionLocal()
    try:
        demo1 = _ensure_user(db, **TEST_ACCOUNTS[0])
        demo2 = _ensure_user(db, **TEST_ACCOUNTS[1])

        _ensure_resume(db, demo1, "陈曦-前端工程师简历", RESUME_FRONTEND)
        _ensure_resume(db, demo1, "刘洋-Go后端简历", RESUME_GO)
        _ensure_resume(db, demo1, "王强-口语化简历", RESUME_COLLOQUIAL)
        _ensure_job(db, demo1, "后端开发工程师（Go）", JOB_GO)
        _ensure_job(db, demo1, "高级前端工程师", JOB_FRONTEND)
        _ensure_job(db, demo1, "后端开发工程师（初级）", JOB_PY_BACKEND)
        _ensure_job(db, demo1, "数据工程师", JOB_DATA)

        # Account B keeps its own data so isolation can be verified.
        _ensure_resume(db, demo2, "王芳-数据分析简历", RESUME_ANALYST)
        _ensure_job(db, demo2, "数据分析实习生", "岗位要求：熟悉 SQL 与 Excel，能够整理业务数据并输出报表。")

        db.commit()
        logger.info("seed data is ready")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed()
