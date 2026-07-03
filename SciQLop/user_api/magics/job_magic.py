"""Implementation of %job line magic — submit, inspect, list, and cancel
background jobs from a notebook cell (see SciQLop.user_api.jobs)."""
import shlex

from IPython.core.error import UsageError


SUBCOMMANDS = {
    "submit": "Submit a shell command as a detached background job",
    "status": "Show a job's status, exit code, and log tail",
    "list": "List all known jobs and their status (default)",
    "cancel": "Send SIGTERM to a running job",
    "help": "Show this help",
}


def _cmd_submit(rest: str):
    from SciQLop.user_api.jobs import submit_job

    rest = rest.strip()
    name = ""
    if rest.startswith("--name"):
        parts = rest.split(None, 2)
        if len(parts) < 3:
            raise UsageError("Usage: %job submit [--name NAME] <command>")
        name = parts[1]
        rest = parts[2]
    if not rest:
        raise UsageError("Usage: %job submit [--name NAME] <command>")

    job_id = submit_job(rest, name)
    print(f"Submitted job {job_id}: {name or rest}")


def _get_job_id(rest: str, usage: str) -> str:
    parts = shlex.split(rest) if rest.strip() else []
    if not parts:
        raise UsageError(usage)
    return parts[0]


def _cmd_status(rest: str):
    from SciQLop.user_api.jobs import job_status

    job_id = _get_job_id(rest, "Usage: %job status <id>")
    try:
        st = job_status(job_id)
    except KeyError:
        raise UsageError(f"No such job '{job_id}'")

    lines = [
        f"id:           {st['id']}",
        f"name:         {st['name']}",
        f"command:      {st['command']}",
        f"status:       {st['status']}",
        f"submitted_at: {st['submitted_at']}",
        f"finished_at:  {st['finished_at']}",
        f"exit_code:    {st['exit_code']}",
    ]
    print("\n".join(lines))
    if st["log_tail"]:
        print("--- log ---")
        print(st["log_tail"])


def _cmd_list(rest: str):
    from SciQLop.user_api.jobs import list_jobs

    jobs = sorted(list_jobs(), key=lambda j: j["submitted_at"])
    if not jobs:
        print("No jobs.")
        return
    print(f"{'ID':<14}{'NAME':<24}{'STATUS':<10}{'SUBMITTED'}")
    for j in jobs:
        print(f"{j['id']:<14}{j['name'][:22]:<24}{j['status']:<10}{j['submitted_at']}")


def _cmd_cancel(rest: str):
    from SciQLop.user_api.jobs import cancel_job

    job_id = _get_job_id(rest, "Usage: %job cancel <id>")
    try:
        cancel_job(job_id)
    except KeyError:
        raise UsageError(f"No such job '{job_id}'")
    print(f"Cancelled job {job_id}.")


def _cmd_help(rest: str):
    print("Usage: %job <subcommand> [args...]\n")
    print("Subcommands:")
    for name, desc in SUBCOMMANDS.items():
        print(f"  {name:<10} {desc}")


DISPATCH = {
    "submit": _cmd_submit,
    "status": _cmd_status,
    "list": _cmd_list,
    "cancel": _cmd_cancel,
    "help": _cmd_help,
}


def job_magic(line: str):
    """%job [subcommand] [args...]

    Submit, inspect, list, and cancel background jobs (see %job help).

    Subcommands:
      submit [--name NAME] <command>   Submit a shell command
      status <id>                      Show a job's status + log tail
      list                             List all known jobs (default)
      cancel <id>                      Send SIGTERM to a running job
      help                             Show this help
    """
    line = line.strip()
    if not line:
        subcmd, rest = "list", ""
    else:
        parts = line.split(None, 1)
        subcmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

    handler = DISPATCH.get(subcmd)
    if handler is None:
        raise UsageError(f"Unknown subcommand '{subcmd}'. Run %job help")
    handler(rest)
