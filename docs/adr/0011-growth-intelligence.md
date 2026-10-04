# Keep growth questions out of the contribution Opportunity

Foreshadow already answers which external repository is worth a contribution. Growth Intelligence answers a different question: given comparable public projects, what bounded experiment is worth trying on one owned repository, how transferable the evidence is, and how the owner will know whether it worked. The two stay separate because a famous repository can be a useful case and a bad contribution target.

Status: accepted

## Decision

The first slice lives in `foreshadow.growth_intel` and the `growth` command group (`study`, `portfolio`, `plan`, `export`). It reads a committed casebook. It does not crawl GitHub at plan time, does not train a model, and does not write a second star-history table. `snapshots` remains the only daily star and fork series. New claims use `OBSERVED`, `CORRELATED`, `HYPOTHESIS`, `QUASI_EXPERIMENTAL`, `EXPERIMENT_RESULT`, or `UNKNOWN`. There is no `CAUSAL` status. A retrospective casebook cannot exceed `HYPOTHESIS` unless a dated event and a matched control share a real calendar window, and a current README blob cannot supply that event.

An exportable plan becomes generic Engineering Work Order v1. Research fields stay in the growth plan. The work order carries the file task, ordinary-language evidence, and the existing action boundary. Nightshift validates and previews that file. It does not learn growth vocabulary, and this slice does not run it.

## Considered options

Broaden `Opportunity` until it means every project decision. Rejected. Contribution ranking, Expected Entry Value, and Official Top 5 would become a growth score by accident.

Rename `pipeline/trainer.py` (`growth_sign_30d` = `delta_stars > 0`) into the product decision. Rejected. That challenger is an offline sign classifier on local snapshots. It is not a model of adoption, maintenance load, or transfer.

Add owner traffic to the existing GitHub client. Rejected for this slice. Public stargazer timestamps returned 404 for third-party repositories. Traffic for an owned repository answered only because the logged-in `gh` credential has `repo` scope. Folding that into `GITHUB_TOKEN` would widen the GET-only client. Traffic stays out of the client and out of the work order.

Store the casebook as new SQLite tables or a vector index. Rejected. Cohort membership, the experiment, and its outcome do not need a second history of stars. The casebook is a versioned JSON document with source URLs, observation times, and commit or blob SHAs.

## Consequences

The portfolio rank is a friction rule, not an Opportunity score. A release-blocked repository is ineligible. Among the rest, an install-path contradiction outranks a weak public description. Stars below 30 cannot be the success metric.

Brand-high cases stay in the casebook as observations and are excluded from the transferable supporting set. A GitHub-owned or Microsoft-owned launch is not a tactic a solo maintainer can copy.

The slice can say "no experiment" and can leave a claim `UNKNOWN`. That is a successful output.

## Attack before building

Are we only rediscovering that big projects are big? The casebook keeps matched controls with the same install tropes and much smaller star stocks. The first experiment does not use star count as its metric.

Are features contaminated by future information? Plan time must be after each row's observation time. A quasi-experimental label requires a dated event. Current README scope cannot explain earlier growth.

Are brand effects dominating? `github/spec-kit`, `microsoft/markitdown`, `astral-sh/uv`, `docling-project/docling`, and `pydantic/pydantic` are marked high brand and are not transfer sources.

Are ages incomparable? Solo Rust CLIs in the casebook are years old. `whereToken` was created on 2026-08-15. Their READMEs are not a template for a repository that is about fifty days old.

Are we confusing README quality with popularity caused elsewhere? Literature opened for this design (Borges and Valente, arXiv:1606.04984 and arXiv:1811.07643; Aggarwal, Hindle, and Stroulia, MSR 2014) treats activity and docs as correlates. The tested documentation direction is popularity attracting later edits. This slice does not promote that correlate to a cause.

Are social spikes being mistaken for code changes? No event study in this slice attributes a star window to a commit.

Are we using today's README to explain historical growth? README blobs are `CURRENT_SNAPSHOT`. The study claim about them is `UNKNOWN`.

Are missing fields becoming zeros? Stars, forks, and mechanism flags stay null when the read failed. Cohort selection drops missing stars instead of filling them.

Are windows real dates? Elapsed days are the difference of observation dates, not the number of samples.

Are we buying attention by making the project harder to maintain? The experiment forbids a release, star solicitation, and extra primary install commands. Stars and clones are guardrails, not success.

Can the experiment be measured? Success is whether `README.md` and `Formula/wheretoken.rb` name the same version and one primary install command. That is a file fact. A star effect is `UNKNOWN`.

Can the tool say it does not know? Yes. Unsupported status strings, including `CAUSAL`, are rejected. A release-blocked repository produces no growth experiment.

## Amendment

`docs/adr/0012-owned-experiment-observations.md` supersedes the measurement sentence above that treats agreement of `README.md` and `Formula/wheretoken.rb` as the experiment result. That agreement is a treatment check. Version strings belong in the casebook discrepancy, not in the generic planner. A file pass does not create `EXPERIMENT_RESULT`.
