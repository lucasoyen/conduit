# conduit

Run Python jobs on a remote GPU/CPU machine from your laptop, with Claude Code integration via MCP.

Submit jobs from the CLI or let Claude Code dispatch them directly — git clone, venv setup, and dependency installation happen automatically on the remote machine.

## How it works

```
laptop                               desktop (GPU machine)
------                               ---------------------
conduit CLI  ──── HTTP (Tailscale) ───► FastAPI server
MCP server ───────────────────────►   clones repo → C:\projects\<repo>
                                       creates .venv, installs deps
                                       runs your command
                                       streams output to logs/
```

## Project structure

```
conduit/
├── server/       # runs on the GPU machine
├── mcp/          # runs on the laptop, plugs into Claude Code
├── cli/          # runs on the laptop
└── logs/         # job output (on the GPU machine)
```

---

## Desktop setup (GPU machine, Windows)

### Prerequisites
- Python 3.10+
- Git
- [Tailscale](https://tailscale.com/download)

### Install

```powershell
cd C:\path\to\conduit\server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Set where repos get cloned (defaults to `~/projects`):

```powershell
$env:CONDUIT_PROJECTS_DIR = "C:\your\preferred\path"
```

### Run

```powershell
python main.py
# Uvicorn running on http://0.0.0.0:8000
```

### Auto-start on login (Task Scheduler)

```powershell
# Run as admin
$action = New-ScheduledTaskAction `
  -Execute "C:\path\to\conduit\server\.venv\Scripts\python.exe" `
  -Argument "C:\path\to\conduit\server\main.py" `
  -WorkingDirectory "C:\path\to\conduit\server"

$trigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask -TaskName "conduit-server" -Action $action -Trigger $trigger -RunLevel Highest
```

Start it immediately without rebooting:
```powershell
Start-ScheduledTask -TaskName "conduit-server"
```

### Recommended machine settings

```powershell
# Prevent sleep
powercfg /change standby-timeout-ac 0

# Enable Ultimate Performance power plan
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61
# Then set it active in Power Options

# Exclude projects dir from Defender (big I/O speedup)
Add-MpPreference -ExclusionPath "C:\your\projects\path"
```

Also in NVIDIA Control Panel → Manage 3D Settings → Power management mode → **Prefer maximum performance**.

---

## Laptop setup

### Prerequisites
- Python 3.10+
- [Tailscale](https://tailscale.com/download) (same account as desktop)
- Claude Code (for MCP integration)

### Set the server URL

Find your desktop's Tailscale IP in the Tailscale app or with `tailscale ip`.

```bash
# Add to ~/.bashrc or ~/.zshrc
export CONDUIT_SERVER="http://<tailscale-ip>:8000"
```

### Install the CLI

```bash
cd path/to/conduit/cli
pip install -r requirements.txt

# Optional: make conduit available globally
pip install --editable .
```

### Add the MCP server to Claude Code

```bash
claude mcp add conduit python /path/to/conduit/mcp/server.py \
  -e CONDUIT_SERVER=http://<tailscale-ip>:8000
```

Install MCP dependencies:

```bash
cd path/to/conduit/mcp
pip install -r requirements.txt
```

---

## Usage

### CLI

```bash
# Run a command (code already on the machine)
conduit run "python train.py --epochs 10"

# Clone a repo and run
conduit run "python train.py" --repo https://github.com/you/project --name "training run 1"

# Pass environment variables
conduit run "python train.py" --repo https://github.com/you/project -e BATCH_SIZE=64 -e LR=0.001

# List jobs
conduit jobs

# Tail output
conduit logs <job-id>
conduit logs <job-id> --lines 100

# Full job details
conduit status <job-id>

# Kill a job
conduit kill <job-id>
```

### Claude Code (MCP)

Once configured, Claude Code can submit and monitor jobs directly:

> "Run train.py on my GPU machine using https://github.com/you/project"

Available MCP tools:
| Tool | Description |
|------|-------------|
| `run_job(command, git_repo?, working_dir?, name?)` | Submit a job |
| `job_status(job_id)` | Status + last 20 lines of output |
| `list_jobs()` | All jobs |
| `job_output(job_id, lines?)` | Full log tail |
| `kill_job(job_id)` | Terminate a job |

### Direct HTTP

```bash
# Submit
curl -X POST http://<server>:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"name":"test","command":"nvidia-smi"}'

# List
curl http://<server>:8000/jobs

# Output
curl "http://<server>:8000/jobs/<id>/output?lines=50"

# Kill
curl -X DELETE http://<server>:8000/jobs/<id>
```

---

## Per-project virtual environments

When a `git_repo` is provided, the server automatically:

1. Clones the repo (or pulls if it exists)
2. Creates a `.venv` inside the repo if one doesn't exist
3. Installs `requirements.txt` or `pyproject.toml` dependencies
4. Runs your command inside that venv

The venv persists between runs. Dependencies are re-installed on every pull so changes to `requirements.txt` are always picked up.

---

## Environment variables

| Variable | Where | Description |
|----------|-------|-------------|
| `CONDUIT_PROJECTS_DIR` | Desktop | Where repos are cloned (default: `~/projects`) |
| `CONDUIT_SERVER` | Laptop | Job server URL (default: `http://localhost:8000`) |
