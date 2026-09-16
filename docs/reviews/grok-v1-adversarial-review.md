déjà vu: the RFC set was written to fill a “missing belief object” — this review attacks that premise (deja:01a0ab88).

The RFCs are internally careful. They keep SQLite, GET-only radar, Gate 1/2, immutable snapshots, and they correctly reject event sourcing, vector databases, and autonomous writes. That is not the problem. The problem is that they invent a second product on top of an unfinished first one, and they store interpretation as if it were a new domain.

Foreshadow already has 28 tables, 21 mission statuses, and at least six scoring vocabularies. The original product still has an in-progress 7-day soak. This branch is still moving Gate 2 code. v1 proposes six more tables and a heuristic lifecycle that will fight the hydrate budget every morning.

───

Diagnosis

1. Architecture sanity

The missing piece is not an aggregate. It is a read path.

Today a repository already has:

┌────────────────────┬───────────────────────────────────────────┐
│ Existing record    │ What a human can already ask              │
├────────────────────┼───────────────────────────────────────────┤
│ snapshots          │ What did GitHub report, by day?           │
├────────────────────┼───────────────────────────────────────────┤
│ observation_events │ What changed since yesterday?             │
├────────────────────┼───────────────────────────────────────────┤
│ scores / intel_    │ What did we conclude, as of this date?    │
│ scores             │                                           │
├────────────────────┼───────────────────────────────────────────┤
│ observations       │ Are we still collecting evidence? Until   │
│                    │ when?                                     │
├────────────────────┼───────────────────────────────────────────┤
│ reviews            │ What did the user decide?                 │
├────────────────────┼───────────────────────────────────────────┤
│ entry_analyses     │ What should they try, and when does that  │
│                    │ go stale?                                 │
├────────────────────┼───────────────────────────────────────────┤
│ entry_missions     │ What work is in flight?                   │
├────────────────────┼───────────────────────────────────────────┤
│ contribution       │ What happened on that work?               │
│ _events            │                                           │
└────────────────────┴───────────────────────────────────────────┘

RFC 001 treats the absence of a single opportunities.current_revision_id as a gap. It is not. It is the same fact spread across tables that already have dates, confidence, and NULL semantics. A Board join can answer “what do we currently believe?” A new pipeline/temporal.py will answer it again, with different words, and then those words will drift from Official v1, intel EEV, and mission status.

temporal.py plus an “opportunity repository” is a shallow module: a persistence adapter around a heuristic that will leak into Board, strategy, and refresh. Deleting it would not scatter complexity across callers. The complexity would remain where it already lives: snapshots, scores, entry analysis, missions.

Two other boundary errors:

• Opportunity owns a mission. ADR 0009 says identity is mission_id + issue, and sibling missions on one repo stay independent. linked_mission_id is the wrong cardinality.
• Repo-level “growing” is user-scoped. Potential is a property of public GitHub evidence. Stance is user-scoped. Putting both in (user_id, repo_id, target_kind, target_key) duplicates global facts per Board login and makes “growing” a personal opinion about a public repository.

There is also a paper conflict in this repo: docs/contribution-lifecycle-v1.md (2026-09-16) uses NEW → TRACKING → ENTRY_READY → COOLED|CLOSED. RFC 002 (the next day) uses open → growing → mature → cooling → expired. Same word, “lifecycle,” two ontologies. That is not a settled design.

2. Product direction

P0 asked: which 0–5 public repos are worth a look today, with honest evidence, and then stop.

Beta 0.6.1 already stretched that into observation, intel, missions, an executor, and Gate 2.

v1 asks: “what do we currently believe, why, until when, and what should a human do next?”

That is a generic intelligence-platform question. It is how you talk about an agent memory layer. It is not how a single-maintainer radar survives.

The RFCs say they will not claim future success. Then they add a lifecycle named growing / mature / cooling. P0 invariant 6 already forbade explosion theater. This is Explosion with a new noun.

The original failure mode in docs/p1-observation.md was concrete: search-only days churned so hard that 8/24 ∩ 8/31 = 0, so v7 stayed NA. Observation seats and snapshots were the fix. A belief object does not create a 7-day series. If the soak is still in progress, v1 is optimizing the wrong layer.

This is not yet a microservice platform. It is already an over-layered knowledge graph: Official v1, v2 compare, intel EEV, Board dim20, S1 earlyness/window, Access plus observed-access overlay, entry route, thesis, and now belief dimensions. That is nine ways to say “is this worth it?”

