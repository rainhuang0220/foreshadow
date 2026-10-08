# whereToken growth recovery, 2026-10-08

Phase: `OBSERVATIONAL_GROWTH_SPRINT`.

This replaces the active plan in `docs/growth-experiment-wheretoken-2.md`. That file is `SUPERSEDED_BY_GROWTH_RECOVERY`. Its pre-registration was not rewritten. No eligible baseline day was stored, so there is no causal outcome to preserve.

`build_plan` is unchanged and still channel-agnostic. A traffic change after this date is `UNKNOWN` as a cause. It may later be `OBSERVED_CHANGE` or `NO_CLEAR_CHANGE`. It is not evidence that one field worked.

## Observation

Fetched from the public GitHub API unless another source is named. Stars were 3 at `Date: Thu, 08 Oct 2026 03:58:50 GMT` and still 3 at `Date: Thu, 08 Oct 2026 04:07:34 GMT`. Forks 0. The open issue list was four pull requests, `#11`, `#7`, `#6`, and `#5`. No external trial issue was open.

Search `token usage claude code`, sorted by stars, `Date: Thu, 08 Oct 2026 03:59:36 GMT`, total 2116. Page 1 began with `getagentseal/codeburn` (11349), `teamchong/pxpipe` (7506), `junhoyeo/tokscale` (5640). `rainhuang0220/whereToken` was not on that page. A name search found the repo only by the name `wheretoken`.

Before the metadata write, the description was `你的 token 都花在哪 — 本机优先的 coding agent 用量观测器`, homepage was null, and topics were `cli`, `developer-tools`, `go`, `golang`, `tokens`. The profile pins, from GraphQL as `rainhuang0220`, included `rainhuang0220/whereToken`.

Release `v0.7.7` was published `2026-09-27T05:52:36Z`. Asset `download_count` at `Date: Thu, 08 Oct 2026 03:58:52 GMT`: checksums 7, darwin arm64 6, windows amd64 2, every other listed asset 0. These counts mix unknown self-downloads, CI, and other people. They are not users.

`GET /repos/rainhuang0220/whereToken/traffic/views` returned 401. `FORESHADOW_OWNER_TRAFFIC_TOKEN` was unset. Fourteen-day views, uniques, clones, referrers, and paths are `UNKNOWN`. No number was filled in.

`https://wheretoken.plainlist.space/api/health` at `Date: Thu, 08 Oct 2026 04:01:30 GMT` was HTTP 200, body `{"status":"ok","version":"v0.7.7"}`. An anonymous browser open of `https://wheretoken.plainlist.space/` landed on `/login?next=/app`. The page says GitHub login identifies the account and does not request repository permission. It does not show a ledger before login.

`https://rainhuang0220.github.io/whereToken/demo/` rendered. The visible header included `2026/9/4 12:59:10 · 演示数据`. The first screen showed a kiln wall, 16.78 M peak, and $500.08, with the line that the price is a public-list equivalent and not a subscription bill. The script and stylesheet URLs in the HTML returned with the page.

`go run ./cmd/wheretoken --offline` with `WHERETOKEN_HOME` pointed at an empty directory printed a note that no ledger was found. Hit rate, estimated cost, and portrait were `—`. The total and today lines printed `0.00 M`. The real home ledger was not read.

`Formula/wheretoken.rb` on `c56f52d` and on `b3917eb` is still the v0.7.6 tarball, sha256 `384780534bf6051ca546519ac74182d6f6bfb6331677c04299030a18399417bf`. `https://registry.npmjs.org/wheretoken` returned 404. The README already says release binaries are unsigned.

CI on `cd3213d` had succeeded. CI for the presentation merge was still running when this note was started. The formula packet in `docs/growth-approval-wheretoken-formula-v077.md` stays unapplied.

### Competitors, same window

Counts are the API values the read-only pass fetched between `2026-10-08T03:59:25Z` and `2026-10-08T04:03:08Z`. Star gaps are not a quality ranking and are not a cause.

