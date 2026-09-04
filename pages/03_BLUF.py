import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Bottom Line Up Front | Non-Compliant Controls",
    page_icon="⚠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Load open findings pushed from the Assessment page (session_state)
# Fallback to empty / sample if none present
# -----------------------------------------------------------------------------
def load_open_findings_from_assessment():
    """
    Pull NON-COMPLIANT + PARTIALLY COMPLIANT findings that the
    Assessment page stored in session_state after a completed run.
    """
    findings = st.session_state.get("bluf_open_findings", [])
    level = st.session_state.get("bluf_cmmc_level", "CMMC Level 1")
    framework = st.session_state.get("bluf_framework", "CMMC 2.0")
    return findings, level, framework


def findings_to_dataframe(findings):
    """Convert the list of finding dicts into a clean display DataFrame."""
    if not findings:
        return pd.DataFrame()

    rows = []
    for f in findings:
        rows.append({
            "Control ID": f.get("control_id", "N/A"),
            "Status": f.get("status", "UNKNOWN"),
            "Severity": str(f.get("severity", "UNKNOWN")).title(),
            "Confidence %": f.get("confidence", 0),
            "Evidence Summary": (f.get("evidence_summary") or "")[:180] + ("..." if len(f.get("evidence_summary") or "") > 180 else ""),
            "Remediation": (f.get("remediation") or "")[:150] + ("..." if len(f.get("remediation") or "") > 150 else ""),
            "Source File": f.get("filename", ""),
            "Priority Score": f.get("priority_score", 0),  # may be absent if not pre-computed
        })
    df = pd.DataFrame(rows)

    # Simple priority if not already annotated
    if "Priority Score" not in df.columns or df["Priority Score"].sum() == 0:
        sev_map = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Unknown": 3}
        status_map = {"NON-COMPLIANT": 5, "PARTIALLY COMPLIANT": 3}
        df["Priority Score"] = df.apply(
            lambda r: sev_map.get(str(r["Severity"]).title(), 3) * status_map.get(r["Status"], 2),
            axis=1
        )
    return df.sort_values("Priority Score", ascending=False).reset_index(drop=True)


# -----------------------------------------------------------------------------
# CMMC Level sizing (used for simulation scaling)
# -----------------------------------------------------------------------------
CMMC_LEVEL_CONTROL_COUNTS = {
    "CMMC Level 1": 15,
    "CMMC Level 2": 110,
    "CMMC Level 3": 134,
}

# -----------------------------------------------------------------------------
# Sidebar – simulation parameters (user-adjustable assumptions)
# -----------------------------------------------------------------------------
st.sidebar.header("Simulation Parameters")
st.sidebar.markdown(
    "Adjust assumptions to model consequences of **not correcting** "
    "the open (Non-Compliant / Partially Compliant) controls."
)

time_horizon = st.sidebar.slider("Time Horizon (months)", 3, 36, 12)
base_incident_rate = st.sidebar.slider(
    "Base Monthly Incident Rate (if uncorrected)", 0.05, 2.0, 0.40, 0.05
)
risk_growth = st.sidebar.slider("Monthly Risk Growth Factor", 1.01, 1.30, 1.09, 0.01)
avg_incident_cost = st.sidebar.number_input(
    "Average Cost per Incident ($)", 25000, 5000000, 450000, 25000
)
mission_impact_weight = st.sidebar.slider("Mission Impact Multiplier", 1.0, 5.0, 2.3, 0.1)
num_simulations = st.sidebar.slider("Monte Carlo Runs", 100, 2000, 500, 100)

st.sidebar.markdown("---")
st.sidebar.info(
    "This is a **notional model** for decision support. "
    "It does not replace formal risk assessment, POA&M development, "
    "or a certified CMMC assessment."
)

# -----------------------------------------------------------------------------
# Load data pushed from Assessment page
# -----------------------------------------------------------------------------
open_findings, cmmc_level, framework = load_open_findings_from_assessment()
df = findings_to_dataframe(open_findings)

