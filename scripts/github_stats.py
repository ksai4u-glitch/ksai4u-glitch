"""Fetch the numbers for the "GitHub Stats" block from GitHub's GraphQL API.

Read-only: every call here is a query, nothing is ever written to GitHub.
Uses only the Python standard library, so the GitHub Action needs no pip install.

The one public function is collect(). Everything else is a small helper that
does one job, so you can read it top to bottom:

    collect()
      -> fetch_user()        followers, account creation date, user id
      -> fetch_repos()       every repo you own or contribute to, with stars
      -> count_lines()       lines added/deleted by you, per repo
      -> count_commits()     your commit contributions, year by year
"""

import datetime as dt
import json
import time
import urllib.error
import urllib.request

API_URL = "https://api.github.com/graphql"


class GitHubError(RuntimeError):
    """The API answered, but with an error (bad token, unknown user, ...)."""


# ---------------------------------------------------------------------------
# Transport: send one GraphQL query, get back the "data" part of the answer.
# ---------------------------------------------------------------------------

def graphql(query, variables, token, retries=3):
    body = json.dumps({"query": query, "variables": variables}).encode()
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "profile-card-builder",
    }
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(API_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as err:
            # 502/503 happen now and then on big history queries: wait and retry.
            if err.code in (502, 503, 504) and attempt < retries:
                time.sleep(5 * attempt)
                continue
            raise GitHubError(f"HTTP {err.code} from GitHub: {err.reason}") from err

    if payload.get("errors"):
        raise GitHubError(payload["errors"][0].get("message", "unknown GraphQL error"))
    return payload["data"]


# ---------------------------------------------------------------------------
# Queries. Each one asks for exactly the fields the card needs.
# ---------------------------------------------------------------------------

USER_QUERY = """
query ($login: String!) {
  user(login: $login) {
    id
    createdAt
    followers { totalCount }
  }
}
"""

REPOS_QUERY = """
query ($login: String!, $cursor: String, $privacy: RepositoryPrivacy) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, privacy: $privacy,
                 ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner stargazerCount owner { login } }
    }
  }
}
"""

LINES_QUERY = """
query ($owner: String!, $name: String!, $author: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor, author: {id: $author}) {
            pageInfo { hasNextPage endCursor }
            nodes { additions deletions }
          }
        }
      }
    }
  }
}
"""

COMMITS_QUERY = """
query ($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) { totalCommitContributions }
  }
}
"""


# ---------------------------------------------------------------------------
# Helpers. `run` is a function (query, variables) -> data. Passing it in,
# instead of calling graphql() directly, is what lets the tests feed in
# fake answers without touching the network.
# ---------------------------------------------------------------------------

def fetch_user(login, run):
    user = run(USER_QUERY, {"login": login})["user"]
    if user is None:
        raise GitHubError(f"no GitHub user called {login!r}")
    return user


def fetch_repos(login, include_private, run):
    """Return (list of repo nodes, total count). Follows pagination to the end."""
    repos, cursor = [], None
    while True:
        variables = {"login": login, "cursor": cursor}
        if not include_private:
            variables["privacy"] = "PUBLIC"
        page = run(REPOS_QUERY, variables)["user"]["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return repos, page["totalCount"]
        cursor = page["pageInfo"]["endCursor"]


def count_lines(repo, author_id, run):
    """Lines added and deleted by you on the repo's default branch."""
    owner, name = repo["nameWithOwner"].split("/", 1)
    added = deleted = 0
    cursor = None
    while True:
        data = run(LINES_QUERY, {"owner": owner, "name": name,
                                 "author": author_id, "cursor": cursor})
        branch = data["repository"]["defaultBranchRef"]
        if branch is None:          # empty repo, nothing pushed yet
            return 0, 0
        history = branch["target"]["history"]
        for commit in history["nodes"]:
            added += commit["additions"]
            deleted += commit["deletions"]
        if not history["pageInfo"]["hasNextPage"]:
            return added, deleted
        cursor = history["pageInfo"]["endCursor"]


def count_commits(login, created_at, now, run):
    """GitHub only answers one year at a time, so walk from sign-up to today."""
    total = 0
    start = created_at
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        data = run(COMMITS_QUERY, {"login": login,
                                   "from": start.isoformat(), "to": end.isoformat()})
        total += data["user"]["contributionsCollection"]["totalCommitContributions"]
        start = end
    return total


def parse_time(text):
    # GitHub sends "2025-03-01T10:00:00Z"; older Pythons dislike the "Z".
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# The one function build_card.py calls.
# ---------------------------------------------------------------------------

def collect(login, token=None, include_private=True, run=None, now=None):
    if run is None:
        run = lambda query, variables: graphql(query, variables, token)  # noqa: E731
    now = now or dt.datetime.now(dt.timezone.utc)

    user = fetch_user(login, run)
    repos, contributed = fetch_repos(login, include_private, run)
    owned = [r for r in repos if r["owner"]["login"].lower() == login.lower()]

    added = deleted = 0
    for repo in repos:
        a, d = count_lines(repo, user["id"], run)
        added += a
        deleted += d

    return {
        "repos": len(owned),
        "contributed": contributed,
        "stars": sum(r["stargazerCount"] for r in owned),
        "commits": count_commits(login, parse_time(user["createdAt"]), now, run),
        "followers": user["followers"]["totalCount"],
        "loc_added": added,
        "loc_deleted": deleted,
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
    }
