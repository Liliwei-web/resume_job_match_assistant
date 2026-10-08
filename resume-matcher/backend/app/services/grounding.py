"""Grounding rules.

Two guarantees are enforced here, in code, on every analysis:

1. Every quote that reaches the database is a literal slice of the snapshot it
   claims to come from. Content the model invents is dropped instead of trusted.
2. Every rewrite stays inside the candidate's own material: it may not introduce
   numbers, technologies, employers, projects or quantities the resume never
   mentioned. Anything that does is downgraded to a confirmation question.
"""
import re

from ..models import MATCH_ABSENT, MATCH_NEEDS_CHECK, MATCH_SHOWN, MATCH_STATUSES

# suggestion.action 的取值（模型输出契约，落库时映射为 is_question）
ACTION_REWRITE = "改写"
ACTION_APPEND = "补充"
ACTION_LABELS = (ACTION_REWRITE, ACTION_APPEND)

# 中文技术栈/方法论关键词：出现在改写建议里，就必须能在简历原文里找到同样的说法。
ENTITY_LEXICON = (
    "微服务",
    "消息队列",
    "分布式",
    "高并发",
    "容器",
    "集群",
    "数据仓库",
    "数据湖",
    "数据中台",
    "数据质量",
    "机器学习",
    "深度学习",
    "推荐系统",
    "搜索引擎",
    "负载均衡",
    "中间件",
    "单元测试",
    "自动化测试",
    "持续集成",
    "持续交付",
    "敏捷开发",
    "领域驱动",
    "性能压测",
    "爬虫",
    "报表",
)

# 机构/系统类后缀：命中时，后缀前面的“实体核心”必须出现在简历原文里。
ENTITY_SUFFIXES = (
    "公司",
    "集团",
    "科技",
    "大学",
    "学院",
    "学校",
    "研究院",
    "研究所",
    "实验室",
    "平台",
    "系统",
    "中心",
    "银行",
    "事业部",
    "工作室",
    "项目组",
    "团队",
    "部门",
)

# 实体核心至少要有 3 个汉字，避免把“的团队”这类普通表述当成编造实体。
MIN_ENTITY_CORE = 3


def find_quote(text: str, quote: str | None) -> str | None:
    """Return the exact slice of ``text`` that matches ``quote`` (whitespace tolerant)."""
    if not quote:
        return None
    candidate = quote.strip()
    if not candidate:
        return None
    if candidate in text:
        return candidate
    parts = [part for part in re.split(r"\s+", candidate) if part]
    if not parts:
        return None
    pattern = re.compile(r"\s+".join(re.escape(part) for part in parts))
    match = pattern.search(text)
    return match.group(0) if match else None


_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def introduces_new_numbers(suggested: str, original: str, resume_text: str) -> bool:
    """True when the rewrite contains a number that appears nowhere in the resume.

    This is the code-level guarantee behind the rule "never invent quantified
    results": a rewrite may reuse digits the candidate already wrote, but it may
    not introduce new ones.
    """
    known = set(_NUMBER_RE.findall(original)) | set(_NUMBER_RE.findall(resume_text))
    return any(number not in known for number in _NUMBER_RE.findall(suggested))


# 技术栈/工具/公司英文名：字母开头，允许 FastAPI、CI/CD、Node.js、C++ 这类写法。
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.+#/_-][A-Za-z0-9]+)*")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
# 中文数量词：只在“数字 + 单位”时才算，避免“一起”“统一”这类误判。
_CJK_QUANTITY_RE = re.compile(
    r"[一二三四五六七八九十百千万亿]+(?:个|次|年|月|日|天|人|倍|成|条|款|周|小时|分钟|秒|万|亿)"
)


def _squeeze(text: str | None) -> str:
    """Drop all whitespace and case, so line breaks never cause a false negative."""
    return re.sub(r"\s+", "", text or "").lower()


