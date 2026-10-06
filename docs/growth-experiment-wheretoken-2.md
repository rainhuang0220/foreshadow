# whereToken growth experiment 2

Recorded 2026-10-05. This replaces `docs/growth-experiment-wheretoken-1.md`, which is `SUPERSEDED_BEFORE_TREATMENT`. The homepage field was not written.

`gx-qualified-traffic-v1` in `build_plan` is unchanged. The planner stays channel-agnostic. This page is not a planner output and it is not `TREATMENT_APPLIED`.

## Identity

| Field | Value |
|---|---|
| id | `wt-description` |
| target | `rainhuang0220/whereToken` |
| surface | GitHub repository description, one field |
| public main | `cd3213d9d831207766295ed7515c7d8103a455d2` |
| release | `v0.7.7` |
| classification | `SAFE_NONFUNCTIONAL` |
| functional_change | false |
| treatment_applied | false |
| owner approval required | false |
| lifecycle | `READY_FOR_BASELINE` |
| measurement state | `INSUFFICIENT_BASELINE` |

The description write itself does not need owner approval. The stabilization cutoff is now public. The write stays forbidden until at least 7 eligible post-cutoff days are stored. No baseline row exists. This is not `TREATMENT_APPLIED` and not `BASELINE_COLLECTING`.

## Before and after

Before, unauthenticated repository metadata on 2026-10-04, rechecked at `Date: Tue, 06 Oct 2026 20:07:04 GMT`, and still not written:

`你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`

Homepage was `null`. Topics were `cli`, `developer-tools`, `go`, `golang`, `tokens`.

Previous proposed after, recorded 2026-10-05 and not written:

`Local-first token usage analytics for coding agents · 你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`

94 Unicode code points, 129 UTF-8 bytes. That line repeats the same job. `Local-first` and `本机优先` say the same placement. `token usage analytics` and `用量观测器` say the same job. `coding agents` and `coding agent` are the same term.

Final proposed after, refined 2026-10-06 before any baseline row and before any treatment, and not written:

`Local-first token usage analytics for coding agents · 你的 token 都花在哪`

67 Unicode code points, 80 UTF-8 bytes. One description field. The English clause still contains `coding agents`, `token usage`, `analytics`, and `Local-first`. The Chinese clause keeps the existing brand line. GitHub's description limit is 350 characters. No agent names. No second field.

The shorter line drops the exact phrases `本机优先`, `用量观测器`, and the Latin tokens inside the old Chinese clause. It does not drop the term from the field: `coding agents` remains in the English clause. This record does not claim that GitHub stems `agents` to `agent`. The long line was keyword restatement, not an extra fact. Neither sentence claims that a report never touches the network.

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

No owner-traffic row is stored. `FORESHADOW_OWNER_TRAFFIC_TOKEN` was unset on 2026-10-05 and was still unset at the 2026-10-06 stabilization check. `GITHUB_TOKEN` was also unset. `growth observe` was not run. `gh` was not used as a traffic credential. The traffic API was not called.

| Field | Value |
|---|---|
| baseline dates | none |
| baseline observations | empty |
| treatment timestamp | null |
| intervention_on | null |

## Stabilization

Lifecycle is `READY_FOR_BASELINE`. Public main contains the hygiene, and the live Pages HTML matches that commit. No post-cutoff observation is stored, so the lifecycle is not `BASELINE_COLLECTING`.

| Field | Value |
|---|---|
| stabilization_sha | `cd3213d9d831207766295ed7515c7d8103a455d2` |
| integration timestamp | `2026-10-06T20:00:15Z` |
| stabilization_timestamp | `2026-10-06T20:07:01Z` |
| pages_verified_at | `2026-10-06T20:07:01Z` |
| pages last-modified | `2026-10-06T20:04:07Z` |
| pages content sha256 | `b23ecc8283542499c73644c8c50e8e31f6c5c41e64e2272a9af56a89118e92f6` |
| pages workflow | `37523137243`, success, updated `2026-10-06T20:04:14Z` |
| hygiene branch | `engineering/pre-baseline-hygiene` |
| hygiene tip | `e1ca6caaa2b139dfd9192180c291a640b8e84224` |
| earlier hygiene commit | `b6b741de6500049d115d7c321f6db16d9fcaa2e8` |
| hygiene parent | `52dc06cc3dcbf2ba6300ca0760dd239a162f6c0f` |
| previous public main | `6948f7522a0a98d4f7d2619583e1b717b9363162` |