3. Data model

Schema. Six new tables on a 28-table local DB, with cyclic current_revision_id, JSON evidence bags, and no foreign keys to the facts they cite. snapshot:123 in JSON will dangle. Heterogeneous IDs were chosen to avoid link tables. That also avoids integrity.

Temporal state. open/growing/mature/cooling/expired is not specified enough to implement. “Strengthening evidence” is not a rule. The first honest implementation will be a second H-rule pile that disagrees with Official v1 and intel. Absence of a snapshot is correctly not cooling — and then you have three “don’t trust this” states: low confidence, cooling, expired. Users will not keep them straight.

Belief. intel_scores already stores dated potential, entry fit, openness, confidence, and a model version. entry_analyses already has stale_after. scores already rewrite every run. An append-only interpretation log has a versioning trap:

• Hash includes formula version → every heuristic tweak revises every tracked repo.
• Hash excludes it → old belief_json is reread by new code and silently changes meaning.

Dated score rows already handle the first case honestly. Revisions do not.

Append-only revisions. The fingerprint risk the RFC names is the production bug. JSON key order, timestamps, or a volatile “observed_at” will emit a revision per repo per day. Two years × N tracked targets is how a local SQLite file becomes archaeology.

Attempts / outcomes / lessons. contribution_attempts is unique on mission_id. That is a view of entry_missions, not an entity. contribution_outcomes and contribution_lessons re-ontologize contribution_events, which already exist and already feed observed_access. Lesson scopes that include “ecosystem/language” and “user preference” are a personalization engine with a sample size of a few dogfood PRs.

Missing. There is still no issues table. Issue-level opportunities with target_key and no issue row means “#42 was assigned” has nothing to point at except JSON. The operational need is live GET recertification of the bound issue, which Gate 2 preflight already has to do.

Ownership. Missions should point at repo + issue. Opportunities should not point at one mission. Repo potential should not be owned by users.id. Lessons should not own strategy.

Migration. Additive migrations are the right rule. The cost is not the CREATE TABLE. The cost is a second write path in foreshadow run, dual-write with entry_missions.status, and Board joins that must not break users who have radar history and zero opportunities. RFC 004 refuses to backfill, so v0.7 ships empty next to full observations / reviews tables. Empty infrastructure is not independently useful.

4. Workflow design

entry_missions already has 21 statuses. DISCOVERED and INTERESTED are declared and never used. BLOCKED has no outbound map. Gate 2 already requires WAITING_USER_APPROVAL plus a current snapshot. That machine is the product. It is already hard.

v1 adds:

• 5 opportunity lifecycles
• 6 recommended actions (observe, inspect, refresh, start a mission, wait, stop) that overlap reviews (watch, interested, investigate, enter, later, reject)
• 7 attempt statuses
• ~12 outcome kinds
• lesson polarity/status/scope

After a hundred missions a maintainer will need a glossary to answer “what is going on with this repo?” The Board already shows 观察时间线, 为什么现在, preview vs Official, and mission why. v0.8 asks it to show lifecycle without collapsing stance, panel membership, Official rank, and belief into one badge. That is a research problem, not a release.

Would this remain understandable after hundreds of missions? No. The mission table would, if you deleted dead statuses and showed one coarse bucket in the UI. The proposed overlay would not.

5. Implementation reality

One maintainer. Current work is still Gate 2 / submission. foreshadow run is already cap-and-budget constrained (120 candidates, Phase B 30, GraphQL 800, REST 400). Issue-level next_refresh_at plus “admitted, watched, active-mission, or recently changed” is a second scheduler fighting P1 observation seats.

v0.7–v1.0 is four product releases of UI, heuristics, and journals before the radar’s longitudinal KPI is proven. That is not a 6-month plan. That is how a solo OSS repo accumulates architecture and loses dogfood.

───

KEEP

SQLite, numbered migrations, repos.node_id identity

Why it should stay. Local-first, one writer, rename-safe identity. This is the only storage model the project has shown it can operate.

Long-term value. A volunteer can copy one file, run tests without a socket, and migrate with 001_…sql. That is how a 2-year OSS tool stays installable.

GET-only radar, separate approved-write port, write allowlist

Why it should stay. Radar must not grow POST by accident. Fork/push/create-PR after Gate 2 is already the only exception, and it is tested.

