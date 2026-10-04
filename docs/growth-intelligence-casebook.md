# Growth casebook, 2026-10-04

This note is the human reading of `src/foreshadow/growth_intel/casebook.json`. The JSON is the scoring set: 40 repositories, schema `foreshadow.growth-casebook` version 1, selection `RETROSPECTIVE_SELECTION`, epistemic ceiling `HYPOTHESIS`. Counts, licenses, topics, default-branch SHAs, and README blob SHAs were read from the GitHub API at each row's `observation_time`. The latest row time is `2026-10-04T10:35:00Z`. Full SHAs live in the JSON. Twelve-character prefixes below are locators, not substitutes.

README mechanism flags describe the blob at that SHA. Scope is `CURRENT_SNAPSHOT`. A flag that could not be read is null. Null is not false and is not zero. No row is a daily star history. Public stargazer timestamps were not available for third-party repositories (the `starred_at` media type returned 404 on `astral-sh/uv` and `browser-use/browser-use` during the API check). Foreshadow's own `snapshots` table is the longitudinal store. This casebook does not backfill one.

## Sample composition

| Stratum | Rows | What it is |
|---|---:|---|
| AI / coding-agent breakouts | 7 | Famous agent tools, including one platform-owned repo |
| AI matched controls | 5 | Smaller or stalled peers, including one archived repo |
| CLI / local-first breakouts | 8 | Long-lived developer CLIs plus `astral-sh/uv` |
| CLI predecessor | 1 | `astral-sh/rye`, partial match to uv |
| CLI controls | 5 | Same category, much smaller star stocks |
| Developer-infrastructure breakouts | 7 | Converters, libraries, and HTTP clients |
| Infrastructure controls | 4 | Older document tools matched weakly or partially to markitdown |
| Owned portfolio | 3 | whereToken, Foreshadow, Nightshift |

Brand advantage in the scoring set: 24 low, 10 medium, 6 high. Maintainer class is a judgment recorded next to `owner_type`, not an API field. High brand means a platform owner or a company whose distribution is not something a solo maintainer can reproduce. Those rows stay in the table so the brand is visible. `select_cohort` drops them from a transferable cohort.