`6948f752` through `e1ca6ca`, which `origin/main` contains via merge commit `cd3213d`, changes only `site/index.html`. The commits correct static claims about the default report, Cursor and Trae account APIs, commands that print local paths, the Community Rank payload, hosted sync, public-profile refresh, and the Trae account-API label. A later static edit on the same file narrowed two sentences to the upload paths the CLI uses: a plain report does not upload the public snapshot, and a paired hosted sync uploads the sanitized public profile on `sync`, `scan`, a running `serve`, and `login` unless `--no-sync`. No `cmd/`, `internal/`, `scripts/`, or `Formula/` file changed.

Pull request `#12` merged at `2026-10-06T20:00:15Z`. That timestamp is the integration time. It is not the Pages verification time. The live page `https://rainhuang0220.github.io/whereToken/` returned HTTP 200 at `Date: Tue, 06 Oct 2026 20:07:01 GMT`, 12518 bytes, and the sha256 above. That hash is `git show cd3213d:site/index.html`. The body contains the corrected sentences and does not contain "Nothing uploads unless you opt in", "Everything stays on your machine", or "nothing crosses the network".

Pushing the hygiene branch earlier updated `pushed_at` to `2026-10-04T17:05:48Z` while public main stayed `6948f752`. That push is a pre-baseline event. The merge moved `pushed_at` to `2026-10-06T20:00:15Z`. Homepage, description, and topics were unchanged at the 2026-10-06 recheck. Neither push is the description treatment.

`Formula/wheretoken.rb` on `cd3213d` is still the v0.7.6 tarball `384780534bf6051ca546519ac74182d6f6bfb6331677c04299030a18399417bf`. The owner has not approved the v0.7.7 packet. That pin stays a frozen confounder for the whole experiment. The packet is `docs/growth-approval-wheretoken-formula-v077.md`. It was not applied. Classification remains `APPROVAL_REQUIRED_FUNCTIONAL`.

GitHub Actions on `cd3213d` passed `go vet` and `go test` on Ubuntu, Windows, and macOS (`37523137237`, success at `2026-10-06T20:07:04Z`, and the pull-request run `37523123178`). The Pages workflow passed separately.

## Baseline eligibility

Stored historical traffic and the formal baseline are different. A later `growth observe` may return daily rows dated before stabilization. Store those rows as GitHub returned them. Do not fill dates GitHub omitted. An explicit zero stays zero. A missing key stays unstored.

A stored row counts toward the formal baseline only when its `observed_on` calendar date is strictly after `2026-10-06`. That UTC date is ineligible: the merge and the Pages deploy both happened on it, so the day is partial. The first eligible day is `2026-10-07`. Do not move this cutoff earlier to lengthen the window.

The formal baseline still needs at least 7 eligible stored calendar days. Ten to fourteen is preferred. That length is a collection policy, not a significance test. `BASELINE_COLLECTING` starts only after stabilization and at least one eligible observation are both stored. Until the owner-traffic token exists, the lifecycle stays `READY_FOR_BASELINE`.

## Frozen confounders

Once the cutoff exists, any of these moves between the first baseline day and the last post day makes the label `UNKNOWN`.

- Homepage stays `null`.
- Topics stay `cli`, `developer-tools`, `go`, `golang`, `tokens`.
- README blob stays the blob at the cutoff.
- Pages content stays the cutoff deploy, sha256 `b23ecc8283542499c73644c8c50e8e31f6c5c41e64e2272a9af56a89118e92f6`.
- In-repo formula stays on the `v0.7.6` source tarball.
- No new tag, release, or announcement. Latest release stays `v0.7.7`.
- No social post, promotional Discussion, or star solicitation.
- The description, once set, stays the final proposed sentence: `Local-first token usage analytics for coding agents · 你的 token 都花在哪`.
- No telemetry is added to whereToken or Pages.

## What would make a later result invalid

A missing day stored as zero. A rolling 14-day total used as the effect. Stars used as the primary success. A second public string changed in the same window. A pre-cutoff day, including `2026-10-06`, counted as a baseline day. A traffic token reused from `gh` or `GITHUB_TOKEN`. An emergency product fix during the window that is still labeled as a clean baseline: mark that window `UNKNOWN` and restart stabilization. Product correctness outranks a clean window.
