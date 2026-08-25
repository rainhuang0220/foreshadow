"""S3 Contribution Strategy. PR is not the default entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import AccessResult, compute_access
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
    "TOOLING": "工具链 / CI 辅助，先小补丁",
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "summary_zh": self.summary_zh,
            "steps_zh": list(self.steps_zh),
            "difficulty": self.difficulty,
            "effort": self.effort,
            "allows_direct_pr": self.allows_direct_pr,
            "why": list(self.why),
        }


def recommend_entry(
    feat: FeaturesBlob | None,
    *,
    s1: S1Result | None = None,
    access: AccessResult | None = None,
) -> StrategyResult:
    feat = feat or FeaturesBlob()
    access = access or compute_access(feat)
    why: list[str] = []
    if s1 is not None and s1.pool == "experimental":
        why.append("证据不足，实验池项目")
        return _pack(
            "DISCUSSION",
            why,
            difficulty="Research",
            effort="2h",
            direct=False,
        )
    if (
        access.merge_rate is not None
        and access.score is not None
        and access.score < 25
    ):
        why.append("进入通道偏低，先观察社区是否响应")
        return _pack("DISCUSSION", why, "Medium", "4h", False)
    if feat.bug_n is not None and feat.bug_n >= 2:
        why.append("开放样本里有多条 bug 信号")
        return _pack("REPRODUCTION", why, "Medium", "6h", False)
    if feat.gap_docs == 1:
        why.append("文档缺口（不是贡献机会本身，只是入口）")
        return _pack("DOCUMENTATION", why, "Easy", "4h", False)
    if feat.gap_tests == 1:
        why.append("测试目录缺口")
        return _pack("TEST", why, "Easy", "6h", False)
    if feat.gap_ci == 1:
        why.append("缺少 CI")
        return _pack("TOOLING", why, "Medium", "1d", False)
    if (feat.unassigned_help or 0) >= 1 or (feat.help_n or 0) >= 1:
        why.append("有未认领的求助 Issue；GFI 只作 onboarding 信号")
        titles = feat.help_issue_titles or feat.open_issue_titles or []
        if titles:
            why.append(f"建议先看：{titles[0]}")
        return _pack("ISSUE", why, "Easy", "4h", False)
    if feat.screenshot_only:
        why.append("仓库几乎只有展示材料")
        return _pack("RESEARCH", why, "Research", "2h", False)
    if access.merge_rate is not None and access.merge_rate >= 0.35:
        why.append("外部 PR 曾被接受，仍建议先 Issue 对齐")
        return _pack("BUG_FIX", why, "Medium", "1d", False)
    why.append("默认先 Issue / 讨论，不默认提 PR")
    return _pack("ISSUE", why, "Medium", "6h", False)


def _pack(
    path: EntryPath,
    why: list[str],
    difficulty: Literal["Easy", "Medium", "Hard", "Research"],
    effort: str,
    direct: bool,
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
    )
