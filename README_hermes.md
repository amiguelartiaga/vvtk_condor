# vvtk_condor for hermes2

This document describes the `hermes2` variant of `vvtk_condor`.
For the general overview, see [README.md](README.md). For the default `voz`
setup and the more complete tutorial examples, see [README_voz.md](README_voz.md).

## Quick Install

```bash
curl -fsSL http://dihana.cps.unizar.es/~cadrete/condor_hermes2 | bash

# Or download and run locally:
bash condor_hermes2
```

The installer will:
1. Ask for an install directory (default: `~/.local/bin`)
2. Extract the core scripts there (`condor`, `condor_for`, `condor_list`, `condor_joblist`)
3. Offer to add the directory to your `PATH` in `~/.bashrc`
4. Offer to add convenience aliases such as `condor_cpu` and `condor_nice` to `~/.bashrc`
5. Offer to configure HTCondor system paths (`/usr/local/condor/...`)

Pressing Enter on every prompt accepts the defaults and gives you a working setup.

## Building installers

```bash
bash src/hermes2/build_installer.sh
```

## Usage

```bash
condor my_script.sh                        # GPU job, blocking (default)
condor --noblock my_script.sh arg1 arg2    # GPU job, non-blocking
condor --nodate my_script.sh               # Reuse legacy fixed log names
condor --cpu my_script.sh                  # CPU-only job (500 MB)
condor --nice my_script.sh                 # Nice GPU job
condor --help                              # Show all options
```

### Options

| Flag        | Effect                                      | Default |
|-------------|---------------------------------------------|---------|
| `--cpu`     | No GPU                                     | GPU on  |
| `--nodate`  | Keep legacy `.condor` names without date    | dated   |
| `--nice`    | Run as nice user (lower priority)           | off     |
| `--autoenv` | Auto-wrap `python` in the active env        | off     |
| `--noblock` | Return immediately, don't wait for the job  | block   |

### Optional Aliases

The installer can append these aliases to `~/.bashrc`:

| Command       | Equivalent        |
|---------------|-------------------|
| `condor_cpu`  | `condor --cpu`    |
| `condor_nice` | `condor --nice`   |

All submit wrappers append a timestamp to `.condor` file names by default. Use
`--nodate` when you want the old fixed names instead.

`condor_joblist --color 1` highlights your jobs in red. The default is `--color 0`.

## Tutorial

The workflow is the same as in `voz`, but `hermes2` does not support `--local`
or any `*_local` helper.

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

You can check the job status in another terminal:

```bash
condor_joblist
```

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

print(pyfiglet.figlet_format("CONDOR OK"))
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
```bash
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





### 2. Submit an array of jobs with `condor_for`

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

### 3. Submit jobs from a list with `condor_list`

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

### 4. Useful standard HTCondor commands

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

### 5. Advanced: configure defaults with `condor.cfg`

If a `condor.cfg` file is present in the current directory, `condor` copies that
file into the submit description and then appends the executable, arguments,
output, error, log, and `queue` lines automatically.

On `hermes2`, GPU jobs are usually requested by adding
`+Architecture="GPU3090"` to the submit configuration.

You can then run the job with the same command each time:

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
request_memory        = 100
+Architecture         = "GPU3090"
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
request_memory        = 100
+Architecture         = "GPU3090"
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
request_memory        = 100
+Architecture         = "GPU3090"
should_transfer_files = no
requirements = ( TARGET.Machine == "vivoidenty02.intra.unizar.es" )
EOF

condor python gpu_test_info.py
```

When you no longer want those defaults, remove or edit the local `condor.cfg`
before the next submission.