# 同一组内的词互换不携带任何新信息：只把“有所提升”换成“得到提升”不算改写。
_EQUIVALENT_WEAK_WORDS = (
    ("有所", "得到", "有了"),
    ("进行", "开展", "做了", "作出"),
    ("配合", "协助", "协同"),
)

# 助词/结构虚词：只增删这些字同样不构成实质改写。
_EMPTY_PARTICLES = "了的着过地得"

# 空泛名词：只加一个“问题”“情况”不带来任何新信息。
_FILLER_NOUNS = ("问题", "情况", "相关", "方面", "内容", "等等", "之类")


# 口语化／非专业动词。本轮边界是“只提问、不自动改写”（见 ``app/llm.py`` 的
# 「本轮暂不开放：口语化表述一律不自动改写」）。提示词里已经写明，但模型仍会偶尔
# 给出“弄了个 → 实现”这类换词建议——事实边界一向由这一层兜底，所以这里用词表再拦一道。
_COLLOQUIAL_MARKERS = (
    "弄了个", "弄一下", "弄了", "搞了个", "搞了", "搞定", "整了", "整了个",
    "写了点", "做了个", "看了下", "看了一下", "帮忙", "顺手", "差不多",
    "改过几次", "弄", "搞",
)


def find_colloquial_marker(passage: str | None) -> str | None:
    """原文里出现口语化／非专业动词时返回命中的那个词，否则 None。"""
    for marker in _COLLOQUIAL_MARKERS:
        if marker in (passage or ""):
            return marker
    return None


def _is_no_substantive_change(original: str, suggested: str) -> bool:
    """True when the two texts differ only by filler words, not by information.

    归一化三步后完全相同，就说明这次“改写”没有带来任何新信息：
    1. 去掉空白与大小写差异；
    2. 把每组等价弱表达统一成组内第一个词（有所／得到／有了）；
    3. 去掉“了／的／着／过／地／得”这类只影响语气和结构的虚词，以及
       “问题／情况”这类空泛名词。
    """
    def canonical(text: str) -> str:
        squeezed = _squeeze(text)
        for group in _EQUIVALENT_WEAK_WORDS:
            for word in group[1:]:
                squeezed = squeezed.replace(word, group[0])
        for particle in _EMPTY_PARTICLES:
            squeezed = squeezed.replace(particle, "")
        for noun in _FILLER_NOUNS:
            squeezed = squeezed.replace(noun, "")
        return squeezed

    return canonical(original) == canonical(suggested)


def _entity_candidates(text: str) -> list[tuple[str, str]]:
    """Return (core, suffix) pairs for机构/系统-style names found in ``text``."""
    candidates: list[tuple[str, str]] = []
    for run in _CJK_RUN_RE.findall(text):
        for suffix in ENTITY_SUFFIXES:
            start = 0
            while True:
                index = run.find(suffix, start)
                if index == -1:
                    break
                candidates.append((run[max(0, index - 6) : index], suffix))
                start = index + 1
    return candidates


def find_unsupported_terms(suggested: str, resume_text: str) -> list[str]:
    """Terms in a rewrite that the resume never mentions.

    Three layers, deliberately precise rather than aggressive:

    * ASCII tokens (Kubernetes, Redis, AWS, ...) must appear in the resume;
    * Chinese tech/method keywords must appear in the resume;
    * a name ending in an institution/system suffix is accepted only when at
      least ``MIN_ENTITY_CORE`` characters in front of that suffix can be found
      in the resume — so “校园招聘平台” is rejected while a rewrite that keeps
      “实验室设备借用平台” intact is not.

    A plain “every content word must appear verbatim” rule was rejected because
    it misfires on legitimate rewrites such as
    ``设备借还的接口`` → ``设备借还接口``.
    """
    resume = _squeeze(resume_text)
    squeezed = _squeeze(suggested)
    unsupported: list[str] = []

    for token in _ASCII_TOKEN_RE.findall(suggested):
        if _squeeze(token) not in resume:
            unsupported.append(token)

    for term in ENTITY_LEXICON:
        if term in squeezed and term not in resume:
            unsupported.append(term)

    for core, suffix in _entity_candidates(suggested):
        if len(core) < MIN_ENTITY_CORE:
            # 后缀前面凑不出一个够长的实体核心（例如“负责实验室…”里的“实验室”），
            # 说明这不是一个可判定的机构/系统名，跳过以免误伤。
            continue
        supported = any(
            len(core) - index >= MIN_ENTITY_CORE and (core[index:] + suffix) in resume
            for index in range(len(core))
        )
        if not supported:
            unsupported.append(core + suffix)

    for quantity in _CJK_QUANTITY_RE.findall(suggested):
        if quantity not in resume:
            unsupported.append(quantity)

    return list(dict.fromkeys(unsupported))


