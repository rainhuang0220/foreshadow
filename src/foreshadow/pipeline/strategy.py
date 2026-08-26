"""S3 Contribution Strategy. PR is not the default entry."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from foreshadow.models import FeaturesBlob
from foreshadow.pipeline.access import AccessResult, compute_access
from foreshadow.pipeline.features import clip, is_readme_only_tree
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
    full_name: str | None = None,
    blurb: str | None = None,
) -> StrategyResult:
    feat = feat or FeaturesBlob()
    access = access or compute_access(feat)
    skills = tuple(skills) if skills is not None else DEFAULT_SKILLS
    why: list[str] = []
    hard = _language_too_hard(language, skills)
    pack_kw: dict[str, Any] = {
        "s1": s1,
        "access": access,
        "language": language,
        "feat": feat,
        "full_name": full_name,
        "blurb": blurb,
    }
    if s1 is not None and s1.pool == "experimental":
        why.append("证据不足，实验池项目")
        return _pack(
            "DISCUSSION",
            why,
            difficulty="Research",
            effort="2h",
            direct=False,
            **pack_kw,
        )
    if (
        access.merge_rate is not None
        and access.score is not None
        and access.score < 25
    ):
        why.append("进入通道偏低，先观察社区是否响应")
        return _pack("DISCUSSION", why, "Medium", "4h", False, **pack_kw)
    if feat.bug_n is not None and feat.bug_n >= 2:
        why.append("开放样本里有多条 bug 信号")
        path: EntryPath = "ISSUE" if hard else "REPRODUCTION"
        titles = feat.help_issue_titles or feat.open_issue_titles or []
        if titles:
            why.append(f"建议先看：{titles[0]}")
        if hard:
            why.append(f"主语言是 {language}，先跟 Issue / 复现说明，不建议重写核心")
        return _pack(path, why, "Medium", "6h", False, **pack_kw)
    if feat.screenshot_only and _tree_has_source(feat):
        why.append("README 以展示材料为主，但仓库有源码，先测量再讨论")
        return _pack("BENCHMARK", why, "Research", "4h", False, **pack_kw)
    if feat.gap_docs == 1:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("文档缺口（不是贡献机会本身，只是入口）")
            return _pack("DOCUMENTATION", why, "Easy", "4h", False, **pack_kw)
        why.append("有文档缺口，但外部接受未知、为 0、或进入通道偏低，先 Issue，不要直接补 CONTRIBUTING.md")
        return _pack("ISSUE", why, "Easy", "4h", False, **pack_kw)
    if feat.gap_tests == 1 and not hard:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("测试目录缺口")
            return _pack("TEST", why, "Easy", "6h", False, **pack_kw)
        why.append("测试缺口在外部接受未知时不能当成补测试 PR")
        return _pack("ISSUE", why, "Easy", "4h", False, **pack_kw)
    if feat.gap_ci == 1 and not hard:
        if _accepts_code_entry(access) and (access.score is None or access.score >= 25):
            why.append("缺少 CI")
            return _pack("TOOLING", why, "Medium", "1d", False, **pack_kw)
        why.append("缺少 CI，但先讨论，不要直接提工作流 PR")
        return _pack("ISSUE", why, "Easy", "4h", False, **pack_kw)
    if (feat.unassigned_help or 0) >= 1 or (feat.help_n or 0) >= 1:
        why.append("有未认领的求助 Issue；GFI 只作 onboarding 信号")
        titles = feat.help_issue_titles or feat.open_issue_titles or []
        if titles:
            why.append(f"建议先看：{titles[0]}")
        return _pack("ISSUE", why, "Easy", "4h", False, **pack_kw)
    if feat.screenshot_only:
        why.append("仓库几乎只有展示材料")
        return _pack("RESEARCH", why, "Research", "2h", False, **pack_kw)
    if access.merge_rate is not None and access.merge_rate >= 0.35:
        why.append("外部 PR 曾被接受，仍建议先 Issue 对齐")
        path = "ISSUE" if hard else "BUG_FIX"
        if hard:
            why.append(f"主语言是 {language}，不要一上来改核心实现")
        return _pack(path, why, "Medium", "1d", False, **pack_kw)
    why.append("默认先 Issue / 讨论，不默认提 PR")
    if hard:
        why.append(f"主语言是 {language}，按你当前能力走 Issue / 文档")
    return _pack("ISSUE", why, "Medium", "6h", False, **pack_kw)


def _tree_has_source(feat: FeaturesBlob) -> bool:
    if feat.tree_kind == "readme_only":
        return False
    if feat.tree_kind == "has_source":
        return True
    names = feat.tree_names or []
    return bool(names) and not is_readme_only_tree(names)


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
    feat: FeaturesBlob | None = None,
    full_name: str | None = None,
    blurb: str | None = None,
) -> StrategyResult:
    why = list(why)
    titles = []
    if feat is not None:
        titles = list(feat.help_issue_titles or feat.open_issue_titles or [])
    if titles and not any("建议先看：" in w for w in why):
        why.append(f"建议先看：{titles[0]}")
    if language and not any("主语言" in w for w in why):
        why.append(f"主语言 {language}")
    return StrategyResult(
        path=path,
        summary_zh=PATH_ZH[path],
        steps_zh=customize_steps(
            path,
            feat=feat,
            language=language,
            full_name=full_name,
            blurb=blurb,
        ),
        difficulty=difficulty,
        effort=effort,
        allows_direct_pr=direct,
        why=why,
        long_term=long_term_potential(s1=s1, access=access),
        language=language,
    )


_STOP = "停在这里。任何发到 GitHub 的操作都要你确认。"
_ORD = ("第一步", "第二步", "第三步", "第四步", "第五步", "第六步")
_HEAD_HINTS = (
    "install",
    "setup",
    "getting started",
    "quick start",
    "quickstart",
    "usage",
    "example",
    "demo",
    "benchmark",
    "contributing",
    "how to",
)


def customize_steps(
    path: EntryPath,
    *,
    feat: FeaturesBlob | None = None,
    language: str | None = None,
    full_name: str | None = None,
    inspect: dict[str, Any] | None = None,
    cited: dict[str, Any] | None = None,
    cloned: bool = False,
    blurb: str | None = None,
) -> list[str]:
    """Concrete 第一步/第二步. Never tells the user to open a PR."""
    feat = feat or FeaturesBlob()
    inspect = inspect or {}
    cited = cited or {}
    lines = _path_lines(
        path,
        project=full_name or "这个项目",
        ticket=_ticket(feat, cited),
        readme_bit=_readme_bit(_useful_headings(feat, inspect)),
        shape=_shape_zh(feat, inspect),
        hint=str(inspect.get("install_hint") or "").strip(),
        cloned=cloned,
        language=language,
        blurb=blurb,
    )
    if cloned:
        lines = [
            ln
            for ln in lines
            if "克隆仓库" not in ln and "打开本机 FORESHADOW.md" not in ln
        ]
        first = _cloned_first_work(inspect, cited)
        extra = _cloned_side_evidence(inspect, cited)
        lines = [first, *extra, *lines]
        backend = "后台记录在 FORESHADOW.md"
        if backend not in lines:
            if _STOP in lines:
                lines.insert(lines.index(_STOP), backend)
            else:
                lines.append(backend)
    kind = str((inspect.get("tests") or {}).get("kind") or "")
    if kind == "node":
        lines.append("已跳过 Node 测试（不执行 npm）")
    elif kind == "cargo":
        lines.append("已跳过 Cargo 测试（不执行 cargo）")
    labeled = _label_steps(lines)
    first = labeled[0].lower() if labeled else ""
    if any(tok in first for tok in ("push", "create_pr", "open pr", "开 pr", "创建 pr")):
        labeled.insert(0, "第一步：先完成本机验证，不要发到 GitHub")
    return labeled


def _label_steps(lines: list[str]) -> list[str]:
    out: list[str] = []
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        if text.startswith("第") and "步" in text[:4]:
            out.append(text)
            continue
        prefix = _ORD[i] if i < len(_ORD) else f"第{i + 1}步"
        out.append(f"{prefix}：{text}")
    return out


def _ticket(feat: FeaturesBlob, cited: dict[str, Any]) -> str | None:
    if cited.get("number"):
        title = str(cited.get("title") or "").strip()
        return f"#{cited['number']}" + (f" {title}" if title else "")
    for group in (feat.help_issue_titles or [], feat.open_issue_titles or []):
        for raw in group:
            text = str(raw).strip()
            if text:
                return text
    return None


def _useful_headings(feat: FeaturesBlob, inspect: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    for src in (
        inspect.get("readme_headings") or [],
        inspect.get("contributing_headings") or [],
        feat.readme_headings or [],
    ):
        raw.extend(src)
    seen: set[str] = set()
    preferred: list[str] = []
    other: list[str] = []
    for item in raw:
        title = str(item).strip()
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        if any(hint in key for hint in _HEAD_HINTS):
            preferred.append(title)
        else:
            other.append(title)
    return (preferred + other)[:5]


def _first_present(items: Any) -> str | None:
    for item in items or []:
        text = str(item).strip()
        if text:
            return text
    return None


def _cloned_first_work(inspect: dict[str, Any], cited: dict[str, Any]) -> str:
    """第一步 is the work. FORESHADOW.md / ISSUE_DRAFT.md are backend evidence."""
    cmd = _first_present(inspect.get("issue_commands"))
    test = _first_present(inspect.get("test_files"))
    related = _first_present(inspect.get("related_files"))
    if cmd:
        number = cited.get("number")
        issue_ref = f"Issue #{number}" if number not in (None, "") else "Issue"
        return (
            f"运行 `{cmd}`，核对 {issue_ref} 描述的行为。"
            "缺依赖就停，不要擅自安装。"
        )
    if test:
        return f"对仓库已有 `{test}` 做安全检查（collect-only）。"
    if related:
        return f"对照 Issue，验证 `{related}` 中的行为（路径仅作证据）。"
    return "UNKNOWN：不要编造。"


def _cloned_side_evidence(inspect: dict[str, Any], cited: dict[str, Any]) -> list[str]:
    """Cite a real related file after 第一步 when the work was a command or test."""
    del cited
    if _first_present(inspect.get("issue_commands")) or _first_present(
        inspect.get("test_files")
    ):
        related = _first_present(inspect.get("related_files"))
        if related:
            return [f"对照 Issue，验证 `{related}` 中的行为（路径仅作证据）。"]
    return []


def _clip_blurb(blurb: str | None) -> str:
    text = " ".join(str(blurb or "").split())
    if not text:
        return ""
    if len(text) > 80:
        return text[:77].rstrip() + "…"
    return text


def _readme_bit(heads: list[str]) -> str:
    if not heads:
        return ""
    quoted = "、".join(f"「{h}」" for h in heads[:3])
    return f"，先看 {quoted}"


def _shape_zh(feat: FeaturesBlob, inspect: dict[str, Any]) -> str | None:
    names: list[str] = []
    names.extend(str(n) for n in (inspect.get("top_entries") or []))
    names.extend(str(n) for n in (feat.tree_names or []))
    lower = {n.lower() for n in names}
    kind = inspect.get("kind")
    if not kind:
        if {"pyproject.toml", "setup.py", "setup.cfg"} & lower:
            kind = "python"
        elif "package.json" in lower:
            kind = "node"
        elif "cargo.toml" in lower:
            kind = "rust"
        elif "go.mod" in lower:
            kind = "go"
    return {
        "python": "这是 Python 仓库（有 pyproject/setup）",
        "pytest": "这是 Python 仓库",
        "node": "这是 Node 仓库（有 package.json）",
        "rust": "这是 Rust 仓库（有 Cargo.toml）",
        "go": "这是 Go 仓库（有 go.mod）",
    }.get(str(kind) if kind else "")


def _path_lines(
    path: EntryPath,
    *,
    project: str,
    ticket: str | None,
    readme_bit: str,
    shape: str | None,
    hint: str,
    cloned: bool,
    language: str | None,
    blurb: str | None,
) -> list[str]:
    if hint:
        install = (
            f"README 里写了 `{hint}`。你自己在本机执行；Foreshadow 不会代跑安装命令。"
        )
    elif shape:
        install = f"{shape}。按 README 自己准备环境；Foreshadow 不会执行 pip/npm/cargo。"
    else:
        install = "按 README 自己准备环境；Foreshadow 不会替你安装依赖。"
    clipped = _clip_blurb(blurb)
    about = f"（{clipped}）" if clipped else ""
    open_readme = f"打开 {project} 的 README{about}{readme_bit}"
    if cloned:
        first_read = f"对照 README{about}{readme_bit or ' 了解项目怎么跑'}"
    else:
        first_read = f"把 {project} 下到本机后，打开 README{about}{readme_bit}"
    ticket_line = (
        f"对照 {ticket}，在本机按它说的做一次，记下实际看到的现象"
        if ticket
        else "找一条开放问题，在本机按它说的做一次，记下实际看到的现象"
    )
    draft = "把你要说的话写进本机 ISSUE_DRAFT.md（还没发出去）"
    hard_note = (
        f"主语言是 {language}，不要一上来改核心实现"
        if language
        else None
    )
    if path == "REPRODUCTION":
        lines = [first_read, install, ticket_line, draft, "先把复现说明给维护者看，不要先改代码发到网上"]
        if hard_note:
            lines.append(hard_note)
        lines.append(_STOP)
        return lines
    if path == "DISCUSSION":
        return [
            first_read if cloned else open_readme,
            "用自己的话写下项目在做什么，以及一个具体问题",
            draft,
            "先观察维护者会不会回应，不要改代码",
            _STOP,
        ]
    if path == "DOCUMENTATION":
        return [
            first_read if cloned else open_readme,
            "看看入门说明缺了什么（有 CONTRIBUTING 就对照它的目录）",
            "把缺口写进 ISSUE_DRAFT.md，先问要不要补，不要直接改文档发上去",
            _STOP,
        ]
    if path == "TEST":
        return [
            first_read,
            install,
            "看仓库怎么跑测试。Foreshadow 最多探路，不会替你装依赖或跑完整测试",
            "把要补的一条测试想法写进 ISSUE_DRAFT.md",
            "本地改动只留在 foreshadow/entry 分支，不要发到网上",
            _STOP,
        ]
    if path == "TOOLING":
        return [
            first_read,
            "看有没有现成的自动化 / 工作流文件",
            "把最小改动想法写进 ISSUE_DRAFT.md，先讨论",
            _STOP,
        ]
    if path == "BUG_FIX":
        return [
            first_read,
            install,
            ticket_line,
            "最小修复只留在本机。ISSUE_DRAFT.md 和 PR_DRAFT.md 都未发送",
            _STOP,
        ]
    if path == "BENCHMARK":
        return [
            f"{project} 看起来像展示项目，但仓库里有源码，适合先测量",
            first_read if cloned else open_readme,
            install,
            "记下可重复的一组数字（耗时或效果）到 ISSUE_DRAFT.md",
            "先讨论数字，不要发优化补丁",
            _STOP,
        ]
    if path == "PERFORMANCE":
        return [
            first_read,
            "先测量，不要凭感觉改",
            "把数字写进 ISSUE_DRAFT.md，再讨论要不要动代码",
            _STOP,
        ]
    if path == "FEATURE":
        return [
            open_readme,
            ticket_line if ticket else "先对齐要不要做、做多大",
            draft,
            "实现之前等维护者，不要把新功能发到网上",
            _STOP,
        ]
    if path == "INTEGRATION":
        return [
            open_readme,
            "写清你想接什么、接口是什么，放进 ISSUE_DRAFT.md",
            "先讨论接口，再在本机实现",
            _STOP,
        ]
    if path == "RESEARCH":
        return [
            open_readme,
            "判断这是不是主要在展示、暂时不适合改代码",
            "把问题和笔记写进 ISSUE_DRAFT.md",
            "不要提交代码",
            _STOP,
        ]
    return [
        first_read if cloned else open_readme,
        ticket_line if ticket else "找一条相关开放问题，补充你本机看到的信息",
        draft,
        "等维护者回应，再决定要不要在本机改代码",
        _STOP,
    ]