| Repo | Stars | What the README actually says |
|---|---:|---|
| `ccusage/ccusage` | 18911 | Local CLI. `npx ccusage@latest`. Many agent JSONL sources. LiteLLM pricing file. `--compact` is for screenshots. Awesome Claude Code badge. No published price card and no missing-versus-zero rule in the fetched README. |
| `junhoyeo/tokscale` | 5640 | Local TUI plus an optional public leaderboard. `npx tokscale@latest`. Cursor is a web export, not `~/.cursor`. An omitted price stays unpriced. Trae China is not supported. |
| `steipete/CodexBar` | 22292 | macOS menu-bar app and Linux CLI. `brew install --cask codexbar`. Quota and spend for many providers. On-device by default. Incomplete history stays labeled. Not a local-ledger price card. |
| `mag123c/toktrack` | 193 | Local tracker. `npx` or a Homebrew tap. A missing LiteLLM price shows `?`. `toktrack report` writes text and SVG. |
| `juliantanx/aiusage` | 137 | Local-first tracker with a localhost dashboard and optional cloud sync. Historical totals depend on retained logs. |
| `splunk/token-meter` | 113 | Local only. The README says missing evidence stays unavailable, never zero. No GitHub release. |
| `korjwl1/toki` | 21 | Claude Code and Codex JSONL. Homebrew tap. Missing price cache omits the cost column. |
| `itchernetski/claude-code-token-meter` | 14 | Claude Code JSONL only. `pipx`. Localhost dashboard. No cloud. |

`splunk/token-meter` already states the missing-versus-zero rule. whereToken does not own that sentence. whereToken does publish `wheretoken pricing` as a built-in card whose help text says the rates have official sources, and `docs/token-accounting.md` defines the six figures. That is a documentation difference. It is not a measured accuracy advantage.

Cursor and Trae account calls are labeled on the landing page. Tokscale's README says Cursor is not parsed from `~/.cursor` and Trae China is unsupported. Those are different mechanisms. Neither side was timed or checked against the same account in this sprint.

## Hypothesis

These are guesses. They are not findings.

- English queries miss the repo while the description is only Chinese. The description now contains English. A later search can check the page-1 fact again. The change is not itself the proof.
- A first-time visitor who hits GitHub login before seeing a number leaves. The old primary button was that login. The new primary button is the synthetic demo. No click log exists.
- `npx` is a shorter first command than an unsigned installer or a two-step Homebrew tap. whereToken's demo is the response to that, not a claim that the installer is easy.
- The shareable object is a sanitized public profile or a labeled synthetic screenshot. The maintainer-only features are hosted sync, the profile scheduler, and Community Rank. No external share was observed.
- Five to ten external trials will show whether install and the empty-ledger message are the activation break. No trial has been returned.

## Presentation actions

Not a causal treatment. `treatment_applied` for `wt-description` stays false.

| Time | Action |
|---|---|
| `2026-10-08T04:07:14Z` | Pull request `#13` merged as `c56f52d98376fe1f3b5a7abf44daa458f53830f1`. Parents include `0ee2ac00f300cb780fc4e3563b47e73c61df6bc1` and `92cafa493b1504ba4613a511eae9ff5f20b7b71a`. Files: `README.md`, `README.zh-CN.md`, `site/index.html`. |
| `2026-10-08T04:07:28Z` | Unauthenticated read still showed the old description and a null homepage. |
| `2026-10-08T04:07:34Z` | Unauthenticated read showed description `Local-first token usage analytics for coding agents · 你的 token 都花在哪` and homepage `https://rainhuang0220.github.io/whereToken/`. Topics were unchanged. |
| `2026-10-08T04:09:19Z` | Pull request `#14` merged as `b3917ebebb67534b92168d238689928349ff3a03`. Files: `.github/ISSUE_TEMPLATE/external-trial.yml` and `config.yml`. |

Author and committer on the branch commits were `rainhuang0220 <iamrainhuang@163.com>`. The diff from `cd3213d` to `b3917eb` does not include `cmd/`, `internal/`, `scripts/`, `Formula/`, `npm/`, or `web/`.

The README links are `https://rainhuang0220.github.io/whereToken/demo/`, `#install` / `#安装`, and `docs/token-accounting.md`. The dashboard image is labeled synthetic. The landing primary button is Try Demo. Open Web App remains, with a sentence that it is GitHub login plus a paired CLI. The Go line says the dashboard is not in `go install`.

Pages workflow `37725949605` deployed `c56f52d` and finished success at `2026-10-08T04:15:28Z`. The live page at `Date: Thu, 08 Oct 2026 04:15:51 GMT` was HTTP 200, Last-Modified `Thu, 08 Oct 2026 04:11:03 GMT`, 13002 bytes, sha256 `030bd5f01fdc04deace2820c85994b7b1c47267d997e9e57aad9837f16e8aab2`. The primary button is Try Demo. Open Web App remains. CI on pull requests `#13` and `#14` succeeded (`37725949527`, `37726111550`). The issue-form merge does not match the Pages path filter.

## Human distribution actions

None were published.

