# vvtk_condor

Simplified HTCondor job submission wrappers.

For a general overview of the available clusters and the common HTCondor workflow,
see [README.md](README.md).

## Quick Install

This README documents the default `voz` setup. For the `hermes2` variant, see
`README_hermes.md`.

```bash
curl -fsSL http://dihana.cps.unizar.es/~cadrete/condor_voz | bash

# Or download and run locally:
bash condor_voz
```

The installer will:
1. Ask for an install directory (default: `~/.local/bin`)
2. Extract the core scripts there (`condor`, `condor_for`, `condor_list`, `condor_joblist`, `condor_reserve`)
3. Offer to add the directory to your `PATH` in `~/.bashrc`
4. Offer to add convenience aliases such as `condor_cpu` and `condor_nice` to `~/.bashrc`
5. Offer to configure HTCondor system paths (`/usr/local/condor/...`)

Pressing Enter on every prompt accepts the defaults and gives you a working setup.

## Building installers

Each package folder has its own standalone builder script. For the current `voz` tools, run:

```bash
bash src/voz/build_installer.sh
bash src/hermes2/build_installer.sh
```

## Usage

```bash
condor my_script.sh                        # GPU job, blocking (default)
condor --noblock my_script.sh arg1 arg2    # GPU job, non-blocking
condor --nodate my_script.sh               # Reuse legacy fixed log names
condor --cpu my_script.sh                  # CPU-only job
condor --prio my_script.sh                 # High-priority GPU job
condor --nice my_script.sh                 # Nice GPU job on any machine
condor --nice --local my_script.sh         # Nice GPU job on this machine
condor_reserve --gpu 2 1h                  # Reserve 2 local GPUs for 1 hour
condor --help                              # Show all options
```

### Options

| Flag        | Effect                                      | Default |
|-------------|---------------------------------------------|---------|
| `--cpu`     | No GPU (alias: `--gpu 0`)                  | GPU on  |
| `--nodate`  | Keep legacy `.condor` names without date    | dated   |
| `--prio`    | Request high-priority scheduling            | off     |
| `--nice`    | Run as nice user (lower priority)           | off     |
| `--local`   | Pin job to current machine (`$HOSTNAME`)    | off     |
| `--noblock` | Return immediately, don't wait for the job  | block   |

### Optional Aliases

The installer can append these aliases to `~/.bashrc`:

| Command             | Equivalent                     |
|---------------------|--------------------------------|
| `condor_cpu`        | `condor --cpu`                 |
| `condor_nice`       | `condor --nice`                |
| `condor_local`      | `condor --local`               |
| `condor_cpu_local`  | `condor --cpu --local`         |
| `condor_nice_local` | `condor --nice --local`        |

### Loop & monitor tools

- `condor_for` — submit an array of indexed jobs
- `condor_list` — submit jobs from a list file
- `condor_joblist` — show running jobs grouped by host, optionally with `--color 1`
- `condor_reserve` — reserve one or more GPUs on the current machine

All submit wrappers append a timestamp to `.condor` file names by default. Use
`--nodate` when you want the old fixed names instead.

## Tutorial

### 1. Submit a single GPU job with `condor`

```bash
rm -rf .condor/
```

Create a small Python script that uses the GPU:

```bash
echo 'import torch
x = torch.randn(5).to("cuda")
print(x)' > gpu_test.py
```

Submit it:

```bash
condor python gpu_test.py
```

This will block until the job finishes and print the output. You can also run it
on this machine only:

```bash
condor --local python gpu_test.py
```
You can check the job status in another terminal:

```bash
condor_joblist
```



For a more informative python script:
```bash
cat > gpu_test_info.py <<'EOF'
import torch
import os, socket, time
print(f"Running on {socket.gethostname()}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA DEVICE: {os.getenv('CUDA_VISIBLE_DEVICES', 'all')}")
x = torch.randn(5).to("cuda")
print(x)
time.sleep(60)
EOF
```

The default dated log names let you submit the same script more than once without
any `.condor` file clashes.

And you can check again now non blocking:
```bash
condor --noblock python gpu_test_info.py
condor --noblock python gpu_test_info.py
condor --noblock python gpu_test_info.py
condor --noblock python gpu_test_info.py
```
You can check the job status in this terminal since we used `--noblock`:
```
condor_joblist
```

The output can be read from the log file:

```bash
cat .condor/python_gpu_test_info.py_*.log
```

Lets try nice GPU jobs as well:

```bash
condor --nice --noblock python gpu_test_info.py
condor --nice --noblock python gpu_test_info.py
condor --nice --noblock python gpu_test_info.py
```

You can check the job status in this terminal since we used `--noblock`:
```bash
condor_joblist
```

