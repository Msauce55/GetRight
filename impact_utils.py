"""
impact_utils.py

Persistence layer for the Customer Impact Dashboard.

Assessment history and customer feedback are stored as CSV files
committed directly to this repo via the GitHub Contents API. That
keeps storage free (no database, no new account beyond GitHub, which
you already have since the app is deployed from a repo) and makes the
data durable across Streamlit Community Cloud restarts/redeploys —
the app's local disk is wiped on every reboot, but the repo isn't.

REQUIRED SETUP
---------------
1. Create a GitHub Personal Access Token (fine-grained, scoped to
   just this repo, with "Contents: Read and write" permission):
   https://github.com/settings/tokens?type=beta

2. Add these to your Streamlit secrets (Settings -> Secrets on
   Streamlit Community Cloud, or .streamlit/secrets.toml locally):

     GITHUB_TOKEN = "ghp_..."
     GITHUB_REPO = "yourusername/your-repo-name"
     GITHUB_BRANCH = "data"

3. Add "requests" to requirements.txt if it isn't already pulled in
   as a dependency of another package.

Writing to a separate "data" branch (rather than your deployment
branch) means logged assessments and feedback submissions commit
quietly in the background without triggering a Streamlit Community
Cloud redeploy/restart.

The CSVs are created automatically on first write at:
   data/impact_history.csv
   data/feedback.csv
"""

import base64
import io
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st


STATUS_KEYS = [
    "COMPLIANT",
    "PARTIALLY COMPLIANT",
    "NON-COMPLIANT",
    "INSUFFICIENT EVIDENCE",
]

IMPACT_HISTORY_PATH = "data/impact_history.csv"
FEEDBACK_PATH = "data/feedback.csv"

IMPACT_HISTORY_COLUMNS = [
    "timestamp",
    "company_name",
    "representative",
    "cmmc_level",
    "framework_version",
    "num_controls",
    "net_savings",
    "exposure_avoided",
] + STATUS_KEYS

FEEDBACK_COLUMNS = [
    "timestamp",
    "company_name",
    "representative",
    "rating",
    "comment",
]

GITHUB_API_TIMEOUT_SECONDS = 15
MAX_COMMIT_RETRIES = 3


# ============================================================
# GITHUB CONTENTS API HELPERS
# ============================================================

def _github_headers():

    token = st.secrets["GITHUB_TOKEN"]

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _repo():

    return st.secrets["GITHUB_REPO"]


def _branch():

    return st.secrets.get("GITHUB_BRANCH", "main")


def _github_get_file(path):
    """
    Returns (dataframe, sha) for the CSV at `path` in the repo.
    Returns (None, None) if the file doesn't exist yet.
    """

    url = f"https://api.github.com/repos/{_repo()}/contents/{path}"

    response = requests.get(
        url,
        headers=_github_headers(),
        params={"ref": _branch()},
        timeout=GITHUB_API_TIMEOUT_SECONDS,
    )

    if response.status_code == 404:
        return None, None

    response.raise_for_status()

    payload = response.json()

    content = base64.b64decode(payload["content"]).decode("utf-8")

    df = pd.read_csv(io.StringIO(content))

    return df, payload["sha"]


def _github_put_file(path, df, sha, commit_message):
    """
    Commits `df` (as CSV) to `path` in the repo. Pass the current
    `sha` (from _github_get_file) when overwriting an existing file,
    or None when creating a new file for the first time.
    """

    url = f"https://api.github.com/repos/{_repo()}/contents/{path}"

    csv_content = df.to_csv(index=False)

    encoded_content = base64.b64encode(
        csv_content.encode("utf-8")
    ).decode("utf-8")

    body = {
        "message": commit_message,
        "content": encoded_content,
        "branch": _branch(),
    }

    if sha:
        body["sha"] = sha

    response = requests.put(
        url,
        headers=_github_headers(),
        json=body,
        timeout=GITHUB_API_TIMEOUT_SECONDS,
    )

    response.raise_for_status()


def _append_row_with_retry(path, columns, new_row, commit_message):
    """
    Reads the current CSV, appends `new_row`, and commits it back.
    Retries on a 409 (sha conflict, from two people submitting at
    nearly the same moment) by re-reading the latest version and
    trying again.
    """

    for attempt in range(MAX_COMMIT_RETRIES):

        df, sha = _github_get_file(path)

        if df is None:
            df = pd.DataFrame(columns=columns)

        df = pd.concat(
            [df, pd.DataFrame([new_row])],
            ignore_index=True,
        )

        try:

            _github_put_file(path, df, sha, commit_message)

            return

        except requests.HTTPError as error:

            is_conflict = (
                error.response is not None
                and error.response.status_code == 409
            )

            if is_conflict and attempt < MAX_COMMIT_RETRIES - 1:
                time.sleep(1)
                continue

            raise


# ============================================================
# ASSESSMENT HISTORY
# ============================================================

def load_impact_history():
    """
    Returns the full assessment history as a DataFrame. Returns an
    empty DataFrame (with the right columns) if nothing has been
    logged yet.
    """

    df, _ = _github_get_file(IMPACT_HISTORY_PATH)

    if df is None:
        return pd.DataFrame(columns=IMPACT_HISTORY_COLUMNS)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df


def log_assessment_run(
    company_name,
    representative,
    cmmc_level,
    framework_version,
    all_findings,
    savings,
    exposure,
):
    """
    Appends one row to the assessment history and commits it to the
    repo.
    """

    status_counts = {status: 0 for status in STATUS_KEYS}

    for finding in all_findings:

        status = finding.get("status", "INSUFFICIENT EVIDENCE")

        if status in status_counts:
            status_counts[status] += 1

    new_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "company_name": company_name,
        "representative": representative,
        "cmmc_level": cmmc_level,
        "framework_version": framework_version,
        "num_controls": len(all_findings),
        "net_savings": savings["net_savings"],
        "exposure_avoided": exposure["estimated_exposure_avoided"],
        **status_counts,
    }

    _append_row_with_retry(
        IMPACT_HISTORY_PATH,
        IMPACT_HISTORY_COLUMNS,
        new_row,
        commit_message=f"Log assessment: {company_name}",
    )


# ============================================================
# CUSTOMER FEEDBACK
# ============================================================

def load_feedback():
    """
    Returns all customer feedback as a DataFrame, most recent first.
    Returns an empty DataFrame (with the right columns) if none has
    been submitted yet.
    """

    df, _ = _github_get_file(FEEDBACK_PATH)

    if df is None:
        return pd.DataFrame(columns=FEEDBACK_COLUMNS)

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    return df.sort_values(
        "timestamp", ascending=False
    ).reset_index(drop=True)


def log_feedback(company_name, representative, rating, comment):
    """
    Appends one row of feedback and commits it to the repo.
    """

    new_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "company_name": company_name,
        "representative": representative,
        "rating": rating,
        "comment": comment,
    }

    _append_row_with_retry(
        FEEDBACK_PATH,
        FEEDBACK_COLUMNS,
        new_row,
        commit_message=f"Log feedback: {company_name}",
    )