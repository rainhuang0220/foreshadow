# Opportunity Engine v2 — S1 Earlyness × Evidence × Opportunity Window

**Official remains v1.** This is Preview only. No star band, no star veto, no star bonus. Activity ≠ star growth. No fake snapshots.

Replay: in-memory rescore of the 2026-08-25 PR-H 120 (`daily_runs.id=2`). Stored v2 ranks = **S1 before** (Activity fill only). New `score_repo_v2` = **S1 after**.

---

## Formula (v2)

Stars enter Evidence as **4 points max** (`clip01(log10(S+1)/4)`), never renormalized to 100, never an Earlyness band.

### Earlyness (how far from crowded / hard to enter)

Points, missing terms dropped (not filled 0):

| Term | pts | Unit |
|---|---:|---|
| Youth | 30 | 1 at ≤45d, 0 by ~2y |
| Uncrowded | 30 | `clip01((30−C)/30)` — **C, not S** |
| Access | 20 | PR accept / unassigned help / maint_touch |
| Living | 20 | Activity Momentum if known; else a **weak** push recency (today-only push is 0.35, not 1.0) |

### Evidence (why this is not a toy)

| Term | pts |
|---|---:|
| C | 18 |
| issues | 16 |
| Activity Momentum | 18 |
| releases_30d | 12 |
| recent contributor diversity | 12 |
| maint_touch | 12 |
| pr_accept_rate | 8 |
| **stars (weak)** | **4** |

UNKNOWN ≠ low quality: omitted keys add 0 **weight**, they do not smear a “bad project” label.

### Opportunity Window

```text
if both known:  75 × √(earlyness × evidence) + 25 × access
```

Gold requires **both** high earlyness and high evidence. Not `earlyness + evidence`. Not a star interval.

Experimental pool (does not compete at the top of v2 `pool_rank`):

- not validated (evidence < 24)
- **and** (age ≤21 with thin AM **or** evidence <18 with C≤2 and age≤90)

Window capped at 32 (experimental) / 22 (STAGNANT).

Stage is derived from earlyness, evidence, AM, age, C — not from a star table.

---

## Counterexamples (tests)

All required names in `tests/test_s1_opportunity.py`. `uv run pytest` → **287 passed**.

| Fixture | Result |
|---|---|
| 2★ 2d 1 commit | EXPERIMENTAL pool, evidence &lt; 20, loses to small_active |
| 3★ 14d 20 commits / 2 releases / 4C / issues / maintainer / PR accept | **main** pool, VALIDATED_EARLY or BREAKOUT |
| 300★ 60d rapid 8C | window **&gt;** 2800★ 1400d C=190 mature |
| 5000★ 120d 12C AM high PR accept | main, earlyness ≥50, not vetoed |
| 73★ 800d silent | STAGNANT, window ≤22 |
| 3★ vs 50★ same everything else | |Δ Opportunity| &lt; 8, same pool |

---

## 2026-08-25 replay

### Coverage of new labels

