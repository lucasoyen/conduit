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
# Uvicorn running on http://0.0.0.0:2006
```

### Auto-start on login and wake from sleep (Task Scheduler)

Run as admin. Step 1 — paste the entire block to define the task XML:

```powershell
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=107]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>C:\path\to\conduit\server\.venv\Scripts\python.exe</Command>
      <Arguments>C:\path\to\conduit\server\main.py</Arguments>
      <WorkingDirectory>C:\path\to\conduit\server</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
```

Step 2 — register it:
```powershell
Register-ScheduledTask -TaskName "conduit-server" -Xml $xml
```

Step 3 — start immediately without rebooting:
```powershell
Start-ScheduledTask -TaskName "conduit-server"
```

To remove it:
```powershell
Unregister-ScheduledTask -TaskName "conduit-server" -Confirm:$false
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
export CONDUIT_SERVER="http://<tailscale-ip>:2006"
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
  -e CONDUIT_SERVER=http://<tailscale-ip>:2006
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

# Write a file to the remote machine (e.g. push a .env with secrets)
conduit write .env "C:/Users/lucas/personal-projects/myrepo/.env"
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
| `write_file(path, content)` | Write a file on the remote machine |

### Direct HTTP

```bash
# Submit
curl -X POST http://<server>:2006/jobs \
  -H "Content-Type: application/json" \
  -d '{"name":"test","command":"nvidia-smi"}'

# List
curl http://<server>:2006/jobs

# Output
curl "http://<server>:2006/jobs/<id>/output?lines=50"

# Kill
curl -X DELETE http://<server>:2006/jobs/<id>

# Write a file
curl -X POST http://<server>:2006/files \
  -H "Content-Type: application/json" \
  -d '{"path":"C:/Users/lucas/personal-projects/myrepo/.env","content":"API_KEY=xxx\n"}'
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
| `CONDUIT_SERVER` | Laptop | Job server URL (default: `http://localhost:2006`) |
