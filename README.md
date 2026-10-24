# platform-workflows

Shared GitHub Actions workflows for my repositories. Each service repo calls these
instead of copying CI logic around, so a fix or a new check lands everywhere at once.

This is the "golden path" pattern: a platform team owns how code gets checked and
shipped, and product repos opt in with a few lines of YAML.

## Workflows

| Workflow | What it checks | Called with |
|---|---|---|
| [`pr-title.yml`](.github/workflows/pr-title.yml) | PR title follows [Conventional Commits](https://www.conventionalcommits.org/) | `pull_request` |

## Usage

```yaml
# .github/workflows/pr.yml in a service repo
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

permissions: {}

jobs:
  pr-title:
    uses: Abdel-Abdelaal/platform-workflows/.github/workflows/pr-title.yml@v1
    permissions:
      pull-requests: read
```

## Versioning

Releases are tagged `vX.Y.Z`. The major tag (`v1`) moves to the latest compatible
release, so callers get fixes without editing their workflows. Breaking changes get
a new major tag.
