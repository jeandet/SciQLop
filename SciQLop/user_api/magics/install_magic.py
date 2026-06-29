"""Implementation of %install line magic — install packages and record them."""
import shlex

from IPython.core.error import UsageError

from SciQLop.user_api.packages import install_packages


def install_magic(line: str):
    """%install <package> [package2 ...]

    Install Python packages into the current workspace using uv and record them
    in the .sciqlop manifest so they persist across restarts and venv rebuilds.
    """
    packages = shlex.split(line)
    if not packages:
        raise UsageError("Usage: %install <package> [package2 ...]")

    print(f"Installing: {' '.join(packages)}")
    result = install_packages(*packages)
    if not result["ok"]:
        print(result["error"])
        raise UsageError("Installation failed")
    if result["installed"]:
        print(f"Installed and recorded: {', '.join(result['installed'])}")
    if result["already_present"]:
        print(f"Already present: {', '.join(result['already_present'])}")
