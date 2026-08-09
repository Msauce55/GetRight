"""
impact_utils.py

Shared helpers for the Customer Impact Dashboard (06_Customer_Impact.py).

- log_assessment_run() should be called from 02_Assessment.py once an
  assessment's results (findings, savings, exposure) are available, so
  the dashboard has data to show.
- log_feedback() is called by the dashboard's own feedback form.

Storage is a pair of local JSON-lines files under ./data/. This is
simple and dependency-free, but on most hosted platforms (e.g.
Streamlit Community Cloud) local disk is EPHEMERAL and will be wiped
on redeploy/restart. For durable, multi-instance history, swap the
read/write functions below for a real database (SQLite on a mounted
volume, Postgres, Google Sheets, etc.) — the rest of the dashboard
doesn't need to change.

============================================================
PRIVACY: ENCRYPTION AT REST
============================================================
Every record written to disk (impact_history.jsonl and
customer_feedback.jsonl) contains a customer's company name and
representative's name. Because this is proprietary/identifying
information, records are encrypted with Fernet (AES-128-CBC +
HMAC, via the `cryptography` package) before they're written, and
decrypted transparently on read. Nothing in these files is
plaintext-readable without the key.

The encryption key comes from, in order of preference:

  1. The IMPACT_LOG_ENCRYPTION_KEY environment variable / Streamlit
     secret — a Fernet key you generate once and store securely
     (e.g. in your deployment's secret manager), the same way you
     already handle GROQ_API_KEY. Generate one with:
         python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

  2. A local key file at data/.impact_encryption_key, auto-created
     the first time this module runs if no env/secret key is set.

Option 2 is a real improvement over plaintext (an attacker who
only gets the .jsonl files gets nothing usable) but it is NOT a
substitute for option 1: if the key file lives next to the data
it protects, anyone with full filesystem access — not just the
data files — can still read both. For real protection, set
IMPACT_LOG_ENCRYPTION_KEY as a proper secret, store it somewhere
separate from the data directory (e.g. your platform's secret
manager), and do not commit either the key or data/ to git.

If the key is ever lost or changed, previously written records
become permanently unreadable (this is intentional — it's what
"encrypted" means). load_impact_history()/load_feedback() skip
any record that fails to decrypt rather than crashing, so a lost
key degrades to "history starts over," not an app crash.
============================================================
"""

import json
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = "data"
IMPACT_LOG_PATH = os.path.join(DATA_DIR, "impact_history.jsonl")
FEEDBACK_LOG_PATH = os.path.join(DATA_DIR, "customer_feedback.jsonl")
LOCAL_KEY_PATH = os.path.join(DATA_DIR, ".impact_encryption_key")

STATUS_KEYS = [
    "COMPLIANT",
    "PARTIALLY COMPLIANT",
    "NON-COMPLIANT",
    "INSUFFICIENT EVIDENCE"
]


# ============================================================
# ENCRYPTION KEY / FERNET INSTANCE
# ============================================================

_fernet_instance = None
_key_source = None  # "secret" or "local_file" — surfaced for the UI


def _load_or_create_key():

    global _key_source

    # 1. Streamlit secrets, if available.
    try:

        import streamlit as st

        key = st.secrets.get("IMPACT_LOG_ENCRYPTION_KEY")

        if key:

            _key_source = "secret"

            return key.encode() if isinstance(key, str) else key

    except Exception:

        pass

    # 2. Environment variable (local dev, or non-Streamlit secrets).
    env_key = os.getenv("IMPACT_LOG_ENCRYPTION_KEY")

    if env_key:

        _key_source = "secret"

        return env_key.encode() if isinstance(env_key, str) else env_key

    # 3. Local key file — create once if it doesn't exist yet.
    _ensure_data_dir()

    if os.path.exists(LOCAL_KEY_PATH):

        with open(LOCAL_KEY_PATH, "rb") as f:

            _key_source = "local_file"

            return f.read().strip()

    new_key = Fernet.generate_key()

    with open(LOCAL_KEY_PATH, "wb") as f:

        f.write(new_key)

    try:

        os.chmod(LOCAL_KEY_PATH, 0o600)

    except Exception:

        pass  # best-effort on platforms that don't support chmod

    _key_source = "local_file"

    return new_key


def _get_fernet():

    global _fernet_instance

    if _fernet_instance is None:

        _fernet_instance = Fernet(_load_or_create_key())

    return _fernet_instance


def get_key_source():
    """
    Returns "secret" if the encryption key came from
    IMPACT_LOG_ENCRYPTION_KEY (recommended), or "local_file" if it
    was auto-generated on disk (functional, but weaker — see the
    module docstring). Lets the dashboard show a status hint.
    Triggers key load/creation as a side effect if not already done.
    """

    _get_fernet()

    return _key_source


# ============================================================
# LOW-LEVEL FILE HELPERS (encrypt-on-write, decrypt-on-read)
# ============================================================

def _ensure_data_dir():

    os.makedirs(DATA_DIR, exist_ok=True)


def _append_jsonl(path, record):

    _ensure_data_dir()

    plaintext = json.dumps(record).encode("utf-8")

    token = _get_fernet().encrypt(plaintext)

    with open(path, "a", encoding="utf-8") as f:

        f.write(token.decode("utf-8") + "\n")