def supplement_violations(suggested: str, user_input: str) -> list[str]:
    """模型润色后的补充内容里，用户自己没说过的实体与数字。

    与改写建议不同：这里的“原文”是**用户这次的输入**，而不是简历，所以
    用户自己写出来的技术栈、公司、数字都属于合法输入；只有模型额外加出来的
    才算越界（这正是“不能替用户编造经历”的那条铁律）。
    """
    violations: list[str] = []
    if introduces_new_numbers(suggested, user_input, user_input):
        violations.append("数字/量化指标")
    violations.extend(find_unsupported_terms(suggested, user_input))
    return list(dict.fromkeys(violations))


def clean_suggestion(
    raw_suggestion, resume_text: str, question: str | None
) -> tuple[dict | None, str]:
    """校验单条 suggestion，返回 (可用建议 或 None, 被拦下的原因)。

    “改写/补充”语义、逐字接地、数字闸门、实体闸门与口语化闸门都集中在这里，
    岗位条目建议和与岗位无关的“表达优化建议”共用同一套规则，避免两处判罚不一致。
    """
    if not isinstance(raw_suggestion, dict):
        return None, ""

    original = find_quote(resume_text, str(raw_suggestion.get("original_passage") or ""))
    suggested = str(raw_suggestion.get("suggested_passage") or "").strip()
    section = str(raw_suggestion.get("section") or "").strip()
    rewrite_reason = str(raw_suggestion.get("rewrite_reason") or "").strip()
    action = str(raw_suggestion.get("action") or "").strip()
    if action not in ACTION_LABELS:
        # 没给 action（历史输出或模型漏字段）时按内容推断，绝不默认放行。
        action = ACTION_REWRITE if suggested else ACTION_APPEND

    # 原文偏口语时本轮不接受改写：模型偶尔仍会给出“弄了个 → 实现”这类换词，
    # 一旦溜过去就等于系统替用户改了措辞，正好是这条边界要防的事。
    colloquial = find_colloquial_marker(original) if suggested else None

    blocked_reason = ""
    if action == ACTION_APPEND:
        # “补充”只能提问，不允许携带改写文本。
        if suggested:
            blocked_reason = "该建议被标为“补充”，但“补充”不允许携带改写文本，已改为待确认问题。"
        suggested = ""
    elif colloquial:
        blocked_reason = (
            f"原文里的“{colloquial}”偏口语，本轮不自动改写。建议改成更专业的书面表述"
            "（例如“实现”“负责”“排查”这类动词），请你按真实情况自行改写。"
        )
        suggested = ""
        question = question or blocked_reason
    elif original and suggested and (
        _squeeze(suggested) == _squeeze(original)
        or _is_no_substantive_change(original, suggested)
    ):
        # 改写结果与原文一字不差，或只在“有所／得到”“了／的”这类虚词上动过刀：
        # 采纳后正文不会变得更有信息量，这不是建议而是噪声，直接丢弃；
        # 也不降级成提问，因为原文本身没有信息缺口。
        return None, "改写结果与简历原文没有实质差别（只动了虚词），已丢弃该建议。"
    elif not original or not suggested:
        blocked_reason = (
            rewrite_reason or "该信息在简历中缺失，需要先向你确认，不能自动写入正文。"
        )
        suggested = ""
    elif introduces_new_numbers(suggested, original, resume_text):
        blocked_reason = "改写结果可能引入了原材料没有的数字，已改为待确认问题。"
        suggested = ""
    else:
        unsupported = find_unsupported_terms(suggested, resume_text)
        if unsupported:
            blocked_reason = (
                "改写结果包含简历原文中没有的术语（"
                + "、".join(unsupported[:5])
                + "），已改为待确认问题。"
            )
            suggested = ""

    if original and suggested:
        return (
            {
                "section": section,
                "original_passage": original,
                "suggested_passage": suggested,
                "rewrite_reason": rewrite_reason,
                "is_question": False,
            },
            "",
        )
    if question:
        return (
            {
                "section": section,
                "original_passage": original,
                "suggested_passage": None,
                "rewrite_reason": blocked_reason
                or rewrite_reason
                or "该信息在简历中缺失，需要先向你确认，不能自动写入正文。",
                "is_question": True,
            },
            blocked_reason,
        )
    return None, blocked_reason