Long-term value. Reputation of the tool is the product. One leaked mutation ends it.

Gate 1 / Gate 2, immutable approval snapshots, human final click

Why it should stay. This is Foreshadow’s actual contribution identity, not “temporal intelligence.” ADR 0009 is the right seam.

Long-term value. Every later feature can be judged by one test: did it cross a gate without a human? If yes, it is invalid.

Official v1 isolation, explainable components, NULL ≠ 0

Why it should stay. Scores are the contract with the user. Missing windows stay NA. Temporal belief must not retune weights.

Long-term value. You can change presentation for a decade without invalidating old reports.

Observation panel ≠ user watchlist ≠ Official Top 5

Why it should stay. P1 already solved “rediscovered every day.” TTL, seat caps, and “Board reads do not write” are the correct temporal admission rules.

Long-term value. This is the refresh policy. You do not need a second one.

Snapshots, observation_events, dated scores / intel_scores, entry_analyses.stale_after

Why it should stay. These are the observation model RFC 002 describes. They already exist.

Long-term value. “What changed?” is a query. Do not rebuild it as revisions.

entry_missions as operational authority, sibling missions independent

Why it should stay. Local work has one state machine. Submission has approval_snapshots + submissions.

Long-term value. Safety-critical paths stay in tables you already test.

Reject full event sourcing, extra databases, brokers, autonomous agents, vector memory

Why it should stay. The RFCs got the non-goals right.

Long-term value. Saying no is cheaper than a migration off SQLite you will never finish.

contribution_events as the memory log

Why it should stay. S5 already records entered/setup/clone and user-marked outcomes. observed_access already consumes it without touching formula weights.

Long-term value. One append-only table can grow columns. Three new memory tables cannot be deleted once Board depends on them.

Feature-gate: if interpretation fails, radar and gates still run

Why it should stay. This is the only operational sentence in RFC 004 that matches a solo maintainer.

Long-term value. A broken heuristic must not block foreshadow run.

───

CHANGE

“Opportunity” as a durable write model

Current proposal. opportunities + opportunity_revisions, current pointer, lifecycle, next_refresh_at, optional mission link.

Problem. It duplicates observations, reviews, intel_scores, entry_analyses, and entries. v0.7 refuses backfill, so it ships empty. Fingerprint-stable revisions are a research problem. linked_mission_id violates sibling missions.

Better alternative. A read model, computed at Board/show time from existing rows:

• latest snapshots + observation_events
• latest Official score and intel row
• entry_analyses.stale_after
• latest review
• observation TTL
• open missions for that repo

Persist nothing new unless a human pins a target. If you later need a row for “I am tracking issue #42,” store it as a review or as the mission’s plan_json, which already binds issue_number.

Lifecycle open/growing/mature/cooling/expired

Current proposal. Five states with qualitative exits; Board treats them as first-class.

Problem. Unimplementable without a second ranker. Collides with P0 “do not claim it will explode.” Three overlapping “stale” states. Conflicts with contribution-lifecycle-v1.md.

Better alternative. Do not name market weather. Show three honest predicates the DB already has:

• Fresh — required evidence inside stale_after / last snapshot age
• Stale — evidence expired; refresh before Gate 1
• Dropped — observation TTL ended, user rejected, or repo not_found

If an issue closed or was assigned, that is a fact on the issue target, not a repo-wide cooling.

Belief dimensions (potential, entry-fit, timing, recommended action)

Current proposal. New belief_json independent of Official score.

Problem. intel_scores already is potential + entry_fit + confidence + as-of date + model_run_id. Timing is mostly entry_analyses freshness plus live issue GET. Recommended action duplicates reviews. A fourth JSON blob will version-churn like intel already did (intel-v1.1).

Better alternative. Display intel + Official + entry route + “analysis stale in N days.” Add at most one derived field: entry evidence age. Do not add a belief schema.

pipeline/temporal.py as a daily writer

Current proposal. Pure evaluator, persistence adapter advances pointers during foreshadow run.

Problem. Another stage on the budget-critical path. Pure-given-inputs is true of score.py too; the cost is the write policy and the hydrate expansion for due refresh. Over-creation of revisions is acknowledged and not designed out.

Better alternative. No pipeline stage. Optional foreshadow show / Board projector. If a daily job must exist, it is the existing observation hydrate, not a belief writer.

Target model repo | issue | discussion | repro | other

