"""Flask app for the sync bot.

The Bot syncs the zhinst-qcodes repository with any changes that happen in
the zhinst-toolkit repository.
"""
import os
import threading
import typing as t

import click
import jinja2
from flask import Flask, request
from github import Github, GithubException, GithubIntegration
from github.PullRequest import PullRequest
from github.Repository import Repository

from qcodes_generator_helper import update_qcodes_branch

APP_ID = os.environ.get("APP_ID")
APP_SECRET = os.environ.get("APP_SECRET")
TEMPLATE_PATH = "templates"
TOOLKIT_ID = 245159715

app = Flask(__name__)


def pull_request_for_branch(
    repository: Repository, name: str
) -> t.Optional[PullRequest]:
    """Get pull request for a given branch.

    Args:
        repository: repository where the pull request should live.
        name: name of the branch.

    Returns:
        Pull request for the given branch. None if no pull request exists for
        the given branch.
    """
    for issue in repository.get_issues():
        try:
            if issue.as_pull_request().head.ref == name:
                return issue.as_pull_request()
        except GithubException:
            pass
    return None


def get_repository(name: str, owner: str = "zhinst") -> Github:
    """Get a github repository connection owned by the github app.

    Args:
        name: Name of the repository
        owner: Owner of the repository

    Returns:
        Active github repository connection.
    """
    git_integration = GithubIntegration(APP_ID, APP_SECRET)
    git_connection = Github(
        login_or_token=git_integration.get_access_token(
            git_integration.get_installation(owner, name).id
        ).token
    )
    return git_connection.get_repo(f"{owner}/{name}")


def get_or_create_pull_request(
    branch: str, repo: Repository, linked_title: str, linked_url: str
) -> PullRequest:
    """Get or create a pull request for the given branch.

    Args:
        branch: Name of the branch.
        repo: Repository where the pull request should live.
        linked_title: Title of corresponding source pull request.
        linked_url: URL of corresponding source pull request.

    Returns:
        PullRequest for the given branch.
    """
    templateLoader = jinja2.FileSystemLoader(searchpath=TEMPLATE_PATH)
    jinja_env = jinja2.Environment(loader=templateLoader)
    pull_request = pull_request_for_branch(repo, branch)
    if not pull_request:
        title = f"[SYNC BOT]{linked_title}"
        body = jinja_env.get_template("pr_body.j2").render(
            {"linked_pull_request_url": linked_url}
        )
        pull_request = repo.create_pull(
            title=title, body=body, base="main", head=branch
        )
    return pull_request


def handle_toolkit_sync(payload: t.Dict) -> None:
    """Handle the toolkit sync event.

    Args:
        payload: Payload of the github webhook event.
    """
    source_project = payload["pull_request"]["head"]["repo"]["clone_url"]
    branch = payload["pull_request"]["head"]["ref"]
    last_commit = payload["pull_request"]["head"]["sha"]

    # Only create/update a zhinst-qcodes link if the target branch is main
    if payload["pull_request"]["base"]["ref"] != "main":
        print(
            f"Ignore request for {source_project}@{branch}({last_commit}) "
            "since its base branch is not main."
        )
    templateLoader = jinja2.FileSystemLoader(searchpath=TEMPLATE_PATH)
    jinja_env = jinja2.Environment(loader=templateLoader)

    qcodes_repo = get_repository("zhinst-qcodes")

    # Sync zhinst-qcodes branch with new changes
    branch_existed = branch in [branch.name for branch in qcodes_repo.get_branches()]
    # create update qcodes
    commit_message = f"[SYNC BOT] SYNC with zhinst-toolkit\n{branch}:{last_commit}"
    commit = update_qcodes_branch(commit_message, branch, source_project, last_commit)
    if commit:
        # zhinst-qcodes branch
        pull_request = get_or_create_pull_request(
            branch,
            repo=qcodes_repo,
            linked_title=payload["pull_request"]["title"],
            linked_url=payload["pull_request"]["html_url"],
        )
        # zhinst-toolkit part
        update_message = jinja_env.get_template("update_message.j2").render(
            {
                "new_changes": True,
                "new_branch": not branch_existed,
                "branch_name": branch,
                "branch_url": f"https://github.com/zhinst/zhinst-toolkit/tree/{branch}",
                "commit_url": pull_request.html_url + "/commits/" + commit[0],
                "pull_request": pull_request.html_url,
                "files": commit[1],
                "used_commit": last_commit,
            }
        )
    else:
        update_message = jinja_env.get_template("update_message.j2").render(
            {
                "new_changes": False,
            }
        )
    toolkit_repo = get_repository("zhinst-toolkit")
    issue = toolkit_repo.get_issue(number=payload["pull_request"]["number"])
    issue.create_comment(update_message)