| Identity | Role | Archetype | Stars | Forks | Created | Brand | Class | Matched to | One-command | SHA |
|---|---|---|---:|---:|---|---|---|---|---|---|
| `anomalyco/opencode` | breakout | ai-agent | 211674 | 28138 | 2025-04-30 | medium | startup |  | false | `907b3bc518fa` |
| `browser-use/browser-use` | breakout | ai-agent | 117099 | 12925 | 2024-10-31 | medium | startup |  | false | `7be96ed8bafa` |
| `github/spec-kit` | breakout | ai-agent | 140058 | 12539 | 2025-08-21 | high | platform |  | true | `ae5ade7234be` |
| `OpenHands/OpenHands` | breakout | ai-agent | 89943 | 11882 | 2024-03-13 | medium | startup |  | true | `a6bba78ffd5a` |
| `cline/cline` | breakout | ai-agent | 69815 | 7600 | 2024-07-06 | medium | startup |  | true | `39ff2359f7e0` |
| `Aider-AI/aider` | breakout | ai-agent | 49368 | 5026 | 2023-05-09 | low | small team |  | false | `5dc9490bb35f` |
| `continuedev/continue` | breakout | ai-agent | 36106 | 5443 | 2023-05-24 | medium | startup |  | false | `5522c6f44ca0` |
| `mikehasa/agentacct` | control | ai-agent | 763 | 82 | 2026-07-24 | low | solo | whereToken, partial | unknown | `03f1dd803662` |
| `neovateai/neovate-code` | control | ai-agent | 1560 | 155 | 2025-03-11 | low | small team | opencode, good | true | `0a24b363ecbe` |
| `Jeomon/Web-Use` | control | ai-agent | 302 | 57 | 2024-10-03 | low | solo | browser-use, good | false | `36fe04eaedda` |
| `shotgun-sh/shotgun` | control | ai-agent | 687 | 38 | 2025-08-05 | low | startup | spec-kit, good | true | `4d344d5a46aa` |
| `lmnr-ai/index` | control | ai-agent | 2442 | 185 | 2024-11-30 | medium | startup | browser-use, good | true | `d64bce88d95c` |
| `astral-sh/uv` | breakout | cli-local | 90404 | 3628 | 2023-10-02 | high | startup |  | true | `46b84fd0bfec` |
| `astral-sh/rye` | predecessor | cli-local | 14142 | 467 | 2023-04-22 | high | startup | uv, partial | false | `62ec9edbe471` |
| `BurntSushi/ripgrep` | breakout | cli-local | 68825 | 4407 | 2016-03-11 | low | solo |  | false | `3fce3b5bb023` |
| `sharkdp/fd` | breakout | cli-local | 44632 | 1151 | 2017-05-09 | low | solo |  | unknown | `3460b1e96c3c` |
| `sharkdp/bat` | breakout | cli-local | 60668 | 3317 | 2018-04-21 | low | solo |  | unknown | `4608fc959aa8` |
| `ajeetdsouza/zoxide` | breakout | cli-local | 39861 | 916 | 2020-03-05 | low | solo |  | false | `86b443cffcd7` |
| `casey/just` | breakout | cli-local | 36120 | 857 | 2016-06-17 | low | solo |  | false | `602ee328c9b2` |
| `jdx/mise` | breakout | cli-local | 34573 | 1457 | 2023-01-09 | low | solo |  | true | `17123d84c783` |
| `dandavison/delta` | breakout | cli-local | 32413 | 589 | 2019-06-24 | low | solo |  | false | `6fae1cfbe552` |
| `dalance/amber` | control | cli-local | 954 | 25 | 2016-01-21 | low | solo | ripgrep, partial | true | `a6d54a5957f6` |
| `VladimirMarkelov/haku` | control | cli-local | 46 | 3 | 2019-12-28 | low | solo | just, partial | unknown | `0ae3e93d804d` |
| `jacobdeichert/mask` | control | cli-local | 1626 | 61 | 2019-07-06 | low | solo | just, partial | unknown | `0ba24c1eff6a` |
| `jethrokuan/z` | control | cli-local | 1535 | 50 | 2016-02-27 | low | solo | zoxide, partial | unknown | `26a50962bc68` |
| `pdm-project/pdm` | control | cli-local | 8665 | 497 | 2019-12-27 | low | small team | uv, weak | unknown | `390bb6d1e446` |
| `microsoft/markitdown` | breakout | dev-infra | 188275 | 13934 | 2024-11-13 | high | platform |  | true | `4cc9fa17653d` |
| `docling-project/docling` | breakout | dev-infra | 68355 | 4994 | 2024-07-09 | high | platform |  | unknown | `58f1f8d907fd` |
| `jgm/pandoc` | breakout | dev-infra | 46545 | 5573 | 2010-03-20 | medium | solo |  | false | `1c81b5196430` |
| `Textualize/rich` | breakout | dev-infra | 57473 | 2387 | 2019-11-10 | medium | startup |  | false | `9d8f9a372cc5` |
| `pydantic/pydantic` | breakout | dev-infra | 28935 | 3013 | 2017-05-03 | high | startup |  | unknown | `e87e11b7a740` |
| `fastapi/typer` | breakout | dev-infra | 20048 | 983 | 2019-12-24 | medium | startup |  | false | `a80f6e5ecd74` |
| `encode/httpx` | breakout | dev-infra | 15524 | 2950 | 2019-04-04 | medium | small team |  | false | `b5addb64f016` |
| `jsvine/pdfplumber` | control | dev-infra | 10787 | 929 | 2015-08-24 | low | small team | markitdown, partial | unknown | `4c64b92d5cac` |
| `deanmalmgren/textract` | control | dev-infra | 4727 | 720 | 2014-07-03 | low | small team | markitdown, partial | unknown | `7622ecf7449a` |
| `ssine/pptx2md` | control | dev-infra | 1278 | 160 | 2018-11-02 | low | solo | markitdown, weak | unknown | `39bef65b3120` |
| `lepture/mistune` | control | dev-infra | 3076 | 311 | 2014-02-18 | low | solo | markitdown, weak | false | `a1b50bc12e06` |
| `rainhuang0220/whereToken` | owned | portfolio | 3 | 0 | 2026-08-15 | low | solo |  | true | `6948f7522a0a` |
| `rainhuang0220/foreshadow` | owned | portfolio | 0 | 0 | 2026-08-24 | low | solo |  | true | `da5129f580b3` |
| `rainhuang0220/nightshift` | owned | portfolio | 0 | 0 | 2026-10-02 | low | solo |  | false | `36b2cf1b0082` |

`lmnr-ai/index` was archived at the 2026-10-04 read (`pushed_at` 2025-06-09). `sharkdp/fd`, `sharkdp/bat`, and `pydantic/pydantic` have unknown install flags because the README body fetch failed. `jacobdeichert/mask`, `jethrokuan/z`, and `pdm-project/pdm` have null README blob SHAs. Those gaps stay gaps.

`mikehasa/agentacct` is a partial peer of whereToken: solo, Python, created 2026-07-24, explicit local-first coding-agent cost dashboard, 763 stars and 82 forks at `2026-10-04T10:35:00Z`. Star legitimacy is UNKNOWN. It is a counterexample to "a new local-first agent dashboard stays at three stars," not a tactic to copy. Contributor count was not verified.

## What the rows show

Platform and company repositories hold very large star stocks. On this date, `github/spec-kit` had 140058 stars at age about 408 days, `microsoft/markitdown` 188275, `astral-sh/uv` 90404, and `docling-project/docling` 68355. That is an observation about distribution. It is not a transferable engineering tactic. Cohort selection excludes `brand_advantage` high and unknown.

Solo Rust CLIs also reached large stocks, over many years. `BurntSushi/ripgrep` was created in 2016 and had 68825 stars. `sharkdp/fd`, `sharkdp/bat`, `ajeetdsouza/zoxide`, `casey/just`, and `dandavison/delta` sit in the same band. Age in that band does not predict what a repository created on 2026-08-15 can copy from today's README.