| | n |
|---|---:|
| BREAKOUT (gold) | 22 |
| VALIDATED_EARLY | 18 |
| EMERGING | 50 |
| EXPERIMENTAL (stage) | 24 |
| experimental **pool** | **15** (v2 ranks **#106–#120**) |
| SCALING | 3 |
| ESTABLISHED | 2 |
| STAGNANT | 1 |
| Quadrant gold | 22 |

### Analysis bands (not scoring rules)

| stars | n | experimental pool |
|---|---:|---:|
| 1–9 | 28 | **10** |
| 10–99 | 27 | 2 |
| 100–299 | 20 | 1 |
| 300–999 | 24 | 0 |
| 1000–2999 | 21 | 2 |
| 3000+ | 0 | 0 |

1–9★ is **not** a reject band: 18 of 28 stay in the main pool when evidence exists (`tracefold` 2★, `ohmyharness` 3★).

### v2 Top 10 after S1

| new | old | repo | ★ | stage | Earlyness | Evidence | Window |
|---:|---:|---|---:|---|---:|---:|---:|
| 1 | 1 | Gitlawb/zero | 1626 | BREAKOUT | 59 | 91 | 70 |
| 2 | 3 | caura-ai/caura | 449 | BREAKOUT | 75 | 79 | 73 |
| 3 | 4 | curie-eng/curie | 33 | BREAKOUT | 87 | 71 | 75 |
| 4 | 6 | NVIDIA-NeMo/Gym | 1139 | EMERGING | 49 | 80 | 64 |
| 5 | 5 | mudler/vllm.cpp | 350 | BREAKOUT | 67 | 82 | 60 |
| 6 | 2 | trusty-tools | 18 | BREAKOUT | 75 | 53 | 52 |
| 7 | 14 | isnad | 36 | BREAKOUT | 83 | 55 | 61 |
| 8 | 7 | Ghostex | 706 | BREAKOUT | 65 | 72 | 57 |
| 9 | 13 | docx-editor | 253 | BREAKOUT | 80 | 69 | 66 |
| 10 | 36 | remnic | 181 | BREAKOUT | 62 | 77 | 62 |

### Named before → after

| repo | ★ | stage | pool | v2 old → new |
|---|---:|---|---|---|
| Gitlawb/zero | 1626 | BREAKOUT gold | main | #1 → **#1** |
| curie-eng/curie | 33 | BREAKOUT gold | main | #4 → **#3** |
| trusty-tools | 18 | BREAKOUT gold | main | #2 → #6 |
| TraceFold/tracefold | 2 | VALIDATED_EARLY | main | #9 → #12 |
| Mechanica-Labs/goliath | 1 | EXPERIMENTAL | **experimental** | #84 → **#113** |
| Lyzr-Cognis/cognis | 54 | (low evidence) | main | #10 → **#41** |
| MrGiovanni/PanTS | 123 | STAGNANT | main | #32 → **#56** |

`cc-switch-headless` is not in this 120.

### 300★ vs 3000★

This corpus has no 3000★. Closest:

- `vllm.cpp` **350★ BREAKOUT** window 60, v2 **#5**
- `a2aproject/a2a-python` **2103★ ESTABLISHED** window 26, v2 #57
- Unhydrated 1k+ (boxlite 2275★) evidence **3.4**, window **7**, not gold

The model prefers the 350★ hydrated breakout over the 2k★ established/unknown rows **because of evidence and access**, not because 350 is a magic band.

### 5000★ young breakout

No 5000★ in the 120. Fixture `eco/wave` (5000★, 120d, 12C, AM high, PR accept) stays **main / BREAKOUT / earlyness ≥50**. `Gitlawb/zero` 1626★ is the live analogue: still **#1**, not punished for scale.

---

## Five acceptance answers

### 1. Why a 2★, 2-day, 1-push repo does not Top-5

Evidence is ~0–6 (1 commit, 1 author, no issues). Stage **EXPERIMENTAL**, separate pool, window cap 32. `goliath` 1★: v2 **#113**. Last-push-today is **not** `fresh=1.0` in the window.

### 2. Why a 250★ fast, used, responsive, enterable repo can be a top candidate

`eigenpal/docx-editor` 253★: Earlyness 80, Evidence 69, Window 66, **BREAKOUT gold**, v2 **#9**. Product of earlyness×evidence, plus access.

### 3. Why 300★ breakout can beat 3000★ mature

`vllm.cpp` 350★ window 60 vs `a2a-python` 2103★ ESTABLISHED window 26. Crowding is **C**, not an S>1000 veto. Mature success can be real and still a **narrower opportunity window**.

### 4. Why 5000★ young new-ecosystem can stay high

Stars only add ≤4 evidence points. Earlyness uses age + C + access + AM. Fixture 5000★/120d/12C is BREAKOUT. Live `zero` 1626★ remains #1.

### 5. Why 50★ two-year stagnant is not “early”

`small_stagnant` fixture: STAGNANT, window ≤22. Live `PanTS` (1 commit / 30d): STAGNANT, #32→#56. Low stars do not mint Earlyness once age and activity say otherwise.

Board drawer: **阶段 / 早期程度 / 证据强度 / 机会窗口** plus plus/minus bullets and “Star 只是规模观察，不是区间门槛，也不是否决。”

---

## Official

`score.py` / `select.py` / 55 / 35 / v7 / Official Top 5: **unchanged (still 0)**. Dual-write continues. `score_compare` still v1 vs v2 ranks.

---

## Known leftovers

- Lightweight rows often have C/AM UNKNOWN → evidence is almost only the 4-point star term; window stays low. That is data, not a star magnet.
- Stage `EMERGING` is the leftover bucket for unvalidated but not experimental-pool rows.
- No 5000★ / 3000★ in this 120; those cases are pinned by fixtures.
- Next: S2 maintainer depth, or more hydrate so Evidence is known on the experimental 15. Not another star rule.
