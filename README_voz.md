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
2. Extract the core scripts there (`condor`, `condor_for`, `condor_list`, `condor_stop`, `condor_joblist`, `condor_reserve`)
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
condor --level 2 my_script.sh              # Medium-priority GPU job
condor --nice --local my_script.sh         # Nice GPU job on this machine
condor_reserve --gpu 2 1h                  # Reserve 2 local GPUs for 1 hour
condor --help                              # Show all options
```

### Options

| Flag        | Effect                                      | Default |
|-------------|---------------------------------------------|---------|
| `--cpu`     | No GPU (alias: `--gpu 0`)                  | GPU on  |
| `--nodate`  | Keep legacy `.condor` names without date    | dated   |
| `--prio`    | Request high-priority scheduling (alias of `--level 3`) | off |
| `--nice`    | Run as nice user (alias of `--level 0`)     | off     |
| `--level N` | Priority level 0..3 (0=nice, 1=normal, 2=Media, 3=Alta) | unset |
| `--local`   | Pin job to current machine (`$HOSTNAME`)    | off     |
| `--autoenv` | Auto-wrap `python` in the active env        | off     |
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
- `condor_stop` — interactively kill jobs from the right submitter host
- `condor_reserve` — reserve one or more GPUs on the current machine

All submit wrappers append a timestamp to `.condor` file names by default. Use
`--nodate` when you want the old fixed names instead.

## Tutorial

### 1. Submit a single GPU job with `condor`

#### Basic blocking submission

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

#### Run Python with a manually activated environment

If your Python code needs an environment to be activated first, submit a small
bash wrapper instead of calling `python` directly.

Step 1. Create a virtual environment:

```bash
python -m venv condortutorial
```

Step 2. Activate the environment:

```bash
source condortutorial/bin/activate
```

Step 3. Install the packages that your job needs:

```bash
pip install pyfiglet
```

Step 4. Create the Python script that you want to run:

```bash
cat > hello.py <<'EOF'
import pyfiglet

print(pyfiglet.figlet_format("OK"))
EOF
```

Step 5. Test the script locally before submitting anything:

```bash
python hello.py
```

Step 6. Create a bash wrapper that activates the environment and then runs the
Python script. Use `#!/bin/bash` as the first line.

```bash
cat > run.sh <<'EOF'
#!/bin/bash
source condortutorial/bin/activate
python hello.py
EOF
```

Step 7. Test the wrapper locally:

```bash
bash run.sh
```

Step 8. Submit the wrapper script through Condor:

```bash
condor bash run.sh
```

Step 9. Check the output in the generated log:

```bash
cat .condor/bash_run.sh_*.log
```

If the environment lives somewhere else, replace the activation line in
`run.sh` with the correct path. For example:

```bash
source ~/venvs/myenv/bin/activate
```

#### Use `--autoenv` instead of writing the wrapper yourself

As a shortcut, when the active shell is already inside a `venv` or Conda
environment you can let `condor` build that wrapper for you with `--autoenv`:

```bash
condor --autoenv python hello.py
```

This detects the active environment, locates its `activate` script via
`which python`, and writes a small `.condor/<job>_activate.sh` wrapper that
sources `activate` and then runs `python` with the given arguments. The job
is submitted using that wrapper, so the cluster execution sees the same
environment as your interactive shell.

#### Submit repeated non-blocking runs

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

#### Compare nice jobs with a regular job

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


### 3. Climb the priority ladder with `--level`

The `--level` argument exposes the four priority tiers of the cluster:

| Level | Meaning                                  | Equivalent flag |
|-------|------------------------------------------|-----------------|
| `0`   | Nice job (lowest priority, evictable)    | `--nice`        |
| `1`   | Normal job (no nice, no prio)            | (default)       |
| `2`   | `+Prioridad = "Media"`                   | —               |
| `3`   | `+Prioridad = "Alta"` (highest)          | `--prio`        |

A higher level evicts running jobs of any lower level. The following walk-through
fills the cluster with two sleeping GPU jobs and then keeps adding new jobs at
increasing levels, checking the queue between submissions to see the evictions.

```bash
rm -rf .condor/
```

#### Step 1. Launch two long-running local GPU jobs at level 0 (nice)

```bash
condor --local --level 0 --noblock sleep 5m
condor --local --level 0 --noblock sleep 5m
```

Check the queue and confirm both nice jobs are running:

```bash
condor_joblist
```

#### Step 2. Add two level 1 jobs (normal) — they should evict both level 0 jobs

```bash
condor --local --level 1 --noblock sleep 5m
condor --local --level 1 --noblock sleep 5m
```

```bash
condor_joblist
```

