"""
POA&M Development Assistant
CMMC Levels 2–3

- Level 1: POA&Ms are NOT authorized (hard annotation + block)
- Levels 2–3: Full POA&M builder driven by open findings from Assessment / BLUF
- Standard DoD-style POA&M fields, milestones, prioritization, and CSV export
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, UTC
import json
import uuid

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="POA&M | CMMC",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📋 Plan of Action & Milestones (POA&M)")
st.caption(
    "CMMC-aligned POA&M development assistant. "
    "Supports Levels 2 and 3. Level 1 is restricted."
)

# -----------------------------------------------------------------------------
# Constants & helpers
# -----------------------------------------------------------------------------
CMMC_LEVEL1_PRACTICES = {
    # The 15 CMMC Level 1 practices (also present in Level 2).
    # Under current CMMC rules these may not reside on a POA&M for L2 certification.
    "AC.L1-3.1.1", "AC.L1-3.1.2", "AC.L1-3.1.20", "AC.L1-3.1.22",
    "IA.L1-3.5.1", "IA.L1-3.5.2",
    "MP.L1-3.8.3",
    "PE.L1-3.10.1", "PE.L1-3.10.3", "PE.L1-3.10.4", "PE.L1-3.10.5",
    "SC.L1-3.13.1", "SC.L1-3.13.5",
    "SI.L1-3.14.1", "SI.L1-3.14.2", "SI.L1-3.14.4",
}

STATUS_OPTIONS = [
    "Open",
    "In Progress",
    "Risk Accepted",
    "Completed",
    "Cancelled",
]

PRIORITY_OPTIONS = ["Critical", "High", "Moderate", "Low"]

def _normalize_findings(raw):
    """Normalize findings coming from Assessment / BLUF session_state."""
    if not raw:
        return []
    normalized = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        status = str(
            item.get("status")
            or item.get("Status")
            or item.get("Compliance_Status")
            or ""
        ).strip().upper().replace("_", "-").replace(" ", "-")
        if status in ("NON-COMPLIANT", "NONCOMPLIANT", "FAIL", "FAILED"):
            status = "NON-COMPLIANT"
        elif status in ("PARTIALLY-COMPLIANT", "PARTIAL", "PARTIALLY COMPLIANT"):
            status = "PARTIALLY COMPLIANT"
        else:
            # Keep only open items for POA&M
            if status not in ("NON-COMPLIANT", "PARTIALLY COMPLIANT"):
                continue

        control_id = str(
            item.get("Control ID")
            or item.get("control_id")
            or item.get("id")
            or item.get("Control")
            or f"CTRL-{i+1}"
        ).strip()

        normalized.append({
            "Control ID": control_id,
            "Control Name": str(
                item.get("Control Name")
                or item.get("control_name")
                or item.get("name")
                or ""
            ),
            "Family": str(item.get("Family") or item.get("family") or ""),
            "Severity": str(
                item.get("Severity")
                or item.get("severity")
                or item.get("Residual Risk")
                or "Moderate"
            ),
            "Status": status,
            "Finding": str(
                item.get("Finding")
                or item.get("finding")
                or item.get("description")
                or ""
            ),
            "Days Open": item.get("Days Open") or item.get("days_open") or 30,
            "Related Assets": str(
                item.get("Related Assets")
                or item.get("assets")
                or ""
            ),
        })
    return normalized


def _is_level1_practice(control_id: str) -> bool:
    cid = (control_id or "").strip().upper()
    # Exact match or common short forms
    if cid in {p.upper() for p in CMMC_LEVEL1_PRACTICES}:
        return True
    # Heuristic: AC.L1-*, IA.L1-*, etc.
    if ".L1-" in cid or cid.startswith(("AC.L1", "IA.L1", "MP.L1", "PE.L1", "SC.L1", "SI.L1")):
        return True
    return False


def _default_poam_row(finding: dict, level: int) -> dict:
    """Create a starter POA&M row from an open finding."""
    control_id = finding.get("Control ID", "")
    severity = str(finding.get("Severity", "Moderate")).title()
    if severity not in PRIORITY_OPTIONS:
        severity = "Moderate"

    # CMMC L2 typical close-out window guidance (illustrative)
    days_to_close = 180 if level == 2 else 90
    scheduled = (date.today() + timedelta(days=days_to_close)).isoformat()

    return {
        "POA&M ID": f"POAM-{str(uuid.uuid4())[:8].upper()}",
        "Control ID": control_id,
        "Control Name": finding.get("Control Name", ""),
        "Weakness / Deficiency": finding.get("Finding", "") or "Describe the weakness observed during assessment.",
        "Severity / Priority": severity,
        "POC": "",
        "Resources Required": "",
        "Scheduled Completion Date": scheduled,
        "Milestone 1": "Identify root cause and owner",
        "Milestone 1 Date": (date.today() + timedelta(days=14)).isoformat(),
        "Milestone 2": "Implement corrective action",
        "Milestone 2 Date": (date.today() + timedelta(days=60)).isoformat(),
        "Milestone 3": "Validate & close",
        "Milestone 3 Date": scheduled,
        "Status": "Open",
        "Risk if Not Corrected": "Increased likelihood of exploitation; potential impact to CUI confidentiality/integrity.",
        "Comments / Changes": "",
        "Level 1 Practice?": "Yes" if _is_level1_practice(control_id) else "No",
        "Source Status": finding.get("Status", ""),
    }


# -----------------------------------------------------------------------------
# Sidebar – Level & context
# -----------------------------------------------------------------------------
st.sidebar.header("Assessment Context")

# Prefer values pushed from Assessment / BLUF
session_level = st.session_state.get("bluf_cmmc_level") or st.session_state.get("assessment_level")
session_framework = st.session_state.get("bluf_framework") or st.session_state.get("assessment_framework") or "CMMC"

# Normalize level to int
def _parse_level(val):
    if val is None:
        return 2
    s = str(val).strip().upper()
    if "3" in s:
        return 3
    if "1" in s:
        return 1
    return 2

cmmc_level = st.sidebar.selectbox(
    "CMMC Level",
    options=[1, 2, 3],
    index=_parse_level(session_level) - 1,
    help="POA&Ms are only authorized for CMMC Levels 2 and 3 under current rules.",
)

st.sidebar.markdown(f"**Framework:** {session_framework}")
st.sidebar.markdown("---")

# -----------------------------------------------------------------------------
# LEVEL 1 HARD ANNOTATION / BLOCK
# -----------------------------------------------------------------------------
if cmmc_level == 1:
    st.error("### ⛔ POA&Ms Are NOT Authorized for CMMC Level 1")
    st.markdown(
        """
