# Changelog

## [1.11.0](https://github.com/Abdel-Abdelaal/platform-workflows/compare/v1.10.0...v1.11.0) (2026-10-30)


### Features

* authorize verified autonomous audit intake ([#72](https://github.com/Abdel-Abdelaal/platform-workflows/issues/72)) ([9e5f6c8](https://github.com/Abdel-Abdelaal/platform-workflows/commit/9e5f6c8178286b827371b2b0e12a13cf06f01b82))
* prepare bounded analysis budget experiments ([#85](https://github.com/Abdel-Abdelaal/platform-workflows/issues/85)) ([f449941](https://github.com/Abdel-Abdelaal/platform-workflows/commit/f449941ab96fd56e6443d0fbc14a947b89c9b032))


### Bug Fixes

* activate reviewed source-context credential redaction ([#87](https://github.com/Abdel-Abdelaal/platform-workflows/issues/87)) ([5f38dac](https://github.com/Abdel-Abdelaal/platform-workflows/commit/5f38daccd8b114293bd486da44f9c9e31e4feb30))
* avoid auxiliary model requests for analysis session titles ([#84](https://github.com/Abdel-Abdelaal/platform-workflows/issues/84)) ([5cf2a08](https://github.com/Abdel-Abdelaal/platform-workflows/commit/5cf2a08453dd5d8a2924e203b8e195e6368969bc))
* distinguish quoted injection evidence from unsafe verdicts ([#66](https://github.com/Abdel-Abdelaal/platform-workflows/issues/66)) ([1505f5b](https://github.com/Abdel-Abdelaal/platform-workflows/commit/1505f5b4695fdf457fa6e58827406daf7db42c5c))
* include telemetry identities in generated releases ([#89](https://github.com/Abdel-Abdelaal/platform-workflows/issues/89)) ([7b14982](https://github.com/Abdel-Abdelaal/platform-workflows/commit/7b1498268556bdf5e415c87ddb452c3032aecee8))
* make analysis retries follow completion evidence ([#78](https://github.com/Abdel-Abdelaal/platform-workflows/issues/78)) ([930b336](https://github.com/Abdel-Abdelaal/platform-workflows/commit/930b3361ee26aec1b79572f6bed05762874542ba))
* preserve omitted agent payloads and privacy metadata ([#65](https://github.com/Abdel-Abdelaal/platform-workflows/issues/65)) ([1cc5bda](https://github.com/Abdel-Abdelaal/platform-workflows/commit/1cc5bda594cff73aab3f10a51d3c9a49463fec58))
* provision approved maintenance credentials during public enrollment ([#90](https://github.com/Abdel-Abdelaal/platform-workflows/issues/90)) ([ae5ea0a](https://github.com/Abdel-Abdelaal/platform-workflows/commit/ae5ea0a2b38a944d19872bc8c398994c9b058749))
* redact source credentials echoed without assignment context ([#86](https://github.com/Abdel-Abdelaal/platform-workflows/issues/86)) ([7bfc382](https://github.com/Abdel-Abdelaal/platform-workflows/commit/7bfc382b08ab8c5cf0a38362f5cead0954ec69be))

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