# Fallback sample if user navigates here with no assessment data
if df.empty:
    st.warning(
        "No open findings were pushed from the Assessment page. "
        "Run an assessment first, then click the **BLUF** button in the results section. "
        "Showing a small illustrative sample for demonstration."
    )
    sample = [
        {"Control ID": "AC.L1-b.1.i", "Status": "NON-COMPLIANT", "Severity": "High",
         "Confidence %": 82, "Evidence Summary": "Orphaned privileged accounts still active",
         "Remediation": "Disable unused accounts and implement 90-day review", "Source File": "sample",
         "Priority Score": 20},
        {"Control ID": "IA.L1-b.1.vi", "Status": "PARTIALLY COMPLIANT", "Severity": "High",
         "Confidence %": 71, "Evidence Summary": "MFA not enforced for all privileged paths",
         "Remediation": "Enforce MFA for all privileged and remote access", "Source File": "sample",
         "Priority Score": 12},
        {"Control ID": "SI.L1-b.1.xii", "Status": "NON-COMPLIANT", "Severity": "Critical",
         "Confidence %": 88, "Evidence Summary": "Critical CVEs older than 30 days unpatched",
         "Remediation": "Accelerate patch cycle for Critical/High CVEs", "Source File": "sample",
         "Priority Score": 25},
        {"Control ID": "SC.L1-b.1.x", "Status": "PARTIALLY COMPLIANT", "Severity": "Medium",
         "Confidence %": 65, "Evidence Summary": "Boundary filtering gaps and legacy rules",
         "Remediation": "Review and tighten boundary ACLs", "Source File": "sample",
         "Priority Score": 9},
    ]
    df = pd.DataFrame(sample)
    cmmc_level = "CMMC Level 1"
    framework = "CMMC 2.0 (illustrative)"

total_level_controls = CMMC_LEVEL_CONTROL_COUNTS.get(cmmc_level, 15)
open_count = len(df)
non_compliant_count = len(df[df["Status"] == "NON-COMPLIANT"])
partial_count = len(df[df["Status"] == "PARTIALLY COMPLIANT"])
critical_high = len(df[df["Severity"].isin(["Critical", "High"])])

# -----------------------------------------------------------------------------
# Main content – Bottom Line Up Front
# -----------------------------------------------------------------------------
st.title("⚠️ Bottom Line Up Front")
st.subheader(f"Open Controls — {cmmc_level}")

st.caption(
    f"Framework: **{framework}**  |  "
    f"Data source: Assessment page session (Non-Compliant + Partially Compliant only)"
)

# Summary metrics
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Open Controls", open_count)
with col2:
    st.metric("Non-Compliant", non_compliant_count)
with col3:
    st.metric("Partially Compliant", partial_count)
with col4:
    st.metric("Critical / High", critical_high)
with col5:
    pct_open = (open_count / total_level_controls * 100) if total_level_controls else 0
    st.metric("% of Level Open", f"{pct_open:.0f}%")

st.markdown("---")

# Detailed table
st.markdown("### Open Control Findings (pushed from Assessment)")
st.dataframe(df, use_container_width=True, hide_index=True)

# Severity & Status distribution (native charts)
st.markdown("### Distribution")
dist_col1, dist_col2 = st.columns(2)
with dist_col1:
    st.markdown("**By Severity**")
    sev_counts = df["Severity"].value_counts().reindex(
        ["Critical", "High", "Medium", "Low", "Unknown"]
    ).fillna(0)
    st.bar_chart(sev_counts)
with dist_col2:
    st.markdown("**By Status**")
    status_counts = df["Status"].value_counts()
    st.bar_chart(status_counts)

st.markdown("---")

# -----------------------------------------------------------------------------
# Modeling & Simulation – scaled by CMMC level and open findings
# -----------------------------------------------------------------------------
st.header("Modeling & Simulation: Consequences of Inaction")
st.markdown(
    f"""
    This section models what is likely to occur if the **{open_count} open controls**
    identified for **{cmmc_level}** remain uncorrected.
    The model scales with the number and severity of open findings and the size of the
    control set for the selected CMMC level.
    """
)

# --- Derive model intensity from the actual open findings ---
# More open controls + higher severity → higher starting risk & growth
severity_weight = {"Critical": 1.0, "High": 0.75, "Medium": 0.45, "Low": 0.25, "Unknown": 0.40}
avg_sev_weight = np.mean([severity_weight.get(s, 0.4) for s in df["Severity"]]) if open_count else 0.4
open_ratio = min(open_count / max(total_level_controls, 1), 1.0)

# Starting residual risk (0-100) driven by open ratio and severity
start_risk = 20 + (open_ratio * 45) + (avg_sev_weight * 25)
start_risk = float(np.clip(start_risk, 15, 85))

# Incident intensity also scales with open findings
effective_base_rate = base_incident_rate * (0.6 + open_ratio * 1.2) * (0.7 + avg_sev_weight * 0.8)

# Deterministic trajectories
months = np.arange(0, time_horizon + 1)
risk_score = start_risk * (risk_growth ** months)
risk_score = np.clip(risk_score, 0, 100)

