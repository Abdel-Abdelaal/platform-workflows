# Immutable PR-Agent trial runtime

The upstream GitHub Action at reviewed source commit
`8e5a9295973b24af4b70cafd0b660a230811ef9e` builds from the mutable
`pragent/pr-agent:github_action` tag. Pinning its action source therefore does not
identify the executed image. This adapter pins the published 0.47.0 manifest digest
and selects the same upstream GitHub runner entrypoint explicitly.

Docker Hub reports publication on 2026-10-02, satisfying the fourteen-day cooldown
on 2026-10-25. The manifest digest is
`sha256:7d98954c29289846a08faf00aaea0f1f1375b1676cd8a2ed303e0af07010af7a`.
Its amd64 image digest is
`sha256:94c36d9ae7ccfe331242d551030646bba6c1b1808052e89591ab175d3ab246e4`.
The versioned CLI image contains the upstream package and `/app` Python path;
the adapter overrides only its CLI entrypoint. It adds no packages or model calls.

Upstream source and licensing remain at
[The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent/tree/8e5a9295973b24af4b70cafd0b660a230811ef9e).
This adapter does not relicense the upstream image.

The trial still runs the provider and GitHub token in one process. It has not yet
received the isolated runner's complete telemetry. A reproducible runtime is a
prerequisite for truthful source/version identification, not proof of isolation or
complete observability. Caller activation follows a hosted no-key import test.
