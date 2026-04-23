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
| `--noblock` | Return immediately, don't wait for the job  | block   |

### Optional Aliases

The installer can append these aliases to `~/.bashrc`:

| Command       | Equivalent        |
|---------------|-------------------|
| `condor_cpu`  | `condor --cpu`    |
| `condor_nice` | `condor --nice`   |

All submit wrappers append a timestamp to `.condor` file names by default. Use
`--nodate` when you want the old fixed names instead.

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