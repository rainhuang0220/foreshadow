# Engineering opportunity intelligence

Foreshadow retains observations and turns justified opportunities into reviewable engineering tasks.

## Language

**Observation**: A measured fact at its actual capture time, tied to one repository and source. _Avoid_: prediction, confidence.

**Evidence**: An observation-backed assertion or explicitly labeled inference, with lineage and expiration. _Avoid_: raw score, invented history.

**Opportunity**: A candidate change with rationale, evidence, confidence and intended acceptance conditions. _Avoid_: execution attempt.

**Validated opportunity**: An immutable decision snapshot that passed provenance, freshness and actionability checks. _Avoid_: approved submission.

**Work order**: A generic versioned engineering task exported from a validated opportunity. _Avoid_: executor job, private strategy payload.

**Observation span**: The actual calendar interval covered by measured points. Seven samples are a seven-day window only when the dates cover exactly seven days.

**Legacy contribution**: The existing Board/Gate workflow kept during migration; its execution ownership is outside the new decision core.

**Growth study**: A provenance-preserving reading of comparable public repositories about adoption patterns. It is not a contribution opportunity.
_Avoid_: star predictor, opportunity score

**Growth hypothesis**: A labeled claim that a mechanism might matter for one owned repository, kept separate from observed facts and from causes.
_Avoid_: causal claim, correlation treated as a cause

**Transferability**: A judgment of whether a source case's mechanism can be reproduced on an owned repository, including brand and team class.
_Avoid_: copy the winner

**Growth experiment plan**: A bounded change on one owned repository. A treatment check says whether the change landed. An outcome window says whether a later behavior changed.
_Avoid_: growth advice, marketing campaign

**Treatment check**: An immediate test that the requested files or settings match. Passing it means the change landed.
_Avoid_: adoption result, experiment result

**Outcome measurement**: A comparison of stored observations before and after an intervention, using calendar dates. It is not a cause.
_Avoid_: predicted stars, a file assertion with a waiting period

**Intervention priority**: A rank of actionable friction on owned repositories. It chooses what to try next.
_Avoid_: growth probability, star potential, expected entry value

**Owner traffic observation**: A dated, owner-only count of views, visitors, clones, cloners, referrers, or paths. Missing days stay missing.
_Avoid_: public star snapshot, a token stored in the database

**Growth outcome**: The later measurement of an outcome window. It does not exist until stored observations cover real elapsed days.
_Avoid_: predicted stars