**CMMC Level 1 does not permit Plans of Action & Milestones (POA&Ms).**

#### Why?
- CMMC Level 1 consists of **15 foundational practices** focused on basic cyber hygiene.
- For Level 1 self-assessment / affirmation, **every practice must be fully implemented**.
- There is **no allowance** to place any of the 15 Level 1 practices on a POA&M and still claim Level 1 compliance.

#### What you must do instead
1. Remediate every Non-Compliant or Partially Compliant finding until the practice is **fully met**.
2. Re-run the assessment / collect new evidence.
3. Only after all 15 practices are implemented should the Level 1 affirmation be signed.

#### Official stance (summary)
> POA&Ms are a construct used at CMMC Level 2 and Level 3 (with strict limitations).  
> They are **not** an authorized path for Level 1.

---
If you need to develop POA&Ms, change the **CMMC Level** selector in the sidebar to **Level 2** or **Level 3**.
"""
    )
    st.info(
        "This page remains available so assessors can clearly document the Level 1 restriction. "
        "No POA&M records can be created while Level 1 is selected."
    )
    st.stop()   # Hard stop – no POA&M builder for Level 1

# -----------------------------------------------------------------------------
# LEVELS 2 & 3 – POA&M BUILDER
# -----------------------------------------------------------------------------
st.success(f"**CMMC Level {cmmc_level}** selected — POA&M development is authorized (with restrictions).")

if cmmc_level == 2:
    st.warning(
        """
**Level 2 POA&M rules (high-level reminder)**  
- The **15 CMMC Level 1 practices** that are also part of Level 2 **cannot** be placed on a POA&M for certification purposes.  
- Remaining practices may be eligible for POA&M under current DoD / CMMC guidance, typically with defined close-out windows (commonly 180 days for many items).  
- Always consult the latest official CMMC Assessment Guide and DFARS / 32 CFR language for the exact rules that apply to your contract.
"""
    )
else:
    st.warning(
        """