One-command install is not sufficient. `neovateai/neovate-code` documents `npm install -g` and a docs link, was created 50 days before opencode, and had 1560 stars, with the last push on 2026-03-24. `shotgun-sh/shotgun` documents a one-command install in the same month spec-kit was created and had 687 stars, against spec-kit's 140058 under the GitHub account. `lmnr-ai/index` documents a one-command install and a demo, carries a startup brand, and is archived at 2442 stars. `dalance/amber` is a solo search tool from the same year as ripgrep, documents a one-command install, and had 954 stars against ripgrep's 68825. `Jeomon/Web-Use` is a solo browser agent created a month before browser-use and had 302 stars against 117099. The first screen of opencode and browser-use, as read for the control pass, did not show an install command. Install polish and star stock move apart in this set.

Category is not destiny. `VladimirMarkelov/haku` is a solo task runner, last meaningful activity years before this read, at 46 stars, against `casey/just` at 36120. `jgm/pandoc` shows the other direction: a solo maintainer, created in 2010, medium personal brand, 46545 stars, and no one-command install on the current first screen. Duration and prior audience are doing work that a README edit does not capture.

`Aider-AI/aider` is the low-brand breakout inside the agent stratum (small independent team, 49368 stars, created 2023-05-09, one-command flag false on the current snapshot). It blocks the claim that only platform accounts reach a large stock. It does not identify which of aider's years, distribution, or product surface a fifty-day-old repository can reproduce.

## Examined and left out of the 40

The cap is 40 scoring rows. These four were read in the same control pass and are not scored. Facts are from `gh api` at the times below.

| Identity | Stars | Observed | Why it stayed out | SHA |
|---|---:|---|---|---|
| `rusiaaman/wcgw` | 678 | 2026-10-04T10:23:27Z | Solo, partial match to opencode, not the closest control | `339201affd17` |
| `kodu-ai/claude-coder` | 5217 | 2026-10-04T10:22:38Z | Stalled VS Code agent, medium brand, Cline-lineage credit | `60c1a717992c` |
| `Pimzino/spec-workflow-mcp` | 4302 | 2026-10-04T10:26:17Z | Low brand, partial spec-kit match; would have been row 41 | `d38e82eaa8a6` |
| `VRSEN/agency-swarm` | 4591 | 2026-10-04T10:26:52Z | Weak match, no single breakout pair | `1aeb325b6a3f` |

A selection pass on the same morning also saw, and did not case, `google-gemini/gemini-cli` (107227), `openinterpreter/openinterpreter` (68504), `crewAIInc/crewAI` (59331), `aaif-goose/goose` (54927), `cursor/cursor` (33259), `huggingface/smolagents` (29667), `charmbracelet/crush` (28480), `RooCodeInc/Roo-Code` (24289), and `SWE-agent/SWE-agent` (20486). Observation window for that pass: `2026-10-04T10:22:40Z` and `2026-10-04T10:30:09Z`. Adding more famous winners would have made the book a leaderboard. `openai/codex` was seen as a high-brand breakout and was not added.

## What published work already constrains

Stars are a social signal. In the Borges and Valente survey of 791 developers who had just starred a top repository, 52.5% named appreciation, 51.1% bookmarking, and 36.7% use (https://arxiv.org/abs/1811.07643, HTML read for this design). Inside the already-famous set, language, domain, and org ownership shift medians, and age does not predict the stock (https://arxiv.org/abs/1606.04984). Release weeks accelerate stars and do not hold the lifetime count. README length was not a top discriminator of growth shape, and the authors mark reverse causation as open. Aggarwal, Hindle, and Stroulia (MSR 2014, https://dl.acm.org/doi/pdf/10.1145/2597073.2597120) read the tested documentation direction as popularity attracting later edits. Hacker News before/after gaps were measured on posts that had already reached the top decile, on repositories that were already famous (https://arxiv.org/abs/1908.04219). Bought stars do not create downloads in the later study that cites that work (https://arxiv.org/html/2603.07919v1). None of these papers randomly assigns a README edit to a solo maintainer and measures stars. This casebook does not pretend to close that gap.

## Transfer

The mechanism that can move to a solo repository is narrow: do not publish two install artifacts that name different versions. The owner can edit both files. The change is reversible. The mechanism that cannot move is the launch distribution of `github/spec-kit`, `microsoft/markitdown`, `astral-sh/uv`, or `docling-project/docling`.

Why the file edit might help whereToken: a stranger who follows the in-repo formula and the tap formula does not get the same version, and the README already says the tap and `go install` do not produce the same surface. That is a measured contradiction on commit `6948f7522a0a98d4f7d2619583e1b717b9363162`.

Why it might not help: neovate, shotgun, amber, and the archived lmnr repo already show a coherent one-command path without entering the star regime of their matched breakouts. whereToken has 3 stars. A 14-day star delta is underpowered below the floor of 30. The curl installer, the Chinese-first dashboard, and unsigned macOS binaries are separate friction, and this experiment does not touch them. Agentacct's 763 stars show that a nearby product can be noticed without this repository's formula edit. The source of that gap is UNKNOWN.
