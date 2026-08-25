"""S3 Contribution Strategy. PR is not the default entry."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import AccessResult, compute_access
from foreshadow.pipeline.features import clip
from foreshadow.pipeline.s1 import S1Result

EntryPath = Literal[
    "ISSUE",
    "DISCUSSION",
    "REPRODUCTION",
    "BENCHMARK",
    "DOCUMENTATION",
    "INTEGRATION",
    "BUG_FIX",
    "FEATURE",
    "PERFORMANCE",
    "TEST",
    "TOOLING",
    "RESEARCH",
]

DEFAULT_SKILLS = ("Python", "docs", "tests", "AI/LLM", "Agent", "RAG", "Memory")
HARD_LANGS = frozenset({"rust", "c", "c++", "cuda", "fortran"})

PATH_ZH = {
    "ISSUE": "先跟进 Issue，不要直接提 PR",
    "DISCUSSION": "先参与讨论，项目还不宜直接改代码",
    "REPRODUCTION": "先复现问题，再记录给维护者",
    "BENCHMARK": "先做测量 / 基准，再讨论优化",
    "DOCUMENTATION": "从文档与入门材料开始",
    "INTEGRATION": "适合做集成，但先发方案再写代码",
    "BUG_FIX": "确认 bug 后可以准备修复，仍须先沟通",
    "FEATURE": "新功能需先对齐 roadmap / Issue",
    "PERFORMANCE": "性能方向：测量 → Issue → 再优化",
    "TEST": "从补测试开始，风险较低",
    "TOOLING": "先看 CI / 工作流，再讨论最小改动",
    "RESEARCH": "先阅读与调研，不要急着提 PR",
}


@dataclass
class StrategyResult:
    path: EntryPath
    summary_zh: str
    steps_zh: list[str]
    difficulty: Literal["Easy", "Medium", "Hard", "Research"]
    effort: str
    allows_direct_pr: bool
    why: list[str] = field(default_factory=list)
    long_term: dict[str, Any] = field(default_factory=dict)
    language: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "summary_zh": self.summary_zh,
            "steps_zh": list(self.steps_zh),
            "difficulty": self.difficulty,
            "effort": self.effort,
            "allows_direct_pr": self.allows_direct_pr,
            "why": list(self.why),
            "long_term": dict(self.long_term),
            "language": self.language,
        }


def recommend_entry(
    feat: FeaturesBlob | None,
    *,
    s1: S1Result | None = None,
    access: AccessResult | None = None,
    language: str | None = None,
    skills: Sequence[str] | None = None,
) -> StrategyResult:
    feat = feat or FeaturesBlob()
    access = access or compute_access(feat)
    skills = tuple(skills) if skills is not None else DEFAULT_SKILLS
    why: list[str] = []
    hard = _language_too_hard(language, skills)
    if s1 is not None and s1.pool == "experimental":
        why.append("证据不足，实验池项目")
        return _pack(
            "DISCUSSION",
            why,
            difficulty="Research",
            effort="2h",
            direct=False,
            s1=s1,
            access=access,
            language=language,
        )
    if (
        access.merge_rate is not None
        and access.score is not None
        and access.score < 25
    ):
        why.append("进入通道偏低，先观察社区是否响应")
        return _pack("DISCUSSION", why, "Medium", "4h", False, s1, access, language)
    if feat.bug_n is not None and feat.bug_n >= 2:
        why.append("开放样本里有多条 bug 信号")
        path: EntryPath = "ISSUE" if hard else "REPRODUCTION"
        titles = feat.help_issue_titles or feat.open_issue_titles or []
        if titles:
            why.append(f"建议先看：{titles[0]}")
        if hard:
            why.append(f"主语言是 {language}，先跟 Issue / 复现说明，不建议重写核心")
        return _pack(path, why, "Medium", "6h", False, s1, access, language)
    if feat.gap_docs == 1:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("文档缺口（不是贡献机会本身，只是入口）")
            return _pack("DOCUMENTATION", why, "Easy", "4h", False, s1, access, language)
        why.append("有文档缺口，但外部接受未知、为 0、或进入通道偏低，先 Issue，不要直接补 CONTRIBUTING.md")
        return _pack("ISSUE", why, "Easy", "4h", False, s1, access, language)
    if feat.gap_tests == 1 and not hard:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("测试目录缺口")
            return _pack("TEST", why, "Easy", "6h", False, s1, access, language)
        why.append("测试缺口在外部接受未知时不能当成补测试 PR")
        return _pack("ISSUE", why, "Easy", "4h", False, s1, access, language)
    if feat.gap_ci == 1 and not hard:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("缺少 CI")
            return _pack("TOOLING", why, "Medium", "1d", False, s1, access, language)
        why.append("缺少 CI，但先讨论，不要直接提工作流 PR")
        return _pack("ISSUE", why, "Easy", "4h", False, s1, access, language)
    if (feat.unassigned_help or 0) >= 1 or (feat.help_n or 0) >= 1:
        why.append("有未认领的求助 Issue；GFI 只作 onboarding 信号")
        titles = feat.help_issue_titles or feat.open_issue_titles or []
        if titles:
            why.append(f"建议先看：{titles[0]}")
        return _pack("ISSUE", why, "Easy", "4h", False, s1, access, language)
    if feat.screenshot_only:
        why.append("仓库几乎只有展示材料")
        return _pack("RESEARCH", why, "Research", "2h", False, s1, access, language)
    if access.merge_rate is not None and access.merge_rate >= 0.35:
        why.append("外部 PR 曾被接受，仍建议先 Issue 对齐")
        path = "ISSUE" if hard else "BUG_FIX"
        if hard:
            why.append(f"主语言是 {language}，不要一上来改核心实现")
        return _pack(path, why, "Medium", "1d", False, s1, access, language)
    why.append("默认先 Issue / 讨论，不默认提 PR")
    if hard:
        why.append(f"主语言是 {language}，按你当前能力走 Issue / 文档")
    return _pack("ISSUE", why, "Medium", "6h", False, s1, access, language)


def _accepts_code_entry(access: AccessResult) -> bool:
    """Code-shaped paths need a known, non-zero external merge rate."""
    return access.merge_rate is not None and access.merge_rate > 0


def _language_too_hard(language: str | None, skills: Sequence[str]) -> bool:
    if not language:
        return False
    lang = language.strip().lower()
    if lang not in HARD_LANGS:
        return False
    skill_l = {s.strip().lower() for s in skills}
    aliases = {lang, "c/c++", "c++", "rust"}
    return skill_l.isdisjoint(aliases)


def long_term_potential(
    *,
    s1: S1Result | None,
    access: AccessResult | None,
) -> dict[str, Any]:
    bits: list[float] = []
    missing: list[str] = []
    if access is not None and access.score is not None:
        bits.append(float(access.score))
    else:
        missing.append("access")
    if s1 is not None and s1.evidence is not None:
        bits.append(float(s1.evidence))
    else:
        missing.append("evidence")
    if s1 is not None and s1.stage:
        bits.append(
            {
                "BREAKOUT": 85.0,
                "VALIDATED_EARLY": 78.0,
                "EMERGING": 70.0,
                "SCALING": 60.0,
                "MATURE": 40.0,
                "ESTABLISHED": 38.0,
                "STAGNANT": 12.0,
                "EXPERIMENTAL": 28.0,
            }.get(s1.stage, 50.0)
        )
    if not bits:
        return {
            "score": None,
            "class": None,
            "missing": missing,
            "why": "UNKNOWN (no long-term sample); not 0",
        }
    score = clip(sum(bits) / len(bits), 0, 100)
    label = "low"
    if score >= 70:
        label = "high"
    elif score >= 45:
        label = "medium"
    return {
        "score": round(score, 4),
        "class": label,
        "missing": missing,
        "why": "access × evidence × stage; not a promise you will become a core contributor",
    }


def _pack(
    path: EntryPath,
    why: list[str],
    difficulty: Literal["Easy", "Medium", "Hard", "Research"],
    effort: str,
    direct: bool,
    s1: S1Result | None = None,
    access: AccessResult | None = None,
    language: str | None = None,
) -> StrategyResult:
    steps = {
        "DISCUSSION": ["阅读 README 与最近讨论", "写下你的理解", "准备提问，等待维护者", "不要直接发 PR"],
        "REPRODUCTION": ["克隆仓库", "运行测试", "复现报告的问题", "把复现步骤发给维护者", "等回复后再改代码"],
        "DOCUMENTATION": ["阅读 CONTRIBUTING", "找出过时或不清的段落", "先开 Issue 说明文档缺口", "小补丁需确认后再提交"],
        "TEST": ["跑通现有测试", "为缺口补一条测试", "本地提交", "等待确认再发到 GitHub"],
        "TOOLING": ["查看 CI / 工作流", "提出最小改动", "先讨论", "不默认大重构"],
        "ISSUE": ["阅读相关 Issue", "评论复现或补充信息", "等维护者回应", "再决定是否写代码"],
        "BUG_FIX": ["复现 bug", "开或跟进 Issue", "本地实现最小修复", "用户确认后才创建 PR"],
        "FEATURE": ["读 roadmap / Issue", "先讨论范围", "实现", "用户确认后才 PR"],
        "BENCHMARK": ["建立可重复测量", "把数字写进 Issue", "讨论目标后再优化"],
        "PERFORMANCE": ["先测量", "Issue 说明瓶颈", "再考虑优化 PR"],
        "INTEGRATION": ["写清集成方案", "讨论接口", "再实现"],
        "RESEARCH": ["阅读架构与最近 release", "记录笔记", "不提交代码"],
    }[path]
    return StrategyResult(
        path=path,
        summary_zh=PATH_ZH[path],
        steps_zh=steps,
        difficulty=difficulty,
        effort=effort,
        allows_direct_pr=direct,
        why=why,
        long_term=long_term_potential(s1=s1, access=access),
        language=language,
    )