We add a non nice job to the queue to see the difference:

```bash
condor --noblock python gpu_test_info.py
```

Check the job list again, in a few seconds job4 should evict one of the nice jobs:

```bash
condor_joblist
```

### 2. Compare nice jobs with a high-priority job

```bash
rm -rf .condor/
```

This example uses `sleep` directly so you can inspect the queue behavior without
needing a separate script.

Launch three long nice jobs:

```bash
condor --nice --noblock sleep 1h
condor --nice --noblock sleep 1h
condor --nice --noblock sleep 1h
```

Check the queue:

```bash
condor_joblist
```

Now submit one short high-priority job, without `--nice`:

```bash
condor --prio --noblock sleep 10s
```

Check the queue again:

```bash
condor_joblist
```

This is a quick way to compare how nice jobs and high-priority jobs appear in the
queue on `voz`.


### 3. Reserve two local GPUs

```bash
rm -rf .condor/
```

Use `condor_reserve` to keep GPUs busy on the current machine with sleep jobs.
This is useful when you want to hold local GPUs for a short interactive session.

```bash
condor_reserve --gpu 2 1h
```

Check the reservation jobs in the queue:

```bash
condor_joblist
```

The reservation jobs are pinned to the local host and one queued job is submitted
per requested GPU.

### 4. Submit an array of jobs with `condor_for`

```bash
rm -rf .condor/
```

Create a script that receives a job index as its last argument:

```bash
echo 'import sys
i = int(sys.argv[1])
print(f"entering job {i+1}")' > job.py
```

Submit 5 indexed jobs (each receives 0..4 as its last argument):

```bash
condor_for --cpu python job.py 5
```

Each job will print `entering job 1/5`, `entering job 2/5`, etc.
Check individual outputs:

```bash
cat .condor/python_job.py_5_*.log
```

### 5. Submit jobs from a list with `condor_list`

```bash
rm -rf .condor/
```

Create a list of files to process:

```bash
echo 'file1
file2
file3' > filelist.txt
```

Create a script that processes each file passed as its last argument:

```bash
echo 'import sys
f = sys.argv[1]
print(f"processing {f}")' > process.py
```

Submit one job per line in the list:

```bash
condor_list --cpu python process.py filelist.txt
```

Each job will print `processing file1`, `processing file2`, etc.
Check individual outputs:

```bash
cat .condor/python_process.py_filelist.txt_*.log
```

### 6. Useful standard HTCondor commands

These commands come from HTCondor itself and are useful when inspecting or
managing jobs outside the wrapper scripts.

```bash
condor_q
```

Show the current queue for all visible jobs.

```bash
condor_rm jobid
```

Remove one job from the queue using its job id.

```bash
condor_rm username
```

Remove all queued jobs owned by `username`.

```bash
condor_rm -all
```

Remove all jobs from the queue.

```bash
condor_hold jobid
```

Put one job on hold so it stops trying to run until released.

```bash
condor_release jobid
```

Release a held job so it can return to the queue.

```bash
condor_q jobid -better
```

Explain why a specific job is not matching or starting on available machines.

```bash
condor_q jobid -hold
```

Show the hold reason for a specific job.

```bash
condor_q jobid -long
```

Print the full ClassAd for a job with all of its attributes.

### 7. Advanced: configure defaults with `condor.cfg`

If a `condor.cfg` file is present in the current directory, `condor` copies that
file into the submit description and then appends the executable, arguments,
output, error, log, and `queue` lines automatically.

That means you can keep your submission defaults in `condor.cfg` and still run
the job with the usual command:

```bash
condor python gpu_test_info.py
```

Example 1: basic GPU job with explicit resources.

```bash
cat > condor.cfg <<'EOF'
universe              = vanilla
notification          = Never
getenv                = True
request_cpus          = 1
request_gpus          = 1
request_memory        = 100
should_transfer_files = no
EOF

condor python gpu_test_info.py
```

Example 2: same job, but submitted as a nice user.

```bash
cat > condor.cfg <<'EOF'
universe              = vanilla
notification          = Never
nice_user             = True
getenv                = True
request_cpus          = 1
request_gpus          = 1
request_memory        = 100
should_transfer_files = no
EOF

condor python gpu_test_info.py
```

Example 3: nice GPU job pinned to one specific machine.

```bash
cat > condor.cfg <<'EOF'
universe              = vanilla
notification          = Never
nice_user             = True
getenv                = True
request_cpus          = 1
request_gpus          = 1
request_memory        = 100
should_transfer_files = no
requirements = ( TARGET.Machine == "vivoidenty02.intra.unizar.es" )
EOF

condor python gpu_test_info.py
```

When you no longer want those defaults, remove or edit the local `condor.cfg`
before the next submission.