Wait a few seconds and check again; the two level 1 jobs should displace the
two level 0 jobs back to idle.

#### Step 3. Add two level 2 jobs — they should evict both level 1 jobs

```bash
condor --local --level 2 --noblock sleep 5m
condor --local --level 2 --noblock sleep 5m
```

```bash
condor_joblist
```

#### Step 4. Add two level 3 jobs (`Alta`, equivalent to `--prio`) — they should evict both level 2 jobs

```bash
condor --local --level 3 --noblock sleep 5m
condor --local --level 3 --noblock sleep 5m
```

```bash
condor_joblist
```

At this point the two level 3 jobs are running and the lower-level jobs sit idle
waiting for free GPU slots.

#### Step 5. Same experiment with `condor_for`

Clean up first and reserve the local GPUs again with two array jobs at level 0:

```bash
condor_rm $USER
rm -rf .condor/

condor_for --local --level 0 --noblock sleep 5m 2
condor_joblist
```

Now keep climbing the levels with two jobs per level and watch the evictions:

```bash
condor_for --local --level 1 --noblock sleep 5m 2
condor_joblist

condor_for --local --level 2 --noblock sleep 5m 2
condor_joblist

condor_for --local --level 3 --noblock sleep 5m 2
condor_joblist
```

#### Step 6. Same experiment with `condor_list`

Clean up and prepare a tiny list file:

```bash
condor_rm $USER
rm -rf .condor/

echo '5m
5m' > sleeplist.txt
```

Launch two local GPU sleep jobs at level 0:

```bash
condor_list --local --level 0 --noblock sleep sleeplist.txt
condor_joblist
```

Now add two jobs per level using a two-line list and watch the queue between
submissions:

```bash
echo '5m
5m' > two.txt

condor_list --local --level 1 --noblock sleep two.txt
condor_joblist

condor_list --local --level 2 --noblock sleep two.txt
condor_joblist

condor_list --local --level 3 --noblock sleep two.txt
condor_joblist
```

When you are done, clean the queue:

```bash
condor_rm $USER
```


### 4. Reserve two local GPUs

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

### 5. Submit an array of jobs with `condor_for`

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

### 6. Submit jobs from a list with `condor_list`

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

### 7. Stop jobs from any machine with `condor_stop`

In HTCondor, a job can only be removed (`condor_rm`) from the same schedd
(machine) that submitted it. Forgetting which host you launched a job from is
a very common annoyance.

Every submission made through `condor`, `condor_for` or `condor_list` now drops
a small sidecar file `.condor/<base>._info` that records:

```
JOBID=12345
HOSTNAME=vivoidenty01.intra.unizar.es
IP=155.210.x.x
USER=youruser
EXECUTABLE=/usr/bin/python
ARGUMENTS=gpu_test.py
NJOBS=1
SUBMIT_TIME=2026-05-04 12:34:56
CONFIG=.condor/python_gpu_test.py_..._sub
```

`condor_stop` reads those files in the current directory and uses them to
ssh to the right host and run `condor_rm` for you.

#### Interactive picker

From the directory where you submitted the jobs:

```bash
condor_stop
```

You get a numbered list with one running job per line, like:

```
Running jobs found in .condor/:

   1) 155.210.10.21/vivoidenty01.intra.unizar.es  12345  /usr/bin/sleep 5m
   2) 155.210.10.22/vivoidenty02.intra.unizar.es  12350  /usr/bin/python gpu_test.py

  a) all
  q) quit

Select job to kill [1-2 / a / q]:
```

Type `2` and `condor_stop` will run `ssh vivoidenty02.intra.unizar.es condor_rm 12350`
for you. Type `a` to kill them all.

#### Direct mode

If you already know the cluster id, skip the menu:

```bash
condor_stop 12345        # find host in .condor/*._info, ssh + condor_rm
condor_stop all          # kill every still-running job listed in cwd
```

If the jobid is not found in any local `._info`, `condor_stop` falls back to a
plain `condor_rm` on the local machine.

> Passwordless ssh to the submitter host must work. Otherwise `condor_stop`
> will prompt for a password.

### 8. Useful standard HTCondor commands

These commands come from HTCondor itself and are useful when inspecting or
managing jobs outside the wrapper scripts.

```bash
condor_q
```

Show the current queue for all visible jobs.

```bash
condor_rm jobid
```

Remove one job from the queue using its job id. Run this from the same node
where the submission was sent.

```bash
condor_rm username
```

Remove all queued jobs owned by `username`. Run this from the same node where
the submission was sent.

```bash
condor_rm -all
```

Remove all jobs from the queue. Run this from the same node where the
submission was sent.

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

### 9. Advanced: configure defaults with `condor.cfg`

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
