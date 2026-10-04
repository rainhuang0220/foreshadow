# Separate a landed change from an observed adoption outcome

Growth Intelligence could already propose a file edit. It could not yet say whether that edit had landed, or whether anyone then visited or cloned the repository. The first dogfood also put whereToken version strings inside the generic planner and treated an immediate file check as a 14-day outcome.

Status: accepted

## Decision

A repository observation may carry a structured discrepancy: `kind`, `observed`, `expected`, `affected_surfaces`, and `evidence`. The planner and the work-order exporter read `observed`, `expected`, `affected_surfaces`, and `evidence`. `kind` stays on the observation as a label. They do not contain repository version numbers of their own. `gx-single-install-path-v1` stays, as a treatment-integrity task. Its check is `install_path_agreement`. It has no outcome window. State `TREATMENT_READY` means the task can be applied. After a human or a downstream executor reports the check, `READY_FOR_OBSERVATION` means the files agree and `ABANDONED` means they do not. Either way the epistemic status stays `HYPOTHESIS`. Passing the check does not write `EXPERIMENT_RESULT`.

An adoption experiment is a different object. `gx-qualified-traffic-v1` leaves open whether one legitimate, targeted discovery surface could increase qualified traffic or cloning. This slice does not select that surface. Its outcome metric is `daily_unique_visitors`, the last stored day, not the rolling 14-day unique total. `daily_unique_cloners` is secondary. Stars are a secondary observation only. Daily unique counts are not summed into a window total. The plan does not name a channel, does not post, and does not export this object. With no stored pre-intervention rows its state is `INSUFFICIENT_BASELINE`, evidence `UNKNOWN`, and `low_power` is true because the baseline series is empty. That flag is not a sample-size calculation. A rolling 14-day comparison is not claimed.

`measure_outcome` compares stored rows only. Elapsed time is the calendar distance between the first and last post date. One post date, or two timestamps on the same date, stays `INSUFFICIENT_BASELINE`. A real span with integer visitor counts can be `MEASURED` with evidence `OBSERVED` and interpretation `OBSERVED_CHANGE`, `NO_CLEAR_CHANGE`, or `UNKNOWN`. `causal` stays false. The raw rows are kept. The result is not upgraded to `QUASI_EXPERIMENTAL`.

