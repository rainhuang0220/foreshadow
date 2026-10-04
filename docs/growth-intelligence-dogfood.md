# Growth Intelligence dogfood, 2026-10-04

The slice was exercised from the isolated worktree `engineering/growth-intelligence`, with `PYTHONPATH=src` pointed at that tree. The dirty Foreshadow checkout, Nightshift source, and whereToken source were not edited.

## Commands

`foreshadow growth study`, `portfolio`, `plan`, and `export` are registered on the Decide panel. `growth --help` names those four commands and does not mention GraphQL, sqlite, or argparse.

Plan and export used `--as-of 2026-10-04T10:40:00Z`. That instant is after every casebook `observation_time` (latest `2026-10-04T10:35:00Z` on `mikehasa/agentacct`) and was already in the past when Nightshift checked freshness. `expires_at` is `2026-10-18T10:40:00Z`.

`growth plan --json` wrote `docs/growth-intelligence-plan.json`. The public JSON omits `target_record`. Export uses the in-memory plan, which still carries that record. A later process that only has the dumped plan cannot export until it rebuilds the plan.

## Portfolio result the tool printed

| Repository | Eligible | Score | Reason |
|---|---|---:|---|
| `rainhuang0220/whereToken` | yes | 5 | eligible |
| `rainhuang0220/foreshadow` | yes | 4 | eligible |
| `rainhuang0220/nightshift` | no | null | release-blocked |

Recommended experiment: `gx-single-install-path-v1`. Evidence strength `HYPOTHESIS`. Transfer band `medium`, status `HYPOTHESIS`. That band means a low-brand maintainer can edit the file. It is not an effect size and it does not match on age. The sources are the one-command controls, not the whole casebook. Those controls, named as counterevidence: `dalance/amber`, `lmnr-ai/index`, `neovateai/neovate-code`, `shotgun-sh/shotgun`. No backlog item is `QUASI_EXPERIMENTAL`.

## Work order

Portable file: `docs/growth-intelligence-work-order.json`.

- schema `engineering.work-order`, version 1 (integer)
- task id `wo-281085fcfc8ed7ea225c2d93`
- repository `rainhuang0220/whereToken`
- `path` null, `url` `https://github.com/rainhuang0220/whereToken`
- `base_revision` `6948f7522a0a98d4f7d2619583e1b717b9363162`
- actions allowed `read`, `edit`, `commit`
- actions forbidden `credentials`, `deploy`, `external-write`, `publish`, `push`
- validation argv: `git grep -n -F -e refs/tags/v0.7.7.tar.gz -- Formula/wheretoken.rb`
- rationale contains "This is not a causal claim." and the current-README counterevidence sentence
- observation summary quotes the v0.7.6 formula blob and the v0.7.7 tap

Nightshift at `e27a83a6947d708b5883f808f925688f44220d2e` validated that file. Its canonical dump matched the file byte for byte.

Preview used a second file that differs only by `repository.path` = `/Users/rainhuang/Desktop/whereToken`. That copy's task id is `wo-562c16826664404ed7153fe0`. It is not committed, because the path is this machine's checkout. `nightshift work-order preview --provider fake` returned a plan with `provider=fake`, `network=false`, `write_scope=workspace`, `isolation=clone`, `base_ref` equal to the pinned public commit, and the prompt containing both `v0.7.7` and "not a causal claim." Preview calls `plan_order`, which reads git state and does not create a worktree. No `import`, no `--run`, and no `grok` provider.

`git status` on `/Users/rainhuang/Desktop/whereToken` was unchanged: still behind `origin/main` by 22, with the same untracked `.superpowers/`, `docs/superpowers/plans/2026-09-01-v060-model-pricing-portrait.md`, and `image.png`. HEAD remained `75cef1ae06da50d2801c7febdc2ac599af22ac4d`. The pinned public commit is present in that object store, which is why preview could resolve it. The checkout itself was not moved onto that commit.

The validation argv fails on today's formula, which still urls `v0.7.6`. It passes only after that file names `refs/tags/v0.7.7.tar.gz`. It does not by itself check the README. The README half is the `expectation` string the executor has to satisfy. That split is deliberate: Work Order v1 takes one argv, not a shell comparison.

## Tests

From this worktree, `PYTHONPATH=src` and the existing engineering virtualenv: `tests/test_growth_intel.py` passed 21. The full Foreshadow suite then passed 854, skipped 3, and failed 0. No existing test was deleted, skipped, or weakened. Official Top 5 and contribution scoring were not edited.

## What this dogfood did not do

It did not execute the work order. Nightshift unattended release remains NOT READY. It did not fetch traffic. It did not train a model. It did not rewrite a README. It did not open an issue, solicit stars, or publish a release. It did not treat the casebook as a causal estimate. The study's only README claim is `UNKNOWN`, because every README blob is a `CURRENT_SNAPSHOT`.
