import os
import subprocess
from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP

SERVER = os.environ.get("CONDUIT_SERVER", "http://localhost:2006")

mcp = FastMCP("conduit")


def _api(method: str, path: str, **kwargs):
    url = f"{SERVER}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()


def _git_push(repo_path: str):
    try:
        subprocess.run(["git", "push"], cwd=repo_path, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git push failed: {e.stderr.decode().strip()}")


def _git_pull(repo_path: str):
    try:
        subprocess.run(["git", "pull"], cwd=repo_path, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git pull failed: {e.stderr.decode().strip()}")


@mcp.tool()
def run_job(
    command: str,
    git_repo: Optional[str] = None,
    working_dir: Optional[str] = None,
    name: Optional[str] = None,
    local_repo_path: Optional[str] = None,
) -> dict:
    """Submit a job to the remote GPU server. Returns the new job's ID and initial status.

    If local_repo_path is provided and git_repo is set, pushes local changes before submitting
    so the server pulls the latest code.

    After submitting, you can check in on the job at any time using job_status(job_id) or
    job_output(job_id). Poll job_status until status is 'done' or 'failed'.
    If files_updated is True when the job finishes, call git pull in local_repo_path.
    """
    if git_repo and local_repo_path:
        _git_push(local_repo_path)

    body = {
        "name": name or command[:60],
        "command": command,
        "git_repo": git_repo,
        "working_dir": working_dir,
    }
    return _api("POST", "/jobs", json=body)


@mcp.tool()
def job_status(job_id: str, local_repo_path: Optional[str] = None) -> dict:
    """Get the current status and recent output (last 20 lines) for a job.

    Poll this at any time to check progress — it is safe to call repeatedly.
    When status is 'done' or 'failed', the job has finished.
    If files_updated is True and local_repo_path is provided, pulls remote changes automatically.
    """
    job = _api("GET", f"/jobs/{job_id}")
    output_result = _api("GET", f"/jobs/{job_id}/output", params={"lines": 20})
    job["recent_output"] = output_result.get("output", "")

    if job.get("status") in ("done", "failed") and job.get("files_updated") and local_repo_path:
        _git_pull(local_repo_path)
        job["pulled"] = True

    return job


@mcp.tool()
def list_jobs() -> list:
    """List all jobs on the remote GPU server with id, name, status, and start time."""
    return _api("GET", "/jobs")


@mcp.tool()
def job_output(job_id: str, lines: int = 100) -> str:
    """Get the last N lines of log output for a job. Safe to call at any time during execution."""
    result = _api("GET", f"/jobs/{job_id}/output", params={"lines": lines})
    return result.get("output", "")


@mcp.tool()
def write_file(path: str, content: str) -> dict:
    """Write a file on the remote machine. Useful for creating .env files with secrets."""
    return _api("POST", "/files", json={"path": path, "content": content})


@mcp.tool()
def kill_job(job_id: str) -> dict:
    """Kill a running job by ID."""
    return _api("DELETE", f"/jobs/{job_id}")


if __name__ == "__main__":
    mcp.run()
