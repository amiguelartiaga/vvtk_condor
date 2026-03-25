# vvtk_condor

Simplified HTCondor job submission wrappers.

## Quick Install

```bash
curl -fsSL http://dihana.cps.unizar.es/~cadrete/condor_voz | bash

# Or download and run locally:
bash condor_voz
```

The installer will:
1. Ask for an install directory (default: `~/.local/bin`)
2. Extract all scripts there
3. Offer to add the directory to your `PATH` in `~/.bashrc`
4. Offer to configure HTCondor system paths (`/usr/local/condor/...`)

Pressing Enter on every prompt accepts the defaults and gives you a working setup.

## Usage

```bash
condor my_script.sh                        # GPU job, blocking (default)
condor --noblock my_script.sh arg1 arg2    # GPU job, non-blocking
condor --nogpu my_script.sh                # CPU-only job (500 MB)
condor --nice --local my_script.sh         # Nice GPU job on this machine
condor --help                              # Show all options
```

### Options

| Flag        | Effect                                      | Default |
|-------------|---------------------------------------------|---------|
| `--nogpu`   | No GPU, 500 MB memory (alias: `--cpu`)      | GPU on  |
| `--nice`    | Run as nice user (lower priority)            | off     |
| `--local`   | Pin job to current machine (`$HOSTNAME`)     | off     |
| `--noblock` | Return immediately, don't wait for the job   | block   |

### One-liner wrappers

| Command             | Equivalent                     |
|---------------------|--------------------------------|
| `condor_cpu`        | `condor --nogpu`               |
| `condor_nice`       | `condor --nice`                |
| `condor_local`      | `condor --local`               |
| `condor_cpu_local`  | `condor --nogpu --local`       |
| `condor_nice_local` | `condor --nice --local`        |

### Loop & monitor tools

- `condor_for` — submit an array of indexed jobs
- `condor_list` — submit jobs from a list file
- `condor_joblist` — show running jobs grouped by host

## Tutorial

### 1. Submit a single GPU job with `condor`

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

### 2. Submit an array of jobs with `condor_for`

Create a script that receives a job index as its last argument:

```bash
echo 'import sys
i = sys.argv[1]
print(f"entering job {i}")' > job.py
```

Submit 5 indexed jobs (each receives 0..4 as its last argument):

```bash
condor_for python job.py 5
```

Each job will print `entering job 0`, `entering job 1`, etc.
Check individual outputs:

```bash
cat .condor/python_job.py_5_000.log   # output of job 0
cat .condor/python_job.py_5_001.log   # output of job 1
```

### 3. Submit jobs from a list with `condor_list`

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
chmod +x process.py
```

Submit one job per line in the list:

```bash
condor_list python process.py filelist.txt
```

Each job will print `processing file1`, `processing file2`, etc.
Check individual outputs:

```bash
cat .condor/python_process.py_filelist.txt_000.log   # output for file1
cat .condor/python_process.py_filelist.txt_001.log   # output for file2
```
