# Portfolio growth report, 2026-10-04

Read-only. No commit was made to whereToken, Foreshadow's public tree, or Nightshift. Ranking uses the owned rows in the casebook. It is not an Opportunity score, not Expected Entry Value, and not Official Top 5.

## Rule

A repository with `release_blocked: true` is ineligible. The reason string is `release-blocked` and `intervention_priority` is null. Every other owned repository starts at 0. An install-path contradiction adds 3. A public description that does not state the job adds 2. A one-command install adds 1. A demo adds 1. Missing topics add 1. A null flag does not count as false and does not add points. Ties break by repository identity. The field is `intervention_priority` and `priority_meaning` is `actionable-friction`. It orders eligible work. It is not a growth probability, not star potential, and not Expected Entry Value.

## whereToken

`rainhuang0220/whereToken`. Public main `6948f7522a0a98d4f7d2619583e1b717b9363162`. README blob `2e4212dd400678a7bd3be2a947ea1e74680a8602`. Created 2026-08-15. Stars 3, forks 0, at `2026-10-04T10:26:52Z`. Language Go. Topics `cli`, `developer-tools`, `go`, `golang`, `tokens`. Maintainer class solo. Brand low.

Observed surfaces: the README states a job ("Local-first token usage analytics for coding agents."), leads with a dashboard image, documents a curl install script, documents `brew tap rainhuang0220/wheretoken`, and links a GitHub Pages demo on synthetic data. Intervention priority: contradiction 3, one-command 1, demo 1. Description states the job, so the description term is 0. Topics are present, so the topic term is 0. Intervention priority 5. Eligible.

The contradiction, pinned to that commit: in-repo `Formula/wheretoken.rb` blob `b51368437f5af9cd9034310da383cbb1e93ffba4` urls `archive/refs/tags/v0.7.6.tar.gz` (sha256 `384780534bf6051ca546519ac74182d6f6bfb6331677c04299030a18399417bf`) and builds with `go build`. The tap `rainhuang0220/homebrew-wheretoken` installs `v0.7.7` release binaries. The README says release binaries and `brew tap` include the dashboard, while `go install` and `brew --HEAD` build the CLI only.

The local checkout at `/Users/rainhuang/Desktop/whereToken` is behind `origin/main` by 22 commits (HEAD `75cef1ae06da50d2801c7febdc2ac599af22ac4d`). Facts above are from the public commit, not from that dirty-behind checkout. The checkout was not modified.

Prior expectation: "strongest immediate growth candidate" and "useful sharing loop." The first half matches this friction rank. The second half is not something this round measured. A profile card has pointed at the repository since 2026-09-13. An earlier traffic read was not stored, so it is not a baseline and it is not evidence that a sharing loop worked or failed. The public client still denies `/traffic`.

## Foreshadow

`rainhuang0220/foreshadow`. Public main `da5129f580b313cf9cd43332c1524a2d1414968f`. README blob `84daf4d7b241d2b992ba01b3336c3f28c39f041d`. Created 2026-08-24. Stars 0, forks 0. Topics empty. Description: "Foreshadow · 伏笔 — Find what the future has already foreshadowed." The README sentence a stranger meets is poetic. One-command install is present. No demo flag. No install-path conflict.

Intervention priority: description 2, one-command 1, missing topics 1. Intervention priority 4. Eligible, and second. The highest-confidence change would be an explicit job sentence in the GitHub description. That change is `external-write` (`gh repo edit` or the website API). Work Order v1 forbids `external-write`, so the item stays in the backlog and is not exported. Rewriting the README to imitate famous repositories was not selected. Current README text cannot explain a star history this repository does not have.

## Nightshift

`rainhuang0220/nightshift`. Public main `36b2cf1b0082306be79d18e8b5b7ca2daaf922b4`, which is release 0.2.1. Created 2026-10-02. Stars 0, forks 0, topics empty. The description does state the job. There is no one-command install and no demo flag.

Ineligible. Reason: `release-blocked`. The accepted negative result on `engineering/recovery-handoff` at `e27a83a6947d708b5883f808f925688f44220d2e` stands: native macOS containment has not proven a robust whole-task boundary, so fully unattended release remains NOT READY. Acquisition work before that gate is the wrong experiment. Intervention priority is null on purpose, so a missing demo cannot outrank a safety block.

## Chosen target

whereToken. It is the only eligible repository with a measured install-path contradiction, and the friction sum ranks it 5 against Foreshadow's 4. The contradiction is the largest single term (3). The other two points are the one-command install and the demo. Without those two points the same snapshot would rank Foreshadow first and would export no install experiment. Foreshadow's discovery problem remains the second backlog item. Nightshift is not a promotion target.

The rank does not say whereToken will reach 1024 stars. Three stars is below the policy floor of 30 used to reject star-only success criteria. That floor is not a power calculation. 1024 legitimate stars remains a portfolio milestone. It is not this experiment's success criterion.

The file change stays inside whereToken. The tap repository is a different git identity, so editing it would be `external-write`. The no-release resolution is to point `Formula/wheretoken.rb` at `refs/tags/v0.7.7.tar.gz`, which is the version the tap already installs, and to make `README.md` name that same version as the one primary install. Agreement of those surfaces is a treatment check. It can be verified immediately. Stars and clones are not that check, and passing it does not create an adoption result.

## Ranked backlog

1. `gx-single-install-path-v1` on `rainhuang0220/whereToken`. Exportable treatment. State `TREATMENT_READY`. Evidence strength `HYPOTHESIS`. Implementation check `install_path_agreement`. No outcome window. See the plan JSON.
2. `gx-explicit-header-v1` on `rainhuang0220/foreshadow`. Not exportable. Reason `external-write`. Evidence strength `HYPOTHESIS`. Success would be a GitHub description that states the job in language a stranger reads. Failure is a description that stays poetic or empty. No outcome window. Guardrail: do not solicit stars.
3. `gx-qualified-traffic-v1` on `rainhuang0220/whereToken`. Not exportable. State `INSUFFICIENT_BASELINE`. Outcome metric `unique_visitors`. This is the adoption question, and it is not the work order.
3. No experiment for `rainhuang0220/nightshift`. Evidence strength `UNKNOWN`. Reason `release-blocked`.

Rejected as the first experiment: moving a profile README link (the profile repository is outside this portfolio, and the card has been live while unique views stayed low), and adding `CONTRIBUTING.md` because other successful repositories have one. Neither is the measured contradiction, and the second is a cargo-cult copy.
