# Budget study pilot results (2026-10-31)

Two live runs of the [trusted budget-study workflow](analysis-budget-experiments.md)
on the frozen input in `budget-study-inputs.json`: an advisory review of
agent-dispatcher#48, about 178,000 characters of context and 42,700 input tokens.
Same model (`mimo-v2.6-flash`), endpoint and prompt throughout, thinking on, one
process attempt per condition, random order per run.

| Run | Order |
| --- | --- |
| [41191453699](https://github.com/Abdel-Abdelaal/platform-workflows/actions/runs/41191453699) | 32000-3600, 131072-3600, 131072-600, 32000-600 |
| [41194629246](https://github.com/Abdel-Abdelaal/platform-workflows/actions/runs/41194629246) | 32000-600, 32000-3600, 131072-600, 131072-3600 |

## Outcomes

| Output tokens | Deadline | Run 1 | Run 2 | Valid |
| --- | --- | --- | --- | --- |
| 32000 | 600 s | timed out at 600 s | timed out at 600 s | 0/2 |
| 32000 | 3600 s | valid, 604 s, 31,840 output | budget exhausted at 622 s, 32,000 output (`length`) | 1/2 |
| 131072 | 600 s | timed out at 600 s | valid, 475 s, 20,359 output | 1/2 |
| 131072 | 3600 s | valid, 847 s, 40,181 output | valid, 758 s, 37,640 output | 2/2 |

Reasoning made up 97–99% of output tokens in every call that reported usage.
Valid calls used between 20,000 and 40,000 output tokens and took 475–847 s.
Both of today's production limits (32,000-token client cap, 600 s per attempt)
fall inside that range, so each one alone stops roughly half the calls on an input
this size. That matches the repeated `CompletionBudgetExhaustedError` seen in real
advisory reviews, for example on platform-workflows#99.

No condition was stopped by the early-refusal rule, and all eight conditions were
attempted. The artifacts of both runs lack their signature bundle (fixed in #101
for later runs); their summaries and hashes are in the run artifacts.

## Correctness (adjudicated by Claude, not independent of the operator)

Every comment in the four valid analyses was checked against the reviewed code at
`b21f227`:

| Run | Profile | Comments | Valid |
| --- | --- | --- | --- |
| 1 | 32000-3600 | 3 | 3 |
| 1 | 131072-3600 | 5 | 4 (one claimed an unreachable `exit 0` + `timed_out` state) |
| 2 | 131072-600 | 4 | 4 |
| 2 | 131072-3600 | 6 | 6 |

Every valid analysis found the untested CI-repair timeout exclusion, which was
fixed in agent-dispatcher#54. Other confirmed findings: the warning-clearing
comment overstated what happens, `result.exhausted` is unreachable in the
timeout helper, the turn-cap escalation loop captures `before` once per step, and
three near-duplicate test doubles.

## What this does and doesn't show

It shows that on this one input the larger output budget and the longer deadline
each matter, and that 131072 / 3600 s was the only condition that succeeded both
times. With two repetitions it is a pilot. It makes no claim for other inputs,
thinking-off modes or other models, and no quality or parity claim.

Recommendation: give thinking-enabled advisory review a 131072-token output cap
and a deadline of at least 900 s per attempt (the slowest valid call took 847 s),
with the job timeout sized to match, in a separate reviewed change. Until then,
large reviews will keep running out of budget.