def _read_jsonl(path):

    if not os.path.exists(path):

        return []

    fernet = _get_fernet()

    records = []

    skipped = 0

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:

                continue

            try:

                plaintext = fernet.decrypt(line.encode("utf-8"))

                records.append(json.loads(plaintext))

            except (InvalidToken, ValueError, json.JSONDecodeError):

                # Wrong/rotated key, or a pre-encryption plaintext
                # line left over from before this change — skip
                # rather than crash the dashboard.
                skipped += 1

                continue

    if skipped:

        try:

            import streamlit as st

            st.caption(
                f"⚠️ {skipped} record(s) in "
                f"{os.path.basename(path)} could not be decrypted "
                "with the current key and were skipped."
            )

        except Exception:

            pass

    return records


# ============================================================
# WRITE: CALLED FROM 02_Assessment.py
# ============================================================

def log_assessment_run(
    company_name,
    representative,
    cmmc_level,
    framework_version,
    all_findings,
    savings,
    exposure
):
    """
    Record one completed assessment run so it shows up on the
    Customer Impact Dashboard. The record (including company_name
    and representative) is encrypted before being written to disk
    — see the module docstring.

    all_findings: the flattened list of finding dicts (each with a
        "status" key) used elsewhere in 02_Assessment.py. Only
        status COUNTS are persisted here, never the finding text,
        evidence, or reasoning — those stay in-session only.
    savings: the dict returned by compute_consultant_savings().
    exposure: the dict returned by compute_risk_exposure_avoided().
    """

    counts = {status: 0 for status in STATUS_KEYS}

    for finding in all_findings:

        status = finding.get("status", "INSUFFICIENT EVIDENCE")

        if status in counts:

            counts[status] += 1

    record = {

        "timestamp":
            datetime.now(timezone.utc).isoformat(),

        "company_name":
            company_name or "Unknown Company",

        "representative":
            representative or "",

        "cmmc_level":
            cmmc_level or "",

        "framework_version":
            framework_version or "",

        "num_controls":
            len(all_findings),

        "counts":
            counts,

        "net_savings":
            savings.get("net_savings", 0),

        "estimated_consultant_cost":
            savings.get("estimated_consultant_cost", 0),

        "tool_cost":
            savings.get("tool_cost", 0),

        "exposure_avoided":
            exposure.get("estimated_exposure_avoided", 0),

        "weighted_exposure_percentage":
            exposure.get("weighted_exposure_percentage", 0)

    }

    _append_jsonl(IMPACT_LOG_PATH, record)

    return record


# ============================================================
# WRITE: CALLED FROM THE DASHBOARD'S FEEDBACK FORM
# ============================================================

def log_feedback(company_name, representative, rating, comment):

    record = {

        "timestamp":
            datetime.now(timezone.utc).isoformat(),

        "company_name":
            company_name or "Unknown Company",

        "representative":
            representative or "",

        "rating":
            int(rating),

        "comment":
            (comment or "").strip()

    }

    _append_jsonl(FEEDBACK_LOG_PATH, record)

    return record


# ============================================================
# READ: CALLED FROM THE DASHBOARD
# ============================================================

def load_impact_history():

    import pandas as pd

    records = _read_jsonl(IMPACT_LOG_PATH)

    if not records:

        return pd.DataFrame()

    df = pd.DataFrame(records)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    df = df.dropna(subset=["timestamp"])

    df = df.sort_values("timestamp")

    for status in STATUS_KEYS:

        df[status] = df["counts"].apply(
            lambda counts_dict, s=status: (
                counts_dict.get(s, 0)
                if isinstance(counts_dict, dict)
                else 0
            )
        )

    for numeric_col in (
        "net_savings",
        "estimated_consultant_cost",
        "tool_cost",
        "exposure_avoided",
        "weighted_exposure_percentage",
        "num_controls"
    ):

        if numeric_col in df.columns:

            df[numeric_col] = pd.to_numeric(
                df[numeric_col], errors="coerce"
            ).fillna(0)

    return df


def load_feedback():

    import pandas as pd

    records = _read_jsonl(FEEDBACK_LOG_PATH)

    if not records:

        return pd.DataFrame()

    df = pd.DataFrame(records)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    df = df.sort_values("timestamp", ascending=False)

    return df


# ============================================================
# OPTIONAL: PURGE OLD RECORDS (retention hygiene)
# ============================================================
#
# Not wired into the dashboard automatically — call this yourself
# (e.g. from a scheduled job, or a "Purge old records" admin
# button you add to the dashboard) if you want a retention policy
# rather than an ever-growing history file. Rewrites each file
# encrypted, keeping only records newer than `days`.
#
# ============================================================

def purge_older_than(days):

    import pandas as pd

    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(days=days)

    for path in (IMPACT_LOG_PATH, FEEDBACK_LOG_PATH):

        records = _read_jsonl(path)

        if not records:

            continue

        kept = [
            r for r in records
            if pd.to_datetime(r.get("timestamp"), errors="coerce", utc=True) >= cutoff
        ]

        if len(kept) == len(records):

            continue  # nothing to purge

        _ensure_data_dir()

        with open(path, "w", encoding="utf-8") as f:

            for record in kept:

                token = _get_fernet().encrypt(
                    json.dumps(record).encode("utf-8")
                )

                f.write(token.decode("utf-8") + "\n")