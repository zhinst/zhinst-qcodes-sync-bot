"""Helper module to generate zhinst-qcodes based on toolkit."""
import os
import shutil
import subprocess
import typing as t
from contextlib import contextmanager
from random import randint

import virtualenv
from git import Repo
from git import exc as git_exception

QCODES_URL = "https://github.com/zhinst/zhinst-qcodes"


def install_toolkit_venv(
    venv_path: str, source_project: str, source_commit: str
) -> None:
    """Install a specific toolkit version into a venv.

    Args:
        venv_path: Path to the venv.
        source_project: URL of the source project.
        source_commit: Commit of the source project.
    """
    bashCommand = f"{venv_path}/bin/pip install git+{source_project}@{source_commit}"
    subprocess.run(bashCommand.split(), check=True)


@contextmanager
def temporary_virtual_environment(
    name: str = None,
) -> t.Generator[None, str, None]:
    """Create a temporary python virtual environment.

    The environment is removed when the context is released.

    Args:
        name: Name of the virtual environment.

    Yields:
        Name of the temporary environment.
    """
    name = name if name else f"temp_venv_{randint(0,2e16)}"
    virtualenv.cli_run([name])
    yield name
    shutil.rmtree(name)


@contextmanager
def temporary_git_checkout(url: str, branch: str = None, name: str = None):
    """Create a temporary git checkout.

    The checkout is removed when the context is released.

    Args:
        url: URL of the git repository.
        branch: Branch of the git repository.
        name: Name of the git checkout.
    """
    if not name:
        name = f"temp_qcodes_{randint(0,2e16)}"
    if os.path.exists(name):
        raise RuntimeError(f"{name} already exists")
    os.mkdir(name)
    repo = Repo.init(name)
    try:
        origin = repo.create_remote("origin", url)
        assert origin.exists()
        origin.fetch()
        if not branch:
            branch = "main"
        repo.create_head(branch, origin.refs[branch])
        repo.heads[branch].set_tracking_branch(origin.refs[branch])
        repo.heads[branch].checkout()
        yield repo
    finally:
        shutil.rmtree(name)


def switch_branch(repository: Repo, name: str) -> None:
    """Switch branch in a git repository.

    Args:
        repository: Git repository.
        name: Name of the branch.
    """
    try:
        repository.git.checkout(name)
    except git_exception.GitCommandError:
        repository.git.checkout("origin/main", b=name)


def update_qcodes_branch(
    message: str, branch: str, toolkit_url: str, toolkit_commit: str
) -> None:
    """Update a zhinst-qcodes branch with changes from a toolkit branch.

    Args:
        message: Commit message.
        branch: Name of the branch that should be updated.
        toolkit_url: URL of the toolkit repository.
        toolkit_commit: Name of the toolkit branch to use. If not specified
            the same branch name for toolkit and qcodes are used.

    Returns:
        Commit Hash that contains the changes. None if no changes are detected.
    """
    with temporary_virtual_environment() as temp_venv:
        install_toolkit_venv(temp_venv, toolkit_url, toolkit_commit)
        with temporary_git_checkout(QCODES_URL) as qcodes_repo:
            switch_branch(qcodes_repo, branch)
            relative_python = os.path.relpath(temp_venv, qcodes_repo.working_dir)
            bashCommand = f"{relative_python}/bin/pip install -r requirements.txt"
            subprocess.run(bashCommand.split(), check=True, cwd=qcodes_repo.working_dir)
            bashCommand = (
                f"{relative_python}/bin/python generator/generator.py generate-all"
            )
            subprocess.run(bashCommand.split(), check=True, cwd=qcodes_repo.working_dir)

            if qcodes_repo.index.diff(None):
                changed_files = [file.a_path for file in qcodes_repo.index.diff(None)]
                qcodes_repo.git.add(".")
                qcodes_repo.git.commit(message=message)
                qcodes_repo.git.push("origin", branch, u=True)
                return qcodes_repo.head.commit.hexsha, changed_files
    return None
