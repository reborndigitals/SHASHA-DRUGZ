import os
from git import Repo, InvalidGitRepositoryError
from ..logging import LOGGER


def git():
    """
    VPS Deployment Mode:
    Only checks if repository exists.
    No auto-fetch, no origin, no pull, no token usage.
    """

    try:
        Repo(os.getcwd())
        LOGGER(__name__).info("Git Client Found [VPS DEPLOYMENT MODE]")
    except InvalidGitRepositoryError:
        LOGGER(__name__).warning(
            "Not a Git repository. Running in VPS standalone mode."
        )
    except Exception as e:
        LOGGER(__name__).error(f"Git check failed: {e}")
