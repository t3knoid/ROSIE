# ROSIE Documentation

ROSIE (Root-cause Observation, SRE Incident Examiner) is a documentation-aware operations assistant. It answers questions from your indexed documentation and runbooks, shows its sources, finds runbook gaps, and drafts runbooks for review. Version 0.1 is documentation-only: it never connects to or changes infrastructure.

To install and start ROSIE, follow the [quick start in the repository README](../../README.md).

## Using and Running ROSIE

- [Configuration](configuration.md): every setting, its default, and what to restart after changing it.
- [Source sync](operations/source-sync.md): when documentation is synced, why chat can be locked, and the optional scheduled sync.
- [Troubleshooting](operations/troubleshooting.md): common problems and where to look.
- [GPU acceleration](operations/gpu-acceleration.md): NVIDIA setup, VRAM tuning, and response speed, using a Tesla P4 as the example.
- [Tesla P4 thermal controller](operations/p4-thermal-controller.md): the optional host fan controller and hardware status.
- [Runbooks](runbooks.md): gap detection, the runbook model, the authoring standard, and export and publishing.
- **API reference:** generated from the code and served by ROSIE at `http://localhost:8001/docs`.

## Understanding ROSIE

- [Overview](overview.md): what ROSIE does, its principles, and its investigation method.
- [Architecture](architecture.md): components, data flows, trust boundaries, and what is not implemented.
- [System prompt](system-prompt.md): the prompt ROSIE uses for every answer. Edits take effect immediately.
- [Roadmap](roadmap.md) and [changelog](changelog.md).
- [Lessons learned](lessons-learned.md): findings from building and running ROSIE.

## Developing ROSIE

- [Developer guide](developer-guide.md): local setup, tests, code layout, and change guidelines.
- [Original requirements draft](archive/requirements-v0.1-draft.md): archived design document, kept for history.