| Channel | Who it is for | Why they might care | What to show | Asked action | Observable | Rule | State |
|---|---|---|---|---|---|---|---|
| GitHub profile pin | People who already open `rainhuang0220` | The repo is already pinned | Leave the pin. Optional later: profile README link to the live profile page, not an SVG used as the click target | None now | Profile page | Owner edits their profile repo | `RECOMMENDED_CHANNEL`. Already pinned. Not posted by this sprint. |
| Show HN | People who will run a local tool | The demo runs with no signup | Title starts with `Show HN`. URL is the demo, not the login app. Owner stays in the thread. Factual first comment: local ledgers, missing stays missing, unsigned install, synthetic demo | Try the demo and say what failed | Thread replies, not stars | https://news.ycombinator.com/showhn.html fetched 2026-10-08. Off-topic if it is only a landing page. No signup barrier. Owner must be present. | `RECOMMENDED_CHANNEL`. Not `AUTHORIZED_TO_POST`. |
| `hesreallyhim/awesome-claude-code` | Claude Code users browsing a list | whereToken reads Claude Code locally | One-line description, no emoji, not a sales sentence. Issue form, not a pull request. One resource only. | Maintainer accepts or closes | The list entry | CONTRIBUTING.md: at least 14 days old and later commits, or 100 stars. Use the web issue form. | `RECOMMENDED_CHANNEL`. Eligible on age. Not `AUTHORIZED_TO_POST`. |
| V2EX `/go/create` or a 分享创造 node | Chinese developers who try local tools | Chinese README and the brand line already exist | A build story and the demo. Not a bare link. | Try it and reply | Thread replies | V2EX FAQ allows a new work and rejects moving a pile of links. Some nodes require account age. Do not post the same text twice. | `RECOMMENDED_CHANNEL`. Not `AUTHORIZED_TO_POST`. |
| Direct ask of 5–10 people who use Claude Code, Codex, Cursor, or Kimi | Actual multi-agent users | They already have a ledger | The demo first, then one install path for their OS. Point them at the trial issue form | Fill the form | Issue replies | No star condition. No prompts, keys, sessions, or paths. No bulk DM and no paid stars. | `RECOMMENDED_CHANNEL`. The owner sends it. |

## Traffic observations

None. The owner token is still the gate for GitHub Insights numbers. Views, uniques, clones, referrers, and popular paths for the last 14 days are `UNKNOWN`.

The next useful fetch, after `FORESHADOW_OWNER_TRAFFIC_TOKEN` exists, is one `foreshadow growth observe rainhuang0220/whereToken` from revision `4952787` or later on `engineering/growth-intelligence`. Prefer `2026-10-09` `00:10–01:00 UTC` so `2026-10-08` can be a completed UTC day. That row is still not a causal baseline for the old single-field experiment. The presentation bundle already changed on `2026-10-08`, so days after that date are post-bundle observations.

## External user feedback

The form is on main at `b3917eb`. It asks for agents, OS, understanding, install result, whether the numbers looked like the user's own, whether that matched expectations, and what is missing. It forbids prompts, keys, sessions, and local paths. It does not ask for a star. Blank issues stay open. Zero replies so far.

## Outcome

`UNKNOWN`. Stars were still 3 in the minute after the description write. That is not a window. No external reply exists. No traffic series exists.

## Unknown

- Whether the English description appears on the first page of `token usage claude code` after GitHub reindexes.
- Whether anyone clicks Try Demo.
- Whether the empty-home `0.00 M` total is read as "no data" or as "you used nothing". Changing that is an accounting change and was not done.
- How much of the release `download_count` is the maintainer or CI.
- Whether hosted v0.7.7 and the in-repo formula v0.7.6 confuse a Homebrew-from-this-repo user. The external tap was not re-tested in this sprint.

## Approval still required

Do not apply these.

1. `Formula/wheretoken.rb` v0.7.6 to v0.7.7. Packet: `docs/growth-approval-wheretoken-formula-v077.md`. Sha256 `45c441683f15180330ad19b3a53f3708e9c763a3bcdcb7589e27cef3317e54e5`. Direct formula users would compile a different tag. Tap users are a different repo.
2. Demo application logic, including theme routing inside the built SPA. The static shell loads. No broken asset was seen. A code change stays closed.
3. Making `go install`, the release binary, and Homebrew serve the same dashboard. The landing copy now says they do not. The binaries were not changed.
4. Publishing `npm/`. The registry returns 404. The README already says so.
5. Signing the release binaries. They are unsigned. That is an install-trust change, not a copy change.

## What did not change

CLI parsing, adapters, cache, network, hosted sync, profile refresh, install scripts, Formula, npm packaging, dashboard runtime, demo logic, signing, version, and release. Topics. No social post. No telemetry.