def handle_toolkit_close(payload: t.Dict) -> None:
    """Handle the toolkit close event.

    Args:
        payload: Payload of the github webhook event.
    """
    qcodes_repo = get_repository("zhinst-qcodes")
    branch = payload["pull_request"]["head"]["ref"]
    pull_request = pull_request_for_branch(qcodes_repo, branch)
    if pull_request:
        if payload["pull_request"]["merged"]:
            pull_request.create_comment(
                str(
                    "The corresponding zhinst-toolkit branch was merged. "
                    f"({payload['pull_request']['html_url']})"
                )
            )
        else:
            pull_request.create_comment(
                str(
                    "The corresponding zhinst-toolkit branch was closed. "
                    f"({payload['pull_request']['html_url']})"
                )
            )
            pull_request.edit(status="closed")


def handle_toolkit_reopen(payload: t.Dict) -> None:
    """Handle the toolkit reopen event.

    Args:
        payload: Payload of the github webhook event.
    """
    qcodes_repo = get_repository("zhinst-qcodes")
    branch = payload["pull_request"]["head"]["ref"]
    pull_request = pull_request_for_branch(qcodes_repo, branch)
    if pull_request:
        pull_request.create_comment(
            str(
                "The corresponding zhinst-toolkit branch was reopened. "
                f"({payload['pull_request']['html_url']})"
            )
        )
        pull_request.edit(state="open")


def handle_toolkit_edit(payload: t.Dict) -> None:
    """Handle the toolkit edit event.

    Args:
        payload: Payload of the github webhook event.
    """
    qcodes_repo = get_repository("zhinst-qcodes")
    branch = payload["pull_request"]["head"]["ref"]
    pull_request = pull_request_for_branch(qcodes_repo, branch)
    if pull_request:
        toolkit_repo = get_repository("zhinst-toolkit")
        toolkit_pr = toolkit_repo.get_issue(number=payload["pull_request"]["number"])
        if pull_request.title != toolkit_pr.title:
            pull_request.edit(title=toolkit_pr.title)


@app.route("/", methods=["POST"])
def bot():
    """Entry point for for the github bot through a webhook."""
    # Get the event payload
    payload = request.json

    # For now we only consider pull request actions
    if "pull_request" not in payload:
        return "ok"

    # Only accept calls from zhinst-toolkit directly
    if payload["repository"]["id"] == TOOLKIT_ID:
        if payload["action"] in ["synchronize", "opened"]:
            # Triggered when a pull request's head branch is updated. For example,
            # when the head branch is updated from the base branch, when new
            # commits are pushed to the head branch, or when the base branch is
            # changed.
            threading.Thread(target=handle_toolkit_sync, args=(payload,)).start()
        elif payload["action"] == "closed":
            # If the action is closed and the merged key is false, the pull request
            # was closed with unmerged commits. If the action is closed and the
            # merged key is true, the pull request was merged.$
            threading.Thread(target=handle_toolkit_close, args=(payload,)).start()
        elif payload["action"] == "reopened":
            threading.Thread(target=handle_toolkit_reopen, args=(payload,)).start()
        elif payload["action"] == "edited":
            threading.Thread(target=handle_toolkit_edit, args=(payload,)).start()
        else:
            print(f"Unknown action: {payload['action']}")

    # TODO: Implement reverse path. E.g. if zhinst-qcodes pipeline fails
    # if payload["repository"]["id"] == QCODES_ID:

    return "ok"


@click.command()
@click.option(
    "--port",
    "-p",
    required=True,
    type=int,
    help="Port to listen on",
)
@click.option(
    "--debug",
    "-d",
    required=False,
    is_flag=True,
    default=False,
    help="Enable debug mode",
)
@click.option(
    "--id",
    required=False,
    type=str,
    default=os.environ.get("APP_ID"),
    help="Github App ID. (default environment variable APP_ID)",
)
@click.option(
    "--secret",
    required=False,
    type=str,
    default=os.environ.get("APP_SECRET"),
    help="Github App secret. (default environment variable APP_SECRET)",
)
def start_app(port: int, debug: bool, id: str, secret: str):
    """Start the bot app."""
    global APP_ID, APP_SECRET
    APP_ID = id
    APP_SECRET = secret

    app.run(debug=debug, port=port)


if __name__ == "__main__":
    start_app()