Current proposal. Uniqueness (user_id, repo_id, target_kind, target_key).

Problem. Speculative generality. ADR 0009’s real target is issue-bound missions. other is a hole. Discussion/repro are entry routes (strategy.py already has them), not opportunity identities. No issues table, so issue keys have no integrity.

Better alternative. Two grains only: repository, and mission_id+issue_number. Routes stay on the strategy object.

mission_transitions journal

Current proposal. Append-only (from, to, actor, event) beside entry_missions.status.

Problem. Dual-write risk, which the RFC names. transition() already exists. contribution_events already logs on many paths. A second journal will disagree.

Better alternative. In the same transaction as set_status, insert one contribution_events row with event='status_change' and detail_json containing from, to, actor. One table. Queryable after hundreds of missions.

Contribution outcomes as a new table

Current proposal. contribution_outcomes with kinds and dispositions, then lessons.

Problem. Same events already live in contribution_events (pr_merged, pr_rejected, abandoned, …). Reconciliation already maps GET-only PR state onto those events. A parallel table means two sources of “what happened.”

Better alternative. Add columns to contribution_events: source (github_read | human | system), optional disposition. Keep unknown when GET misses. Do not invent reverted until you have a dogfood revert.

Strategy adaptation via lessons

Current proposal. Filter unavailable targets, prefer proven routes, expose friction, calibrate confidence.

Problem. The first item is a live GET. The rest is a ranker. You already forbade outcome-driven ranking (trainer.py / bandit.py stay shadow). Deterministic thresholds are still ranking.

Better alternative. One function in entry.py: if the cited issue is closed, assigned, or missing, refuse to recommend it and require refresh. Surface CLA/DCO/toolchain from the existing policy scrape. Stop. No lesson table.

Four-release roadmap (v0.7–v1.0)

Current proposal. Belief tables, then Board lifecycle, then four memory tables, then unify every surface.

Problem. v0.8 is UI for an unproven model. v0.9 is a second product. v1.0 is a Board rewrite the RFC itself says is not success (“not a denser dashboard”). Four releases before soak evidence.

Better alternative. One slice: make time visible on the existing Board from existing tables. One slice: Gate 2 + issue recertify remain boring and correct. Ship those. Do not number a 1.0 intelligence narrative.

user_id on repo-level belief

Current proposal. Every opportunity is per user.

Problem. Board accounts are a local overlay. Repo evidence is global. Per-user copies of “growing” will fork on the same laptop if a second user ever logs in, and they make queries worse now.

Better alternative. Keep user_id on reviews, missions, events. Keep snapshots/intel global. Project them together.

Competing v1 documents

Current proposal. RFC 001–004 plus docs/contribution-lifecycle-v1.md.

Problem. Two lifecycles in two days. Implementers will mix enums.

Better alternative. One glossary. Archive or rewrite the 2026-09-16 note so “opportunity” is not a state machine at all.

───

REMOVE

contribution_attempts

Why unnecessary. Unique on mission_id. Every field is already on entry_missions, entries, or submissions. Deleting the table deletes no behavior.

Simpler. SELECT from the mission. If the UI wants coarse buckets (active / submitted / merged / abandoned), map the 21 statuses in the presenter. Then delete DISCOVERED and INTERESTED from the type.

contribution_lessons

Why unnecessary. You do not have enough outcomes to learn. Broad lessons (“maintainers reject AI”) are exactly what the RFC forbids, and scoped lessons still become folklore in JSON. They will leak into maintainer-facing text unless every path is audited again.

Simpler. Human note on the mission. Dismiss = ABANDONED or reviews.reject. Repeat friction = count contribution_events in the portfolio view you already have.

opportunity_revisions as append-only truth

Why unnecessary. scores, intel_scores, and entry_analyses are already dated conclusions. Revisions are a changelog of a function you will edit weekly. After a formula change, history is either incomparable or silently reinterpreted.

Simpler. Keep run-dated scores. At Gate 1, copy cited score/intel/entry-analysis ids into plan_json (the approval-style freeze you already understand). That is the only revision that matters.

pipeline/temporal.py and a refresh scheduler keyed by next_refresh_at

Why unnecessary. Observation membership plus stale_after plus Gate 2 live preflight already decide what to hydrate and what to recertify. A due-refresh index will expand GET load onto issue targets and blow the 400/800 budgets the radar was designed around.

