# whereToken growth experiment 1

Recorded 2026-10-04. State `INSUFFICIENT_BASELINE`. Nothing in this file was applied to `rainhuang0220/whereToken`.

`gx-qualified-traffic-v1` in `build_plan` is unchanged. It still names no channel, still has `intervention_on` null, and still stays `INSUFFICIENT_BASELINE` because no traffic row is stored. This page is the pre-registration for the first dogfood. It is not a planner output and it is not `TREATMENT_APPLIED`.

## Identity

| Field | Value |
|---|---|
| target | `rainhuang0220/whereToken` |
| public main | `6948f7522a0a98d4f7d2619583e1b717b9363162` |
| release | `v0.7.7`, published 2026-09-27T05:52:36Z |
| foreshadow | `engineering/growth-intelligence` at `af41f617afc8437f6964a219c09f47fa2b6390a4` when this review started |
| whereToken worktree | `engineering/growth-experiment-1` at that same public main, upstream unset, no commits |
| classification | `SAFE_NONFUNCTIONAL` |
| functional_change | false |
| owner approval required | false |
| state | `INSUFFICIENT_BASELINE` |

Owner approval is not required for the homepage write itself. The write is still forbidden until a stored baseline exists.

## Baseline

`BASELINE BLOCKED — OWNER TOKEN REQUIRED`

`FORESHADOW_OWNER_TRAFFIC_TOKEN` was unset on 2026-10-04. `GITHUB_TOKEN` was unset. `growth observe` was not run. The traffic API was not called. The logged-in `gh` credential was not used as a substitute.

The local Foreshadow database at `~/Library/Application Support/foreshadow/foreshadow.sqlite3` is schema versions 1 through 10. It has no `owner_traffic_observations` table. `~/.local/share/foreshadow/foreshadow.sqlite3` does not exist. An earlier unsaved read is not a baseline. Release-asset download counts are not a baseline.

| Field | Value |
|---|---|
| baseline dates | none |
| baseline observations | empty |
| treatment timestamp | null |
| intervention_on | null |
| post window | null |

The database is able to store the series once schema 12 is migrated by a real `growth observe` from the `af41f61` implementation and the owner token is present: `daily_views`, `daily_unique_visitors`, `daily_clones`, `daily_unique_cloners`, `rolling_14d_views`, `rolling_14d_unique_visitors`, `rolling_14d_clones`, `rolling_14d_unique_cloners`, and `window_count:<label>` / `window_uniques:<label>` for referrers and paths. That ability is the schema. It is not a stored row.

Days GitHub omits stay missing. They are not stored as zero. A zero GitHub returns stays zero. Daily uniques are not summed into a window unique. Rolling 14-day windows overlap, so `rolling_14d_unique_visitors` is not the effect.

## Selected treatment

One field. GitHub repository homepage, from JSON `null` to exactly:

`https://rainhuang0220.github.io/whereToken/`

No README line. No description edit. No topic edit. No second host. No release. No formula edit. No profile-card move. No Pages content change.

Recorded previous state, unauthenticated `GET /repos/rainhuang0220/whereToken`, response `Date: Sun, 04 Oct 2026 15:34:08 GMT`:

| Field | Before |
|---|---|
| homepage | `null` |
| description | `你的 token 都花在哪 — 本机优先的 coding agent 用量观测器` |
| topics | `cli`, `developer-tools`, `go`, `golang`, `tokens` |
| has_pages | true |
| stars | 3 |
| forks | 0 |
| subscribers | 0 |
| pushed_at | 2026-10-01T05:25:30Z |

The live page was HTTP 200 on 2026-10-04 and byte-identical to `site/index.html` at public main (11282 bytes, SHA-256 `1aab7a43f4e4e960c44a812d0b124304c211e49b2140ba8ef78c44b756a4b69e`). Canonical and `og:url` are that Pages URL. `/demo/` was HTTP 200 and serves fabricated sample JSON. The field must not be pointed at `https://wheretoken.plainlist.space`. That host is the signed-in app.

Reversibility: `PATCH` `homepage` back to null. The field is not in git.

## Hypothesis

People who see the About website slot, and would not have opened the README, produce more later visits to the repository, so stored `daily_unique_visitors` rises after the field flips.

This is a return-visit question. It is not a claim about why the repository has 3 stars.

## Counterevidence

- The link points away from the repository. GitHub counts a repository view when the page loads, which is before the About link can be clicked. The field cannot cause the view that reveals it, except by a repeat visit, an external index, or a return click from Pages.
- Repository search, without `in:`, uses name, description, and topics. It does not use the homepage field. Filling the field creates no search impressions.
- The README already links this URL under Live Demo. Pages already links back to the repository. The new exposure is the About slot and API consumers.
- The landing page's primary button is "Open Web App" to `https://wheretoken.plainlist.space`, then Demo, then Download CLI. The homepage field does not isolate the synthetic demo.
- Referrer and path rows are top-10 snapshots for the fetch date. They have no per-entry day. Presence of the Pages host does not prove the homepage field caused it.
- Stars 3, forks 0, subscribers 0. Low traffic means low power. Seven to fourteen days is a product policy so both series exist. It is not a power calculation and not a significance claim. `low_power` stays true. `causal` stays false.
- The binding acquisition constraint from the source review is distribution: a 50-day repository, discussions off, generic topics, and no third-party page in the searches that were run. An empty website field is invisible to someone who never opens the repository. Posting, mailing, or soliciting is `HUMAN_DISTRIBUTION_ACTION` and was not done.
- Among twelve small local usage CLIs, a homepage was set on four. One of those four has 0 stars. That co-occurrence is not an effect.