Owner traffic uses a separate credential, `FORESHADOW_OWNER_TRAFFIC_TOKEN`. The public GitHub client still denies `/traffic`. The official REST docs for API version 2026-03-10 (https://docs.github.com/en/rest/metrics/traffic) say the traffic endpoints are for repositories the caller can write, and that a fine-grained token needs Administration repository permission read for clones, page views, top paths, and top referrers. Each series covers the last 14 days. `per=day` is what this client requests. Classic `repo` scope is not required by that fine-grained permission and is not accepted as this design. The token is read only for an identity whose casebook role is `owned`. Requests are GET, refuse redirects, and redact the token from errors. The value is not written to SQLite, not printed, not placed in a work order, and not passed to Nightshift or a coding model. Public `GITHUB_TOKEN` is not consulted. `growth plan` works when the owner token is absent.

Daily view and clone counts go in `owner_traffic_observations` as `daily_views`, `daily_unique_visitors`, `daily_clones`, and `daily_unique_cloners`, with grain `day`. The same response's top-level `count` and `uniques` are the last-14-day totals named by the REST endpoint ("the total number of views" or clones, plus a per-day breakdown). Those totals are stored as `rolling_14d_views`, `rolling_14d_unique_visitors`, `rolling_14d_clones`, and `rolling_14d_unique_cloners`, with grain `window` and `observed_on` equal to the fetch date. They are copied from those two fields. They are not a sum of the daily rows. A missing key stays absent, which a reader treats as NULL / unknown. A day GitHub did not return is not inserted and is not stored as zero. A zero GitHub did return stays zero. Referrers and paths are a top-10 list over the last 14 days. The payload has no per-entry timestamp, so the client does not invent earlier days. Their metrics are `window_count:<label>` and `window_uniques:<label>`, grain `window`, and `observed_on` is the fetch date. Replacing one `(identity, source, observed_on)` snapshot removes labels that the new response omitted. The delete and the inserts are one transaction; a failed write leaves the previous snapshot. Other dates and the other source stay. `growth observe` does not accept `--as-of`. Production `fetched_at` comes from the process clock. Tests pass a clock. `growth plan` and `growth export` still use `--as-of` as an evaluation time. Schema version is 12. Columns are identity, source, observed_on, metric, value, fetched_at, and grain. The token is not a column.

Portfolio output is `intervention_priority` with `priority_meaning` `actionable-friction`. The arithmetic is unchanged: contradiction 3, missing job description 2, one-command install 1, demo 1, missing topics 1. Release-blocked repositories stay ineligible with a null priority. The number is not a growth probability. `POLICY_STAR_FLOOR` remains 30 and is documented as a product policy that rejects star-primary success below 30. It is not a power calculation. Contribution Opportunity and Expected Entry Value are untouched.

Transfer stays a structured assessment: archetype, maintainer class, brand, age compatibility, distribution context, mechanism reproducibility, and measurement quality. A low-brand source plus an editable file does not produce a band. Age is `not_comparable` when the target is under 180 days and a source is over 730 days, or the youngest source is over 365 days. Otherwise age is `unknown`. This slice never emits `comparable`, so the shipped status is `UNKNOWN`.

## Threat model

The owner token is a bearer secret that GitHub will honor for Administration reads on the selected repositories. The failure worth preventing is that secret leaving the process: a row in SQLite, a plan dump, a work order, a Nightshift argument, a model prompt, a redirect to another host, or a log line. The client therefore keeps the secret in the request header only, refuses redirects off the call, and redacts it from exceptions. The database table has no token column. The public radar never receives this credential, so a stolen `GITHUB_TOKEN` still cannot read traffic through Foreshadow's public client.

What this boundary does not stop: a fine-grained Administration read token can still read other administration metadata GitHub attaches to that permission. The mitigation is operational. Create the token for the selected repositories only, with that one permission, and do not reuse the logged-in `gh` credential. Foreshadow does not create the token.

## Considered options

Keep the file check and call its 14-day wait the outcome. Rejected. Waiting does not add information about a string compare.

Put traffic reads on the public GitHub client by widening `GITHUB_TOKEN`. Rejected. The public client is a read radar. Traffic is owner-only, and the docs require a permission the public token must not grow to hold.

Store traffic in the existing star snapshot table. Rejected. Stars and forks are public series. Mixing owner-only counts into that table would make a missing traffic day look like a star gap, and it would invite backfill.

Require a stored baseline before shipping the lifecycle. Rejected. The schema and the refusal path are useful before a token exists. The experiment stays `INSUFFICIENT_BASELINE` instead of inventing the earlier unsaved view count.

Upsert each referrer or path label and leave labels missing from the new response in place. Rejected. The top-10 response is the whole snapshot for that fetch date. A label that fell off the list is not still current.

Let `growth observe --as-of` choose the fetch date. Rejected. On the other growth commands `--as-of` is an evaluation time. A live referrer or path response has no per-entry timestamp, so a user-supplied date would present a new fetch as an older snapshot.

Sum the daily unique counts and store that sum as the 14-day unique total. Rejected. The endpoint already returns the 14-day total in top-level `uniques`. A person who appears on two days counts once in that field and twice in the sum.

Infer `transferability = medium` from one low-brand source and a solo maintainer. Rejected. That was a label for "someone can edit a file."

## Consequences

`growth observe` exits 2 when the owner token is missing and names the permission the operator would create. It does not fall back to `gh`. It does not accept a historical fetch date. Schema version is 12. Existing databases gain the traffic table and then a grain column. Nightshift still sees only Work Order v1, and only for the treatment. The adoption experiment is not a work order. No posting integration exists.

The work-order argv checks that the discrepancy's `expected` string occurs in the first affected surface. It does not by itself prove the old string is gone, and it does not check later surfaces. The expectation text still states the full success criterion.

## What remains unknown

No least-privilege token was present, so no live traffic row was stored. GitHub's 14-day window means a baseline that is not snapshotted now cannot be reconstructed later. Referrer and path rows are fetch-day snapshots. They cannot show which day a referrer appeared. The interpretation compares the chronologically last stored `daily_unique_visitors` integer in each window. That integer is one day's unique visitors. It is not the rolling 14-day `uniques` field, and the daily values are not summed. Input order does not matter. The other points stay in the raw series, and that series is what a later reader should use. None of that is a causal estimate.