Simpler. Keep P1 caps. Recertify the bound issue at Gate 1 start and again at Gate 2. Everything else can be stale in the UI.

Validity-interval policy engine (valid_from / valid_until by evidence class)

Why unnecessary. Four TTL policies (issue, repo trend, historical outcome, failed refresh) are a rules engine. entry_analyses already uses 3 days. Observations already use 14 days from added_on.

Simpler. Show those two deadlines. Add none.

Recommended-action vocabulary

Why unnecessary. Six new verbs next to six review actions next to 21 mission statuses.

Simpler. Reviews remain the human stance. Missions remain the work. UI copy can say “entry analysis is stale” without an enum.

target_kind values discussion, repro, other

Why unnecessary. Those are strategies, not identities. other cannot be validated.

Simpler. recommend_entry() already returns DISCUSSION / REPRODUCTION. Leave them there.

v0.8 lifecycle Board and v1.0 “coherent narrative” unification

Why unnecessary. The Board already has timelines and 为什么现在. Unifying radar, observation, opportunity, mission, approval, and outcome into one story is a redesign of webapp.py, not a schema.

Simpler. Add stale/fresh labels to the card you have. Do not add a lifecycle filter.

Operator integrity checker for belief pointers

Why unnecessary. You cannot have dangling current_revision_id if you do not have that pointer. This is scaffolding for a model that should not ship.

Simpler. Foreign keys on the tables you keep. PRAGMA foreign_keys=ON is already there.

Feeding outcomes back into opportunity belief (change_reason='outcome_update')

Why unnecessary. This is the learning loop that retunes advice while claiming not to. A merged PR does not make the next issue good. A closed PR should not cool the repository. The RFC states both, then wires C → B anyway.

Simpler. Outcomes stay on the mission. They do not write radar state.

“Temporal contribution intelligence” as the v1 product name

Why unnecessary. It does not tell a user what to do on Monday. It invites the next RFC to add embeddings.

Simpler. Keep the identity you have: local OSS radar, human-gated contribution, honest evidence over time.

───

FINAL VERDICT

1. Is Foreshadow v1 directionally correct?

The need is correct: a repo must persist across days, evidence must age in public, and a closed issue must not be recommended as if it were live.

The architecture is not. v1 is specified as a new interpretation substrate — belief, lifecycle, attempts, lessons — instead of a thinner projection of tables that already encode time. That is how a radar becomes an AI-memory demo without ever shipping a vector database.

Directionally keep the product. Do not build this shape.

2. What is the biggest architectural risk?

A second, heuristic state machine (opportunity lifecycle + revision fingerprint + outcome feedback) that diverges from Official scores, intel, observation TTL, and mission status, while next_refresh_at competes with the hydrate budget that makes v7 real.

Once Board reads current_revision_id, you cannot delete it. You will spend the next two years explaining why “cooling” is not “expired” is not “stale entry analysis” is not “Official missed Top 5.”

3. What should NOT be built in the next 6 months?

• opportunities, opportunity_revisions, contribution_attempts, contribution_outcomes, contribution_lessons, mission_transitions
• pipeline/temporal.py
• lifecycle badges and filters
• lesson-driven route ranking
• issue/discussion/repro opportunity identities
• v1.0 unified dashboard
• any write on Board GET
• any outcome → radar feedback

Also do not start this while Gate 2 / submission on the current branch is still moving. Safety core first.

4. What are the first 3 implementation priorities?

1. Freeze the contribution path you have. Collapse unused mission statuses. Keep Gate 1/2 and snapshot immutability as the only write story. Recertify the bound issue with GET at Gate 1 and Gate 2. That is temporal intelligence at the only moment it can hurt you.

2. Project existing time on the Board, read-only. Snapshot span, last observation_events, intel as-of date, entry_analyses.stale_after, observation expires_on, latest review. No new tables. If this does not change a user’s Monday, neither will six journals.

3. Make contribution_events the audit log. Record from/to on status change in the same transaction. Add source. One rule: dead or assigned targets cannot be recommended. Leave trainer.py / bandit.py shadow-only until you have dozens of real outcomes, which you do not.

The 2-year version of Foreshadow is a boring local SQLite app that still finds a few honest targets, still refuses to lie about missing history, and still will not push until a human clicks. Everything in these RFCs that does not serve that should wait until the soak and a handful of merged missions say you are forgetting something a query cannot answer. You are not there yet.