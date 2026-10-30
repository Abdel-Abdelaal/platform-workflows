# Changelog

## [1.11.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.10.0...v1.11.0) (2026-10-30)

### Features

* allow the trusted controller to discover public fleet audits and authorize only
  verified, unchanged proposals under the owner's autonomous intake policy
  ([#72](https://github.com/Abdel-Abdelaal/platform-workflows/pull/72)); model text
  cannot authorize itself or change its own task state

### Bug Fixes

* retain omitted payloads and privacy metadata in agent evidence
  ([#65](https://github.com/Abdel-Abdelaal/platform-workflows/pull/65))
* distinguish quoted injection evidence from unsafe verdicts in red-team scoring
  ([#66](https://github.com/Abdel-Abdelaal/platform-workflows/pull/66))
* classify empty, completion-budget-exhausted analysis explicitly and provide
  bounded schema feedback for recoverable failures; reasoning settings and
  deadlines remain unchanged
  ([#78](https://github.com/Abdel-Abdelaal/platform-workflows/pull/78))
* activate one immutable reviewed tooling revision across AI analysis,
  validation, publication and evidence; test inherited settings and reject drift
  ([#79](https://github.com/Abdel-Abdelaal/platform-workflows/pull/79))

### Rollout and Validation

The reviewed retry source passed 328 tests; the activation has 16 workflow
contract cases covering positive and deliberately broken configurations. Release
checks must pass before tagging. Existing consumers and future enrollment still
need explicit updates to this release's immutable commit; publication alone does
not move their pins. This release does not enable conversation resume or claim
that retry classification improves model correctness. Interrupted-state and
larger-budget experiments are tracked separately.

## [1.10.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.9.1...v1.10.0) (2026-10-26)

### Features

* publish validated weekly audit findings as deduplicated `agent:proposed` tickets,
  with a five-new-ticket cap, closed-issue preservation and signed publication receipts ([#59](https://github.com/Abdel-Abdelaal/platform-workflows/pull/59))
* scan decoded model outputs using the checksum-verified secret scanner before
  retention and validation; activate immutable reviewed tooling and serialize audit publication ([#58](https://github.com/Abdel-Abdelaal/platform-workflows/pull/58), [#60](https://github.com/Abdel-Abdelaal/platform-workflows/pull/60))
* enroll public repositories with scoped installation tokens, missing-only provider
  credentials and immutable starter callers ([#47](https://github.com/Abdel-Abdelaal/platform-workflows/pull/47))
* add bounded controller-attempt schema, public-only scanned sender and hosted
  Sigstore ingestion infrastructure; live producer activation and signed dashboard
  proof are tracked separately and are not implied by this release ([#62](https://github.com/Abdel-Abdelaal/platform-workflows/pull/62))

### Bug Fixes

* support the actual default branch in baseline/stale maintenance and pin the
  PR-Agent runtime by image digest ([#48](https://github.com/Abdel-Abdelaal/platform-workflows/pull/48))
* remove the deprecated Pyink validator ([#57](https://github.com/Abdel-Abdelaal/platform-workflows/pull/57))

### Validation

Real shortlink review and audit runs verified the output scanner, durable signed
records and five proposed tickets. Research master baseline and stale dry-run
prove default-branch handling. Enrollment's hosted scoped-App run verified public
classification and missing-only secret provisioning. Agent execution remains
owner-approved; this release never adds `agent:ready` or approves/merges AI work.

## [1.9.1](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.9.0...v1.9.1) (2026-10-25)


### Bug Fixes

* **lint:** leave prose wording to the handbook ([#54](https://github.com/Abdel-Abdelaal/platform-workflows/issues/54)) ([5648ffe](https://github.com/Abdel-Abdelaal/platform-workflows/commit/5648ffecde4e88131cc0f8b479dff162d87609e8))

## [1.9.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.8.0...v1.9.0) (2026-10-25)


### Features

* detect codeql languages automatically and scan every dependency ecosystem ([#50](https://github.com/Abdel-Abdelaal/platform-workflows/issues/50)) ([c0c8b06](https://github.com/Abdel-Abdelaal/platform-workflows/commit/c0c8b06b49730739386f8b4fadae8962be22f7ae))
* detect repository languages and add multi-language lint and node gates ([#49](https://github.com/Abdel-Abdelaal/platform-workflows/issues/49)) ([7b80587](https://github.com/Abdel-Abdelaal/platform-workflows/commit/7b805870e5dfb8a68efebd6f61bffe9b6f597614))
* retain private AI records with explicit DSSE signatures ([#43](https://github.com/Abdel-Abdelaal/platform-workflows/issues/43)) ([cf3e9b2](https://github.com/Abdel-Abdelaal/platform-workflows/commit/cf3e9b24d603fd8e1fee05d4d062682281825bcb))
* separate public and confidential AI evidence signing ([#45](https://github.com/Abdel-Abdelaal/platform-workflows/issues/45)) ([deb0003](https://github.com/Abdel-Abdelaal/platform-workflows/commit/deb000311a62d38f11fb2f6711093c4b4b1374be))
* sign private AI evidence without public transparency ([#41](https://github.com/Abdel-Abdelaal/platform-workflows/issues/41)) ([2e40313](https://github.com/Abdel-Abdelaal/platform-workflows/commit/2e403132c2885d1bb46f0aea27789aa7c17bd85e))


### Bug Fixes

* **lint:** skip formatter and whole-workspace linters ([#51](https://github.com/Abdel-Abdelaal/platform-workflows/issues/51)) ([2185db4](https://github.com/Abdel-Abdelaal/platform-workflows/commit/2185db43cf5e6c74875ebc8e0b2bb2029f963ab7))
* redact the provider credential before recording AI responses ([#44](https://github.com/Abdel-Abdelaal/platform-workflows/issues/44)) ([5d437ee](https://github.com/Abdel-Abdelaal/platform-workflows/commit/5d437eeae812261a7a05464ac68c71a61caa43f3))

## [1.8.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.7.0...v1.8.0) (2026-10-25)


### Features

* attack the ai reviewer weekly and publish signed results ([#35](https://github.com/Abdel-Abdelaal/platform-workflows/issues/35)) ([94be889](https://github.com/Abdel-Abdelaal/platform-workflows/commit/94be8896829cc93f2da4d7e742d678ce1b6ece4f))
* include fleet languages in bounded AI context ([#39](https://github.com/Abdel-Abdelaal/platform-workflows/issues/39)) ([d79b624](https://github.com/Abdel-Abdelaal/platform-workflows/commit/d79b624f04332d3e4e4eb3ae015089a382cd9bee))


### Bug Fixes

* count only the reviewer's own wording as obeying the blocking attack ([#37](https://github.com/Abdel-Abdelaal/platform-workflows/issues/37)) ([89e8ec2](https://github.com/Abdel-Abdelaal/platform-workflows/commit/89e8ec2a9a18348c539e45dc23fa46e432820c16))
* scan complete AI inputs and honor default branches ([#38](https://github.com/Abdel-Abdelaal/platform-workflows/issues/38)) ([9d6c32f](https://github.com/Abdel-Abdelaal/platform-workflows/commit/9d6c32fa174a589708dc5ce15b5b23a6525cddc9))

## [1.7.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.6.0...v1.7.0) (2026-10-25)


### Features

* capture telemetry evidence for AI runs ([#29](https://github.com/Abdel-Abdelaal/platform-workflows/issues/29)) ([2a7948d](https://github.com/Abdel-Abdelaal/platform-workflows/commit/2a7948d382d514ea223c7f21391df665680db8c0))
* sign and durably archive isolated AI evidence ([#30](https://github.com/Abdel-Abdelaal/platform-workflows/issues/30)) ([2e70632](https://github.com/Abdel-Abdelaal/platform-workflows/commit/2e70632da453ff873e98687b9e58dc6df16c7746))


### Bug Fixes

* bind signed AI evidence to trusted producer artifacts ([700eeec](https://github.com/Abdel-Abdelaal/platform-workflows/commit/700eeec98772931724136eaeafdc0da6bbe5eb8c))
* preserve honest telemetry evidence across failure paths ([#32](https://github.com/Abdel-Abdelaal/platform-workflows/issues/32)) ([a07b377](https://github.com/Abdel-Abdelaal/platform-workflows/commit/a07b3774a5d3f90b15a2dc147077d0f0f71a509f))
