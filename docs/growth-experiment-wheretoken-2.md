# whereToken growth experiment 2

Recorded 2026-10-05. This replaces `docs/growth-experiment-wheretoken-1.md`, which is `SUPERSEDED_BEFORE_TREATMENT`. The homepage field was not written.

`gx-qualified-traffic-v1` in `build_plan` is unchanged. The planner stays channel-agnostic. This page is not a planner output and it is not `TREATMENT_APPLIED`.

## Identity

| Field | Value |
|---|---|
| id | `wt-description` |
| target | `rainhuang0220/whereToken` |
| surface | GitHub repository description, one field |
| public main | `6948f7522a0a98d4f7d2619583e1b717b9363162` |
| release | `v0.7.7` |
| classification | `SAFE_NONFUNCTIONAL` |
| functional_change | false |
| treatment_applied | false |
| owner approval required | false |
| lifecycle | `PRE_BASELINE_STABILIZATION` |
| measurement state | `INSUFFICIENT_BASELINE` |

The description write itself does not need owner approval. It is still forbidden until the stabilization cutoff is public and a stored baseline exists.

## Before and after

Before, unauthenticated repository metadata on 2026-10-04, and unchanged by this round:

`你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`

Proposed after, not written:

`Local-first token usage analytics for coding agents · 你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`

94 Unicode code points. The English clause is the README hero without its period. The Chinese clause is the current description, kept whole so the query `coding agent` still matches. No agent names. No extra keywords.

A shorter line that dropped `本机优先的 coding agent 用量观测器` was considered and not chosen. That drop would remove a query the current text already matches.

## Funnel stage

Discovery, before the repository click. The description is part of the default repository search document and the card text. The homepage field is not.

## Primary metric

`daily_unique_visitors`, grain `day`.

The search result or repository card can show the sentence. A click then loads the repository page. GitHub counts that load. The impression itself is not the metric. The arrival is. That order is why this metric is downstream of a description change and is not downstream of the homepage field.

Estimand, if a later window is actually collected: median of stored post days minus median of stored baseline days.

- `NO_CLEAR_CHANGE` if the medians are equal, including a flat zero series.
- `OBSERVED_CHANGE` if the medians differ. This is not a causal claim.
- `UNKNOWN`, and the measurement state stays `INSUFFICIENT_BASELINE`, if either window has fewer than 7 stored days, if a missing day was filled, or if a frozen confounder moved.

`low_power` stays true. `causal` stays false. Stars are not the primary metric. A changed description plus a changed count is not evidence that the field caused the count.

## Secondary metrics

Reported only. They do not rescue a null or declare a win.

- `daily_views`
- `daily_clones`, `daily_unique_cloners`
- `rolling_14d_views`, `rolling_14d_unique_visitors`, `rolling_14d_clones`, `rolling_14d_unique_cloners`
- `window_count:<referrer>`, `window_uniques:<referrer>`, `window_count:<path>`, `window_uniques:<path>`
- stars

Rolling 14-day windows overlap the cut, so they are not the effect. Daily uniques are not summed into a window unique.

## Metric justification

The treatment is readable before the click that creates the observation. Homepage, README body, and GitHub Pages views do not have that order. GitHub traffic does not count Pages views. A README link is visible only after arrival, and a README commit moves `pushed_at`.

## Counterevidence

- Ranking is opaque. A search match is not a rank and not a click.
- Anyone who already has the URL never needs the new sentence.
- Recommendation surfaces that ignore the description are unaffected.
- The current Chinese sentence already matches `coding agent`. The confirmed miss is `local-first`. Query volume for that token is unknown.
- Stars 3, forks 0, subscribers 0. If the baseline days are zeros, the median moves only when at least half of the post days are positive. Seven to fourteen days is a collection policy, not a power calculation.
- An `OBSERVED_CHANGE` still has other explanations: a release, a post, a topic edit, a README commit, or ordinary noise.

## Candidates not selected

| id | why not |
|---|---|
| `wt-homepage` | Superseded. The counted view happens before the link is visible. |
| `wt-topic-usage-analytics` | One real shelf, used by the sampled small meters, about 150 repositories. Rank of a 3-star repo on that page is unknown. The pill does not state the job and does not fix the `local-first` miss. A second topic would destroy attribution. |
| `wt-readme-demo-cta` | Visible only after arrival. No trustworthy GitHub metric for "saw the demo" or "tried it". Paths are a 14-day top-10 with no per-entry day. Clones are not installs. A commit moves `pushed_at`. No telemetry will be added. |

## Baseline status

No owner-traffic row is stored. `FORESHADOW_OWNER_TRAFFIC_TOKEN` was unset on 2026-10-05. `growth observe` was not run. The traffic API was not called.

| Field | Value |
|---|---|
| baseline dates | none |
| baseline observations | empty |
| treatment timestamp | null |
| intervention_on | null |

## Stabilization

Lifecycle is `PRE_BASELINE_STABILIZATION`. The baseline does not start on the current public main.

| Field | Value |
|---|---|
| stabilization_sha | null |
| stabilization_timestamp | null |
| hygiene branch | `engineering/pre-baseline-hygiene` |
| hygiene tip | `b6b741de6500049d115d7c321f6db16d9fcaa2e8` |
| hygiene parent | `52dc06cc3dcbf2ba6300ca0760dd239a162f6c0f` |
| public main | `6948f7522a0a98d4f7d2619583e1b717b9363162` |

The hygiene commits change only `site/index.html`. They narrow privacy sentences that were broader than Cursor and Trae account calls, hosted sync, and profile refresh. They do not change command flags or runtime code. Pages deploys from `main` only, so the live site is still the old copy.

Pushing that branch updated the repository `pushed_at` to `2026-10-04T17:05:48Z`. Public `main` did not move. Homepage, description, and topics were unchanged at `Date: Sun, 04 Oct 2026 17:07:04 GMT`. The push is a pre-baseline event, not the description treatment. Baseline collection still waits for `stabilization_sha`.

`stabilization_sha` is the public `main` commit after that hygiene is what `main` contains, recorded at the time Pages has deployed it. It is not `b6b741d` unless a fast-forward makes that commit `main`. A merge commit would be a different sha. Do not fill this field in advance.

`Formula/wheretoken.rb` staying on `v0.7.6` is a frozen confounder, not a hygiene gate. The approval packet is `docs/growth-approval-wheretoken-formula-v077.md`. It was not applied.

## Frozen confounders

Once the cutoff exists, any of these moves between the first baseline day and the last post day makes the label `UNKNOWN`.

- Homepage stays `null`.
- Topics stay `cli`, `developer-tools`, `go`, `golang`, `tokens`.
- README blob stays the blob at the cutoff.
- Pages content stays the cutoff deploy, including the hygiene copy once it is the deploy.
- In-repo formula stays on the `v0.7.6` source tarball.
- No new tag, release, or announcement. Latest release stays `v0.7.7`.
- No social post, promotional Discussion, or star solicitation.
- The description, once set, stays the one proposed sentence.
- No telemetry is added to whereToken or Pages.

## What would make a later result invalid

A missing day stored as zero. A rolling 14-day total used as the effect. Stars used as the primary success. A second public string changed in the same window. Baseline days collected before `stabilization_sha` is set. A traffic token reused from `gh` or `GITHUB_TOKEN`.
