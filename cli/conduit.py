#!/usr/bin/env python3
import os
import sys
import subprocess
import click
import httpx

SERVER = os.environ.get("CONDUIT_SERVER", "http://localhost:2006")


def api(method: str, path: str, **kwargs):
    url = f"{SERVER}{path}"
    try:
        resp = httpx.request(method, url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        click.echo(f"Error: cannot connect to conduit server at {SERVER}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error {e.response.status_code}: {e.response.text}", err=True)
        sys.exit(1)


@click.group()
def cli():
    """conduit — remote GPU job runner"""


def _git_push():
    try:
        result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("[conduit] Pushed local changes to remote.")
        else:
            click.echo(f"[conduit] Warning: git push failed:\n{result.stderr.strip()}", err=True)
    except FileNotFoundError:
        pass  # git not available or not in a repo


def _git_pull():
    try:
        result = subprocess.run(["git", "pull"], capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(f"[conduit] Pulled remote changes:\n{result.stdout.strip()}")
        else:
            click.echo(f"[conduit] Warning: git pull failed:\n{result.stderr.strip()}", err=True)
    except FileNotFoundError:
        pass


@cli.command("run")
@click.argument("command", nargs=-1, required=True)
@click.option("--repo", default=None, help="Git repo URL to clone/pull before running")
@click.option("--name", default=None, help="Human-readable job name")
@click.option("--dir", "working_dir", default=None, help="Working directory on the server")
@click.option("--env", "-e", multiple=True, metavar="KEY=VALUE", help="Extra env vars (repeatable)")
def run_job(command, repo, name, working_dir, env):
    """Submit a job: conduit run <command> [options]"""
    cmd_str = " ".join(command)
    job_name = name or cmd_str[:60]
    if repo:
        _git_push()

    env_dict = {}
    for item in env:
        if "=" not in item:
            click.echo(f"Invalid env var (expected KEY=VALUE): {item}", err=True)
            sys.exit(1)
        k, v = item.split("=", 1)
        env_dict[k] = v

    body = {
        "name": job_name,
        "command": cmd_str,
        "git_repo": repo,
        "working_dir": working_dir,
        "env": env_dict or None,
    }
    result = api("POST", "/jobs", json=body)
    click.echo(f"Job submitted: {result['id']}")
    click.echo(f"Status: {result['status']}")
    click.echo(f"Name:   {result['name']}")


@cli.command("jobs")
def list_jobs():
    """List all jobs"""
    jobs = api("GET", "/jobs")
    if not jobs:
        click.echo("No jobs.")
        return
    fmt = "{:<38}  {:<30}  {:<10}  {}"
    click.echo(fmt.format("ID", "NAME", "STATUS", "START_TIME"))
    click.echo("-" * 95)
    for j in jobs:
        click.echo(fmt.format(j["id"], j["name"][:30], j["status"], j["start_time"]))


@cli.command("logs")
@click.argument("job_id")
@click.option("--lines", default=50, show_default=True, help="Number of tail lines to show")
def logs(job_id, lines):
    """Tail log output for a job"""
    result = api("GET", f"/jobs/{job_id}/output", params={"lines": lines})
    output = result.get("output", "")
    if output:
        click.echo(output, nl=False)
    else:
        click.echo("(no output yet)")


@cli.command("status")
@click.argument("job_id")
def status(job_id):
    """Get full details for a job"""
    j = api("GET", f"/jobs/{job_id}")
    for k, v in j.items():
        click.echo(f"{k:<15} {v}")
    if j.get("status") in ("done", "failed") and j.get("files_updated"):
        click.echo("\n[conduit] Remote pushed changes. Pulling...")
        _git_pull()


@cli.command("write")
@click.argument("local_file", type=click.Path(exists=True))
@click.argument("remote_path")
def write_file(local_file, remote_path):
    """Write a local file to the remote machine: conduit write .env C:/projects/myrepo/.env"""
    with open(local_file, "r") as f:
        content = f.read()
    result = api("POST", "/files", json={"path": remote_path, "content": content})
    click.echo(f"Written to {result['path']}")


@cli.command("kill")
@click.argument("job_id")
def kill(job_id):
    """Kill a running job"""
    j = api("DELETE", f"/jobs/{job_id}")
    click.echo(f"Job {j['id']} status: {j['status']}")


if __name__ == "__main__":
    cli()
