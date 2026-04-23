# vvtk_condor

Simple shell wrappers around HTCondor for the available VVTK clusters.

## What HTCondor does here

HTCondor is the scheduler that places your jobs on available cluster machines.
In this repository, the wrapper scripts hide most of the submit-file boilerplate so
you can launch jobs with short commands such as `condor`, `condor_for`, and
`condor_list`.

In practice, the workflow is:

1. Prepare a command or script to run.
2. Submit it to the cluster with one of the wrappers.
3. Check the queue with `condor_joblist`.
4. Read the generated logs under `.condor/`.

The wrappers are designed for interactive cluster use:

- Blocking or non-blocking submissions.
- GPU or CPU jobs, depending on the cluster.
- Nice jobs for lower-priority background work.
- High-priority or local-only jobs where supported.
- Timestamped `.condor` files by default, with `--nodate` for legacy fixed names.

## Available clusters

| Cluster | Documentation | Notes |
|---------|---------------|-------|
| `voz` | [README_voz.md](README_voz.md) | Default setup. Supports GPU/CPU jobs, `--local`, `--prio`, and `condor_reserve` for local GPU reservations. |
| `hermes2` | [README_hermes.md](README_hermes.md) | Simpler variant. Supports the core submission commands but not `--local` or `condor_reserve`. |

## Main commands

These names are shared by the cluster-specific installers:

- `condor` submits one job.
- `condor_for` submits an indexed batch of jobs.
- `condor_list` submits one job per line in an input list.
- `condor_joblist` shows current jobs grouped by host.
- `condor_reserve` reserves local GPUs with sleep jobs on `voz`.

## Pick the cluster README

Use the README that matches the cluster where you work:

- [README_voz.md](README_voz.md) for the default `voz` environment and the most complete feature set.
- [README_hermes.md](README_hermes.md) for the `hermes2` variant.

Each cluster README contains install instructions, usage flags, and runnable examples.