**Level 3 POA&M rules (high-level reminder)**  
- Level 3 is significantly more restrictive.  
- Many controls require full implementation; POA&M eligibility is limited.  
- Confirm current official guidance before relying on a POA&M for any Level 3 practice.
"""
    )

# -----------------------------------------------------------------------------
# Load open findings
# -----------------------------------------------------------------------------
raw_findings = st.session_state.get("bluf_open_findings") or st.session_state.get("assessment_open_findings") or []
open_findings = _normalize_findings(raw_findings)

if "poam_items" not in st.session_state:
    st.session_state["poam_items"] = []

# Seed POA&M items from open findings if empty
if open_findings and not st.session_state["poam_items"]:
    for f in open_findings:
        st.session_state["poam_items"].append(_default_poam_row(f, cmmc_level))

# -----------------------------------------------------------------------------
# Summary metrics
# -----------------------------------------------------------------------------
items = st.session_state["poam_items"]
df_poam = pd.DataFrame(items) if items else pd.DataFrame()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("POA&M Items", len(items))
with col2:
    open_cnt = sum(1 for r in items if str(r.get("Status", "")).lower() == "open")
    st.metric("Open", open_cnt)
with col3:
    inprog = sum(1 for r in items if "progress" in str(r.get("Status", "")).lower())
    st.metric("In Progress", inprog)
with col4:
    l1_on_poam = sum(1 for r in items if r.get("Level 1 Practice?") == "Yes")
    st.metric("Level-1 Practices on POA&M", l1_on_poam)
with col5:
    critical = sum(1 for r in items if str(r.get("Severity / Priority", "")).lower() in ("critical", "high"))
    st.metric("Critical / High", critical)

if l1_on_poam > 0 and cmmc_level == 2:
    st.error(
        f"**{l1_on_poam} Level 1 practice(s)** appear on this POA&M. "
        "Under current CMMC Level 2 rules these practices are **not eligible** for POA&M "
        "and must be fully implemented before certification."
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# Source findings
# -----------------------------------------------------------------------------
with st.expander("Open findings received from Assessment / BLUF", expanded=bool(open_findings)):
    if open_findings:
        st.dataframe(pd.DataFrame(open_findings), width="stretch", hide_index=True)
        if st.button("↻ Re-seed POA&M items from current open findings", key="reseed"):
            st.session_state["poam_items"] = [_default_poam_row(f, cmmc_level) for f in open_findings]
            st.rerun()
    else:
        st.info(
            "No open findings found in session. "
            "Run an assessment and click the **BLUF** button first, "
            "or add POA&M items manually below."
        )

# -----------------------------------------------------------------------------
# POA&M Table (editable)
# -----------------------------------------------------------------------------
st.subheader("POA&M Register")

if not items:
    st.info("No POA&M items yet. Add one manually or pull findings from the Assessment page.")
else:
    # Show warning flags
    display_df = df_poam.copy()
    st.dataframe(display_df, width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# Add / Edit form
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("Add or Update a POA&M Item")

with st.form("poam_form", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        control_id = st.text_input("Control ID *", value="")
        control_name = st.text_input("Control Name", value="")
        severity = st.selectbox("Severity / Priority", PRIORITY_OPTIONS, index=1)
    with c2:
        poc = st.text_input("Point of Contact (POC)", value="")
        resources = st.text_input("Resources Required", value="")
        status = st.selectbox("Status", STATUS_OPTIONS, index=0)
    with c3:
        sched_date = st.date_input(
            "Scheduled Completion Date",
            value=date.today() + timedelta(days=180 if cmmc_level == 2 else 90),
        )
        source_status = st.selectbox(
            "Source Finding Status",
            ["NON-COMPLIANT", "PARTIALLY COMPLIANT", "Other"],
            index=0,
        )

    weakness = st.text_area(
        "Weakness / Deficiency *",
        height=80,
        placeholder="Describe the specific weakness identified during the assessment…",
    )
    risk_text = st.text_area(
        "Risk if Not Corrected",
        height=60,
        value="Increased likelihood of exploitation; potential impact to CUI.",
    )

    st.markdown("**Milestones**")
    m1, m2, m3 = st.columns(3)
    with m1:
        ms1 = st.text_input("Milestone 1", value="Identify root cause & owner")
        ms1_date = st.date_input("Milestone 1 Date", value=date.today() + timedelta(days=14), key="ms1d")
    with m2:
        ms2 = st.text_input("Milestone 2", value="Implement corrective action")
        ms2_date = st.date_input("Milestone 2 Date", value=date.today() + timedelta(days=60), key="ms2d")
    with m3:
        ms3 = st.text_input("Milestone 3", value="Validate & close")
        ms3_date = st.date_input("Milestone 3 Date", value=sched_date, key="ms3d")

    comments = st.text_area("Comments / Changes", height=60)

    submitted = st.form_submit_button("➕ Add POA&M Item", type="primary", width="stretch")

    if submitted:
        if not control_id.strip() or not weakness.strip():
            st.error("Control ID and Weakness / Deficiency are required.")
        else:
            new_row = {
                "POA&M ID": f"POAM-{str(uuid.uuid4())[:8].upper()}",
                "Control ID": control_id.strip(),
                "Control Name": control_name.strip(),
                "Weakness / Deficiency": weakness.strip(),
                "Severity / Priority": severity,
                "POC": poc.strip(),
                "Resources Required": resources.strip(),
                "Scheduled Completion Date": sched_date.isoformat(),
                "Milestone 1": ms1,
                "Milestone 1 Date": ms1_date.isoformat(),
                "Milestone 2": ms2,
                "Milestone 2 Date": ms2_date.isoformat(),
                "Milestone 3": ms3,
                "Milestone 3 Date": ms3_date.isoformat(),
                "Status": status,
                "Risk if Not Corrected": risk_text.strip(),
                "Comments / Changes": comments.strip(),
                "Level 1 Practice?": "Yes" if _is_level1_practice(control_id) else "No",
                "Source Status": source_status,
            }
            st.session_state["poam_items"].append(new_row)
            st.success(f"Added {new_row['POA&M ID']} for control {control_id}")
            st.rerun()

# -----------------------------------------------------------------------------
# Manage existing items (delete / status change)
# -----------------------------------------------------------------------------
if items:
    st.markdown("---")
    st.subheader("Manage Existing Items")
    ids = [r["POA&M ID"] for r in items]
    selected_id = st.selectbox("Select POA&M ID", ids)
    selected = next((r for r in items if r["POA&M ID"] == selected_id), None)

    if selected:
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            new_status = st.selectbox(
                "Update Status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(selected["Status"]) if selected["Status"] in STATUS_OPTIONS else 0,
                key="upd_status",
            )
        with mc2:
            if st.button("Update Status", key="btn_upd"):
                selected["Status"] = new_status
                st.success(f"Status of {selected_id} set to {new_status}")
                st.rerun()
        with mc3:
            if st.button("🗑️ Delete Item", key="btn_del"):
                st.session_state["poam_items"] = [r for r in items if r["POA&M ID"] != selected_id]
                st.success(f"Deleted {selected_id}")
                st.rerun()

# -----------------------------------------------------------------------------
# Prioritization helper
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("Prioritization Helper")

if items:
    pri_df = pd.DataFrame(items)
    # Simple scoring: Critical=4, High=3, Moderate=2, Low=1 + Level-1 flag penalty for L2
    score_map = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1}
    pri_df["_score"] = pri_df["Severity / Priority"].map(score_map).fillna(2)
    if cmmc_level == 2:
        # Level-1 practices on a L2 POA&M are a certification blocker → highest urgency
        pri_df.loc[pri_df["Level 1 Practice?"] == "Yes", "_score"] = 5
    pri_df = pri_df.sort_values("_score", ascending=False)
    st.markdown("Suggested remediation order (highest priority first):")
    st.dataframe(
        pri_df[["POA&M ID", "Control ID", "Severity / Priority", "Level 1 Practice?", "Scheduled Completion Date", "Status"]],
        width="stretch",
        hide_index=True,
    )
else:
    st.caption("Add POA&M items to see prioritization.")

# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("Export POA&M")

if items:
    export_df = pd.DataFrame(items)
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download POA&M as CSV",
        data=csv_bytes,
        file_name=f"CMMC_L{cmmc_level}_POAM_{datetime.now(UTC).strftime('%Y%m%d')}.csv",
        mime="text/csv",
        type="primary",
        width="stretch",
    )
    st.caption("Use this CSV as a starting point for your official organizational POA&M template.")
else:
    st.info("Nothing to export yet.")

# -----------------------------------------------------------------------------
# Guidance footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f"""
### Quick Reference – CMMC POA&M

| Level | POA&M Authorized? | Key Constraint |
|-------|-------------------|----------------|
| **1** | **No** | All 15 practices must be fully implemented. No POA&M path. |
| **2** | Yes (limited) | Level 1 practices that are part of L2 **cannot** be on a POA&M. Other practices subject to close-out timelines. |
| **3** | Yes (highly limited) | Significantly more restrictive; confirm current official guidance. |

This tool is for **decision support and drafting only**.  
It does not replace the official CMMC Assessment Guide, DFARS clauses, or your organization’s approved POA&M process.
"""
)

st.caption(
    f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC | "
    "Notional assistant – verify all entries against current official CMMC requirements."
)