def normalize_polish(
    raw_entries, resume_text: str, used_passages: set[str] | None = None
) -> list[dict]:
    """与岗位要求无关的“表达优化建议”：不对应任何要求、但本身有结构或排版问题的句子。

    只接收能直接改写的条目（没有可改写文本、或被降级成提问的一律丢弃——提问必须挂在
    某条岗位要求上才有地方显示），并与岗位条目已经产生的建议按 original_passage 去重，
    避免同一条被给两次。
    """
    used = used_passages or set()
    polished: list[dict] = []
    for raw in raw_entries or []:
        suggestion, _ = clean_suggestion(raw, resume_text, None)
        if (
            suggestion is None
            or suggestion["is_question"]  # polish 只承载改写；提问没有对应要求可挂
            or suggestion["original_passage"] in used
        ):
            continue
        used.add(suggestion["original_passage"])
        polished.append(suggestion)
    return polished


def normalize_items(raw_items: list, resume_text: str, job_text: str) -> list[dict]:
    """Validate model output against the two snapshots and drop anything ungrounded."""
    normalized: list[dict] = []
    used_passages: set[str] = set()

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        requirement = find_quote(job_text, str(raw.get("requirement_quote") or ""))
        if requirement is None:
            # A requirement that is not verbatim in the job description cannot be trusted.
            continue

        evidence = find_quote(resume_text, str(raw.get("evidence_quote") or ""))
        status = str(raw.get("match_status") or "").strip()
        if status not in MATCH_STATUSES:
            status = MATCH_NEEDS_CHECK
        if status == MATCH_SHOWN and evidence is None:
            # Claimed support that cannot be found in the resume -> do not trust the claim.
            status = MATCH_NEEDS_CHECK
        if status == MATCH_ABSENT:
            # "未体现" means there is no clue at all, so it must not carry a quote.
            evidence = None

        reason = str(raw.get("reason") or "").strip()
        question = str(raw.get("confirmation_question") or "").strip() or None
        if status in (MATCH_ABSENT, MATCH_NEEDS_CHECK) and not question:
            question = f"简历中没有与“{requirement}”直接相关的信息，请补充说明相关经历或技能。"

        suggestions: list[dict] = []
        suggestion, _ = clean_suggestion(raw.get("suggestion"), resume_text, question)
        if suggestion is not None:
            passage = suggestion["original_passage"]
            if passage and passage in used_passages:
                # 同一句原文只跟第一条要求挂建议：两条要求命中同一句话时，
                # 重复列出同一条改写只会让用户看到两遍一样的内容。
                suggestion = None
            else:
                if passage:
                    used_passages.add(passage)
                suggestions.append(suggestion)

        normalized.append(
            {
                "requirement_quote": requirement,
                "evidence_quote": evidence,
                "match_status": status,
                "reason": reason,
                "confirmation_question": question,
                "suggestions": suggestions,
            }
        )

    return normalized