A flat series is an acceptable result.

## Metrics

Primary: `daily_unique_visitors`, grain `day`, one integer per stored calendar day.

Estimand, pre-registered: median of stored post days minus median of stored baseline days.

- `NO_CLEAR_CHANGE` if the medians are equal, including a flat zero series.
- `OBSERVED_CHANGE` if the medians differ. Still not causal, still low power, and not a success claim.
- `UNKNOWN`, and the state stays `INSUFFICIENT_BASELINE`, if either window has fewer than 7 stored days, if a missing day was filled, or if a frozen confounder moved.

The shipped last-day comparison is a different summary. It is not this decision rule.

Secondary, reported only. They do not rescue a null or declare a win.

- `daily_views`
- `daily_clones`, `daily_unique_cloners`
- `rolling_14d_views`, `rolling_14d_unique_visitors`, `rolling_14d_clones`, `rolling_14d_unique_cloners`
- `window_count:<referrer>`, `window_uniques:<referrer>`, `window_count:<path>`, `window_uniques:<path>`
- stars, as a secondary observation only

Do not solicit stars. `POLICY_STAR_FLOOR` 30 is a product policy, not a power calculation.

## Observation window

Not started.

Before the field may be flipped:

- Store at least 7 distinct calendar days of `daily_unique_visitors`. Preferred: 14.
- Only then, on a UTC date T, set the homepage to that one URL. T is in neither window.
- Post window: T+1 through T+14, fetched while each day is still inside GitHub's retention. One fetch on the last day is not enough.

## Frozen confounders

If any of these change between the first baseline day and the last post day, the label is `UNKNOWN`.

- No new tag, release, or announcement. Latest release stays `v0.7.7`.
- In-repo `Formula/wheretoken.rb` stays on the `v0.7.6` source tarball. The external tap is a different repository and is not a fix target.
- Description text stays `你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`.
- Topics stay `cli`, `developer-tools`, `go`, `golang`, `tokens`.
- README blob, profile card, and Pages content stay as deployed.
- No social post, no promotional Discussion, no star solicitation.
- Homepage, once set, stays that one URL.

## Candidates refused for this experiment

These are real, and they are not this treatment.

| id | classification | why it is not this experiment |
|---|---|---|
| `wt-readme-demo-cta` | `SAFE_NONFUNCTIONAL` | One README line to `/demo/` is a second treatment. A commit moves `pushed_at` and touches a surface of `gx-single-install-path-v1`. |
| `wt-topics-usage` | `SAFE_NONFUNCTIONAL` | Adding `usage-analytics` and `token-usage` is two labels. Reviewers disagreed with a no-change reading and with a four-topic add. Topics stay frozen. |
| `wt-description-english` | `SAFE_NONFUNCTIONAL` | Default search already matches the Chinese description for `coding agent`. Replacing or prepending it is a different search-document experiment. |
| `wt-site-privacy-copy` | `SAFE_NONFUNCTIONAL` | Pages privacy bullets overclaim relative to Cursor/Trae account calls, hosted sync, and profile refresh. Correcting them changes Pages content, which is frozen. |
| `wt-formula-v077` | `APPROVAL_REQUIRED_FUNCTIONAL` | In-repo formula still urls the `v0.7.6` source tarball. Do not invent a checksum or edit the formula. |
| `wt-distribution` | `HUMAN_DISTRIBUTION_ACTION` | Hacker News, Reddit, X, WeChat, Discord, maintainer mail, Product Hunt, and a promotional Discussion were not sent. |

## What would make a later result invalid

A missing day stored as zero. A rolling 14-day total used as the effect. Stars used as the primary success. A second public string changed in the same window. A traffic token reused from `gh` or `GITHUB_TOKEN`. Telemetry added to whereToken. The homepage written before 7 stored calendar days exist.

## Superseded before treatment

Recorded 2026-10-05. This pre-registration is `SUPERSEDED_BEFORE_TREATMENT`.

reason: metric/treatment mismatch

The sections above are the original pre-registration. They were not rewritten. The homepage field was not changed. It was still JSON `null` when this supersession was written. No traffic row was stored.

`daily_unique_visitors` is counted when the repository page loads. The About homepage link is visible only after that load. Repository search does not read the homepage field. The same Pages URL is already in the README. What remains is a return visit, an external index hit, or an API consumer, and none of those is identifiable as a first arrival in `daily_unique_visitors`. A flat median would not say the field does not matter. It would say this metric cannot see it.

The replacement record is `docs/growth-experiment-wheretoken-2.md`. `build_plan` still does not name a channel.