intensity = effective_base_rate * (risk_growth ** months)
expected_incidents = np.cumsum(intensity)
expected_cost = expected_incidents * avg_incident_cost
mission_deg = 100 * (1 - np.exp(-0.012 * expected_incidents * mission_impact_weight * (1 + open_ratio)))

sim_df = pd.DataFrame({
    "Month": months,
    "Residual Risk Score": risk_score,
    "Expected Cumulative Incidents": expected_incidents,
    "Expected Cumulative Cost ($)": expected_cost,
    "Mission Degradation Index": mission_deg
}).set_index("Month")

# Charts (native Streamlit – no extra dependencies)
tab1, tab2, tab3, tab4 = st.tabs([
    "Risk Trajectory",
    "Expected Incidents & Cost",
    "Mission Impact",
    "Monte Carlo Distribution"
])

with tab1:
    st.markdown("#### Projected Residual Risk Score if Open Controls Remain Uncorrected")
    st.line_chart(sim_df[["Residual Risk Score"]])
    st.caption(
        f"Starting residual risk ≈ {start_risk:.0f} (driven by {open_count} open controls "
        f"and their severity mix). Risk compounds monthly under the selected growth factor."
    )

with tab2:
    st.markdown("#### Expected Cumulative Security Incidents")
    st.line_chart(sim_df[["Expected Cumulative Incidents"]])
    st.markdown("#### Expected Cumulative Direct Cost")
    st.line_chart(sim_df[["Expected Cumulative Cost ($)"]])

with tab3:
    st.markdown("#### Projected Mission Degradation Index")
    st.line_chart(sim_df[["Mission Degradation Index"]])
    st.caption(
        "Mission Degradation Index is a composite proxy for reduced operational availability, "
        "increased recovery time, and loss of confidence in system integrity / CMMC posture."
    )

with tab4:
    st.markdown("#### Monte Carlo Simulation of Total Incidents over Horizon")
    rng = np.random.default_rng(42)
    monthly_rates = effective_base_rate * (risk_growth ** np.arange(time_horizon))
    total_incidents = np.zeros(num_simulations)
    for i in range(num_simulations):
        incidents = rng.poisson(monthly_rates)
        total_incidents[i] = incidents.sum()

    hist_series = pd.Series(total_incidents).value_counts().sort_index()
    st.bar_chart(hist_series)

    mean_inc = float(np.mean(total_incidents))
    p5 = float(np.percentile(total_incidents, 5))
    p95 = float(np.percentile(total_incidents, 95))

    st.markdown(f"""
    **Summary Statistics (over {time_horizon} months)**  
    - Mean total incidents: **{mean_inc:.1f}**  
    - 5th percentile: **{p5:.1f}**  
    - 95th percentile: **{p95:.1f}**  
    - Expected direct cost (mean): **${mean_inc * avg_incident_cost:,.0f}**
    """)

# Key takeaways / BLUF box
st.markdown("---")
st.subheader("Key Takeaways (BLUF)")

level_note = {
    "CMMC Level 1": "Level 1 focuses on basic safeguarding of FCI (15 practices).",
    "CMMC Level 2": "Level 2 addresses protection of CUI (110 practices aligned to NIST SP 800-171).",
    "CMMC Level 3": "Level 3 adds enhanced protections against advanced persistent threats (134 practices)."
}.get(cmmc_level, "")

st.error(
    f"""
**If the {open_count} open controls for {cmmc_level} are not corrected:**

- Residual risk is projected to rise from ~{start_risk:.0f} to approximately **{risk_score[-1]:.0f}** within {time_horizon} months.
- Expected number of security incidents: **~{expected_incidents[-1]:.1f}**.
- Expected direct cost: **${expected_cost[-1]:,.0f}**.
- Mission degradation index could reach **{mission_deg[-1]:.0f}/100**, indicating substantial operational / compliance impact.
- {non_compliant_count} Non-Compliant and {partial_count} Partially Compliant findings drive the accelerated risk growth.
- {level_note}

**Recommendation:** Prioritize Critical/High Non-Compliant findings first, close or accept risk on Partially Compliant items with compensating controls, and accelerate POA&M closure.  
Delay increases both the likelihood and consequence of mission-impacting events and may jeopardize CMMC certification timelines.
"""
)

st.markdown("---")
st.caption(
    f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC | "
    "Notional model for illustration and decision-support purposes only. "
    "Does not constitute formal risk acceptance, POA&M, or certified CMMC assessment guidance."
)

# Navigation back
st.page_link("pages/02_Assessment.py", label="← Back to Assessment", icon="🛡️")
