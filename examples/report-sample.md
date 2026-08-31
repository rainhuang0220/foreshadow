# Foreshadow — 2026-08-24

Snapshot history: 31 days (v7 and v30 defined for tracked repos)
Explosion is a rule on relative growth, not a forecast that a project will “make it.”

Run: **complete**
Candidates: 3 → scored 3 → **Top 5: 1**
Budget: 0 / 800 GraphQL points, 0 REST

## Top 1

━━━━━━━━━━━━━━━━━━

### #1 `acme/memkit`

Opportunity: **85**/100  (confidence: high)
Explosion: **94**/100  (confidence: high)  — potential, not a promise
Contribution: **62**/100  (confidence: high)

Why now:
700 net stars in 7 days on a 200-star base; 22 unique external issue authors; 8 contributors; 10× would crowd identity (`C→80`).

Five-point analysis:
① Acceleration: rel_growth_7d=3.5, accel_ratio=4.166666666666667, size_discount s=0.32. is_accelerating=yes.
② Real users: U_issue_ext=22, bug_n=12, talk_n=20, fork_star=0.09444444444444444, install=1. Stars are not users; this is issue evidence.
③ Contributor gap: star_per_contrib=112.5, demand_ratio=5.6, C=8, starved=True.
④ Contribution opportunity: surface=0.66, gaps=0.33, receptive=0.67, skill=0.92.
⑤ One-year entry: late_now=false, late_10x=true, S=900, C=8.

Direction Fit: 92%  (memory / rag / llm)
Exceptional: no

Best contribution:
1. #12 document eviction — docs, medium impact
2. #18 window overflow — tests
3. 先复现问题，再记录给维护者

Risk:
Maintainer concentration (8 contributors); growth could be a single viral post; H-rules passed.

Evidence: node_id=`R_kgDOEXAMPLE`; snapshots t/t-7/t-30; SPDX=MIT; captured_at=2026-08-24T00:05:00+00:00

```
foreshadow review acme/memkit interested
foreshadow review acme/memkit enter -m "memory evals"
```

━━━━━━━━━━━━━━━━━━

## Below bar (max 3)
- `giant/infra` Opportunity 24 < 55
- `quick/chatgpt-wrapper-pro` **veto H5,H6,H7**

## Source health
- graphql search: ok
- hydrate: 0 failed
- missing windows: 0/3 repos have v7=NA
