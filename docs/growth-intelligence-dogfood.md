# Growth Intelligence dogfood, 2026-10-04, owned-observation round

This round started from `ad96569` on `engineering/growth-intelligence`. It did not rebuild the casebook and it did not edit whereToken, Nightshift, or the dirty Foreshadow checkout.

## What changed in the reading

The generic planner no longer contains whereToken version strings. The whereToken row carries `treatment_id` `gx-single-install-path-v1` and a `surface_discrepancy`: observed `v0.7.6`, expected `v0.7.7`, surfaces `Formula/wheretoken.rb` and `README.md`. A synthetic repository with `1.2.3` versus `9.9.9` on `docs/INSTALL.md` produces the same treatment class.

`gx-single-install-path-v1` is a treatment check. State `TREATMENT_READY`. Implementation metric `install_path_agreement`. Evidence `HYPOTHESIS`. There is no outcome window. Passing it later would be `READY_FOR_OBSERVATION`, still not `EXPERIMENT_RESULT`.

`gx-qualified-traffic-v1` is the adoption question for whereToken. Outcome metric `unique_visitors`, secondary `unique_cloners`, stars as a secondary observation only. State `INSUFFICIENT_BASELINE`. Evidence `UNKNOWN`. `low_power` is true because no pre-intervention traffic row is stored. It is not exportable. It does not name a channel. The earlier unsaved read of 6 unique views is not a baseline. The metric names in this paragraph are what this round shipped. The follow-up below renamed them before any live row was stored.

Transfer status is `UNKNOWN`. Age compatibility is `not_comparable` (whereToken was created 2026-08-15; the one-command controls are much older). Archetype is `mixed`. Measurement quality is `unknown`. The band is not an effect size.

Portfolio field is `intervention_priority`, meaning `actionable-friction`.

| Repository | Eligible | Intervention priority | Reason |
|---|---|---:|---|
| `rainhuang0220/whereToken` | yes | 5 | eligible |
| `rainhuang0220/foreshadow` | yes | 4 | eligible |
| `rainhuang0220/nightshift` | no | null | release-blocked |

## Commands

`growth study`, `portfolio`, `plan`, `export`, and `observe` are on the Decide panel. Plan and export used `--as-of 2026-10-04T11:50:00Z`, after the latest casebook observation `2026-10-04T10:35:00Z`. `expires_at` is `2026-10-18T11:50:00Z`.

`growth plan --json` wrote `docs/growth-intelligence-plan.json`. The public JSON omits `target_record`.

Portable work order `docs/growth-intelligence-work-order.json`:

- task `wo-c438408810f4c0c09fdaa391`
- repository path null
- base revision `6948f7522a0a98d4f7d2619583e1b717b9363162`
- validation argv `git grep -n -F -e v0.7.7 -- Formula/wheretoken.rb`

That argv shows the expected token in the first surface. It does not show that `v0.7.6` is gone, and it does not check `README.md`. The expectation string still requires both surfaces to name `v0.7.7` rather than `v0.7.6`.

Nightshift at `e27a83a` validated that file. Its canonical JSON matched the file byte for byte. Preview was not run. Nothing was executed. Unattended Nightshift release remains NOT READY.

## Owner traffic credential

`FORESHADOW_OWNER_TRAFFIC_TOKEN` was not set. `GITHUB_TOKEN` was not set. This round did not call the traffic API and did not use the logged-in `gh` credential. The public client still denies `/traffic`.

The credential an operator can create later, and only if they want stored baselines:

- Fine-grained personal access token.
- Repository access limited to the owned repositories to observe. For this experiment, `rainhuang0220/whereToken` is enough.
- One repository permission: Administration, Read. GitHub's REST docs for API version 2026-03-10 document that permission for clones, page views, top referral paths, and top referral sources (https://docs.github.com/en/rest/metrics/traffic). The same page says the endpoints are for repositories the caller can write.
- Do not grant classic `repo`. Do not reuse the current `gh` login. Do not put this token in `GITHUB_TOKEN`.
- Export it only as `FORESHADOW_OWNER_TRAFFIC_TOKEN`.

`growth observe rainhuang0220/whereToken` then stores dated rows. Days GitHub omits stay missing. They are not stored as zero. Without that token the adoption experiment remains `INSUFFICIENT_BASELINE`.

## What this round did not do

It did not modify whereToken. The install-path patch can be applied by hand outside this task. It did not post, tweet, open a promotional issue, message a maintainer, solicit stars, or add a posting client. It did not train a model. It did not expand the 40-repository casebook. It did not release Foreshadow.

From this worktree, `PYTHONPATH=src` and the existing engineering virtualenv: the full Foreshadow suite passed 873, skipped 3, and failed 0. The three skips were already present. No existing test was deleted or weakened. Official Top 5 and contribution scoring were not edited.

The casebook still cannot support a comparative growth claim. Current README snapshots remain `UNKNOWN` as explanations of historical stars. The machine path's field-by-field verdict is in `docs/growth-intelligence-casebook.md`.

## Evidence-integrity follow-up

Starting from `4d5e96c` on the same branch, and still without a live traffic call: a same-day referrer or path refetch now replaces that fetch date's snapshot in one transaction. `growth observe` no longer accepts `--as-of`. The fetch clock is the process clock, and tests inject a clock. Daily rows are `daily_unique_visitors` and `daily_unique_cloners`. The endpoint's top-level 14-day `count` and `uniques` are stored separately and are not a sum of the daily uniques. The adoption experiment remains `INSUFFICIENT_BASELINE` / `UNKNOWN`. The full suite after this pass passed 883, skipped 3, and failed 0.
