import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
"""
Bottom Line Up Front (BLUF) Page
CMMC Level 1-3 | Non-Compliant & Partially Compliant Controls

Features:
  - Automatic ingest of open findings from Assessment page (st.session_state)
  - Risk / Incident / Cost / Mission Degradation modeling scaled by CMMC level
  - Monte Carlo simulation
  - Interactive Virtual Exploit Play-Through mapped to MITRE ATT&CK
"""

st.set_page_config(
    page_title="Bottom Line Up Front | CMMC",
    page_icon="⚠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Helper: Load findings pushed from Assessment page
# -----------------------------------------------------------------------------
def get_open_findings():
    """
    Prefer real findings pushed from the Assessment page.
    Fall back to a small illustrative sample so the page still works
    when opened directly.
    """
    findings = st.session_state.get("bluf_open_findings", None)
    cmmc_level = st.session_state.get("bluf_cmmc_level", "Level 1")
    framework = st.session_state.get("bluf_framework", "CMMC")

    if findings and isinstance(findings, list) and len(findings) > 0:
        normalized = []
        for f in findings:
            normalized.append({
                "Control ID": f.get("Control ID") or f.get("id") or f.get("control_id") or "Unknown",
                "Control Name": f.get("Control Name") or f.get("name") or f.get("control_name") or "",
                "Family": f.get("Family") or f.get("family") or "",
                "Severity": f.get("Severity") or f.get("severity") or "High",
                "Status": f.get("status") or f.get("Status") or "NON-COMPLIANT",
                "Finding": f.get("finding") or f.get("Finding") or f.get("description") or f.get("evidence_summary") or "",
                "Recommendation": f.get("recommendation") or f.get("Recommendation") or f.get("remediation") or "",
                "Days Open": f.get("Days Open") or f.get("days_open") or 30,
                "Related Assets": f.get("Related Assets") or f.get("assets") or "N/A"
            })
        return pd.DataFrame(normalized), cmmc_level, framework, True

    # ---------- Illustrative sample (used only when no real data) ----------
    sample = [
        {
            "Control ID": "AC.L1-3.1.1",
            "Control Name": "Limit information system access to authorized users",
            "Family": "Access Control",
            "Severity": "High",
            "Status": "NON-COMPLIANT",
            "Finding": "Privileged accounts not reviewed; orphaned accounts present",
            "Recommendation": "Implement 90-day privileged account review and disable unused accounts",
            "Days Open": 142,
            "Related Assets": "Identity Provider, Domain Controllers"
        },
        {
            "Control ID": "IA.L1-3.5.2",
            "Control Name": "Authenticate before granting access",
            "Family": "Identification and Authentication",
            "Severity": "High",
            "Status": "NON-COMPLIANT",
            "Finding": "MFA not enforced for all privileged and remote access paths",
            "Recommendation": "Enforce MFA on all privileged and remote sessions",
            "Days Open": 203,
            "Related Assets": "VPN, Privileged Access Workstations"
        },
        {
            "Control ID": "SI.L1-3.14.2",
            "Control Name": "Provide protection from malicious code",
            "Family": "System and Information Integrity",
            "Severity": "Critical",
            "Status": "NON-COMPLIANT",
            "Finding": "Critical/high CVEs older than 30 days remain unpatched",
            "Recommendation": "Establish 30-day remediation SLA for critical/high vulnerabilities",
            "Days Open": 54,
            "Related Assets": "Application Servers, Database Tier"
        },
        {
            "Control ID": "SC.L1-3.13.1",
            "Control Name": "Monitor and control communications at external boundaries",
            "Family": "System and Communications Protection",
            "Severity": "High",
            "Status": "PARTIALLY COMPLIANT",
            "Finding": "Inbound/outbound filtering gaps; legacy rules present",
            "Recommendation": "Review and harden boundary firewall rules; remove unused allow rules",
            "Days Open": 115,
            "Related Assets": "Firewalls, Boundary Routers"
        },
        {
            "Control ID": "MP.L1-3.8.3",
            "Control Name": "Control the use of removable media",
            "Family": "Media Protection",
            "Severity": "Moderate",
            "Status": "NON-COMPLIANT",
            "Finding": "USB write access not restricted on workstations handling CUI",
            "Recommendation": "Enforce device control policy blocking unauthorized USB write",
            "Days Open": 67,
            "Related Assets": "Workstations, File Servers"
        },
        {
            "Control ID": "AU.L2-3.3.1",
            "Control Name": "Create and retain system audit logs",
            "Family": "Audit and Accountability",
            "Severity": "High",
            "Status": "PARTIALLY COMPLIANT",
            "Finding": "Critical security events not fully captured on several systems",
            "Recommendation": "Enable advanced auditing and forward all security logs to SIEM",
            "Days Open": 89,
            "Related Assets": "SIEM, Endpoint Agents"
        },
        {
            "Control ID": "CP.L2-3.6.1",
            "Control Name": "Establish contingency plan",
            "Family": "Contingency Planning",
            "Severity": "High",
            "Status": "NON-COMPLIANT",
            "Finding": "Backup restoration testing not performed within required frequency",
            "Recommendation": "Conduct quarterly restore tests and document results",
            "Days Open": 78,
            "Related Assets": "Backup Infrastructure"
        }
    ]
    return pd.DataFrame(sample), "Level 1", "CMMC", False


df, cmmc_level, framework, is_real_data = get_open_findings()

# -----------------------------------------------------------------------------
# Sidebar – Simulation Parameters
# -----------------------------------------------------------------------------
st.sidebar.header("Simulation Parameters")
st.sidebar.markdown(
    "Adjust assumptions to model consequences of **not correcting** "
    "the open (Non-Compliant / Partially Compliant) controls."
)

time_horizon = st.sidebar.slider("Time Horizon (months)", 3, 36, 12)
base_incident_rate = st.sidebar.slider(
    "Base Monthly Incident Rate (if uncorrected)", 0.05, 1.5, 0.35, 0.05
)
risk_growth = st.sidebar.slider("Monthly Risk Growth Factor", 1.01, 1.25, 1.08, 0.01)
avg_incident_cost = st.sidebar.number_input(
    "Average Cost per Incident ($)", 50_000, 5_000_000, 450_000, 25_000
)
mission_impact_weight = st.sidebar.slider("Mission Impact Multiplier", 1.0, 5.0, 2.2, 0.1)
num_simulations = st.sidebar.slider("Monte Carlo Runs", 100, 2000, 500, 100)

# Scale intensity by CMMC level size (rough proxy)
level_multiplier = {
    "Level 1": 1.0,
    "Level 2": 1.6,
    "Level 3": 2.1,
    "CMMC Level 1": 1.0,
    "CMMC Level 2": 1.6,
    "CMMC Level 3": 2.1,
}.get(str(cmmc_level), 1.0)

st.sidebar.markdown("---")
st.sidebar.info(
    f"**Framework:** {framework}  \n"
    f"**Level:** {cmmc_level}  \n"
    f"**Open findings loaded:** {len(df)}  \n"
    f"{'✅ Real data from Assessment' if is_real_data else '⚠️ Illustrative sample data'}"
)
st.sidebar.caption(
    "This is a notional decision-support model. "
    "It does not replace formal risk assessment or ATO processes."
)

# -----------------------------------------------------------------------------
# Main Title
# -----------------------------------------------------------------------------
st.title("⚠️ Bottom Line Up Front")
st.subheader(f"Non-Compliant & Partially Compliant Controls — {framework} {cmmc_level}")

if not is_real_data:
    st.warning(
        "No findings were pushed from the Assessment page. "
        "Showing illustrative sample data so you can explore the modeling features. "
        "Run an assessment and click the **BLUF** button to load real results."
    )

# -----------------------------------------------------------------------------
# Summary Metrics
# -----------------------------------------------------------------------------

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Open Findings", len(df))
with col2:
    critical_high = len(df[df["Severity"].isin(["Critical", "High"])]) if len(df) else 0
    st.metric("Critical / High", critical_high)
with col3:
    non_comp = len(df[df["Status"].str.contains("NON-COMPLIANT", case=False, na=False)]) if len(df) else 0
    st.metric("Non-Compliant", non_comp)
with col4:
    partial = len(df[df["Status"].str.contains("PARTIALLY", case=False, na=False)]) if len(df) else 0
    st.metric("Partially Compliant", partial)
with col5:
    avg_days = int(df["Days Open"].mean()) if len(df) > 0 else 0
    st.metric("Avg Days Open", avg_days)

st.markdown("---")

# -----------------------------------------------------------------------------
# Open Findings Table
# -----------------------------------------------------------------------------
st.markdown("### Open Control Findings (Non-Compliant + Partially Compliant)")
if len(df) > 0:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Finding": st.column_config.TextColumn("Finding", width="large"),
            "Recommendation": st.column_config.TextColumn("Recommendation", width="large"),
        }
    )
else:
    st.info("No open findings to display.")

# Severity distribution
if len(df) > 0:
    st.markdown("### Severity Distribution")
    sev_order = ["Critical", "High", "Moderate", "Low"]
    sev_counts = df["Severity"].value_counts().reindex(sev_order).fillna(0)
    st.bar_chart(sev_counts)

st.markdown("---")

# -----------------------------------------------------------------------------
# Modeling & Simulation
# -----------------------------------------------------------------------------
st.header("Modeling & Simulation: Consequences of Inaction")
st.markdown(
    """
    This section projects what is likely to occur if the open controls above remain uncorrected.
    Intensity is scaled by the number of open findings, their severity mix, and the CMMC level.
    """
)

# Deterministic trajectories
months = np.arange(0, time_horizon + 1)
open_count = max(len(df), 1)
severity_boost = 1.0 + (critical_high / open_count) * 0.4

risk_score = 30 * (risk_growth ** months) * level_multiplier * severity_boost
risk_score = np.clip(risk_score, 0, 100)

intensity = base_incident_rate * (risk_growth ** months) * level_multiplier * (open_count / 5.0)
expected_incidents = np.cumsum(intensity)
expected_cost = expected_incidents * avg_incident_cost
mission_deg = 100 * (1 - np.exp(-0.012 * expected_incidents * mission_impact_weight * severity_boost))

sim_df = pd.DataFrame({
    "Month": months,
    "Residual Risk Score": risk_score,
    "Expected Cumulative Incidents": expected_incidents,
    "Expected Cumulative Cost ($)": expected_cost,
    "Mission Degradation Index": mission_deg
}).set_index("Month")

tab1, tab2, tab3, tab4 = st.tabs([
    "Risk Trajectory",
    "Expected Incidents & Cost",
    "Mission Impact",
    "Monte Carlo Distribution"
])

with tab1:
    st.markdown("#### Projected Residual Risk Score if Controls Remain Open")
    st.line_chart(sim_df[["Residual Risk Score"]])
    st.caption(
        "Risk compounds as unmitigated weaknesses (unpatched systems, weak authentication, "
        "boundary gaps, missing audit coverage, etc.) accumulate."
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
        "increased recovery time, and loss of confidence in system integrity."
    )

with tab4:
    st.markdown("#### Monte Carlo Simulation of Total Incidents over Horizon")
    rng = np.random.default_rng(42)
    monthly_rates = (
        base_incident_rate
        * (risk_growth ** np.arange(time_horizon))
        * level_multiplier
        * (open_count / 5.0)
    )
    total_incidents = np.array([
        rng.poisson(monthly_rates).sum() for _ in range(num_simulations)
    ])

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

# -----------------------------------------------------------------------------
# Key Takeaways
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("Key Takeaways (BLUF)")
st.error(
    f"""
**If the {len(df)} open control(s) are not corrected:**

- Residual risk is projected to rise to approximately **{risk_score[-1]:.0f}/100** within {time_horizon} months.
- Expected number of security incidents: **~{expected_incidents[-1]:.1f}**.
- Expected direct cost: **${expected_cost[-1]:,.0f}**.
- Mission degradation index could reach **{mission_deg[-1]:.0f}/100**, indicating substantial operational impact.
- Critical / High severity findings are the primary drivers of accelerated risk growth.

**Recommendation:** Prioritize remediation of Critical and High findings and accelerate POA&M closure.  
Delay increases both the likelihood and the consequence of mission-impacting events.
"""
)

st.markdown("---")

# =============================================================================
# VIRTUAL EXPLOIT PLAY-THROUGH  (MITRE ATT&CK mapped)
# =============================================================================
st.header("🎮 Virtual Exploit Play-Through")
st.markdown(
    """
    Select an open control to walk through a realistic, stage-by-stage simulation of what 
    happens to the network **if that control is exploited**. Every stage is mapped to the 
    **MITRE ATT&CK** framework (Tactic + Technique).
    """
)

if len(df) == 0:
    st.info("No open findings available for play-through.")
else:
    # Build selector labels
    control_options = [
        f"{row['Control ID']}  |  {row['Status']}  |  {row['Severity']}"
        for _, row in df.iterrows()
    ]
    selected_label = st.selectbox(
        "Select a control to simulate exploitation:",
        options=control_options,
        key="playthrough_selector"
    )
    selected_idx = control_options.index(selected_label)
    selected = df.iloc[selected_idx]

    # ------------------------------------------------------------------
    # ATT&CK scenario library (keyed by family / control prefix)
    # ------------------------------------------------------------------
    def build_attack_scenario(control_id: str, severity: str, finding: str):
        cid = str(control_id).upper()
        sev_multiplier = {"Critical": 1.4, "High": 1.2, "Moderate": 1.0, "Low": 0.8}.get(str(severity), 1.0)

        # Default generic path
        scenario = {
            "title": "Generic Control Failure Exploitation",
            "initial_access": "Adversary identifies and abuses the unremediated control gap.",
            "primary_tactics": ["Initial Access", "Execution", "Impact"],
            "stages": [
                {
                    "name": "Initial Access",
                    "tactic": "Initial Access",
                    "technique": "T1190 – Exploit Public-Facing Application / T1078 – Valid Accounts",
                    "action": "Adversary locates the exposed weakness described in the finding.",
                    "network_path": "Internet → Boundary → Target system",
                    "defender_miss": "The open control left the attack surface unmonitored or unhardened."
                },
                {
                    "name": "Execution & Persistence",
                    "tactic": "Execution / Persistence",
                    "technique": "T1059 – Command and Scripting Interpreter / T1547 – Boot or Logon Autostart",
                    "action": "Malicious code or elevated session is established.",
                    "network_path": "Compromised host → Internal network",
                    "defender_miss": "Missing detection or least-privilege controls allowed execution."
                },
                {
                    "name": "Lateral Movement",
                    "tactic": "Lateral Movement",
                    "technique": "T1021 – Remote Services / T1570 – Lateral Tool Transfer",
                    "action": "Adversary moves to higher-value systems using harvested credentials or trusts.",
                    "network_path": "Workstation → File Server / Domain Controller",
                    "defender_miss": "Insufficient network segmentation and monitoring."
                },
                {
                    "name": "Impact",
                    "tactic": "Impact",
                    "technique": "T1486 – Data Encrypted for Impact / T1041 – Exfiltration Over C2",
                    "action": "Data is encrypted, destroyed, or exfiltrated; mission functions degraded.",
                    "network_path": "Critical systems → External C2 or ransomware note",
                    "defender_miss": "Lack of rapid containment and recovery capability."
                }
            ],
            "systems_affected": ["Workstations", "File Servers", "Domain Controllers"],
            "data_at_risk": "CUI / FCI / credentials",
            "detection_likelihood": "Low–Moderate",
            "time_to_compromise": "Hours to days",
            "est_systems": int(8 * sev_multiplier),
            "est_cost": int(320_000 * sev_multiplier),
            "est_downtime_hrs": int(36 * sev_multiplier)
        }

        # Family-specific overrides
        if any(x in cid for x in ["AC.", "AC-"]):
            scenario.update({
                "title": "Privilege Abuse / Orphaned Account Exploitation",
                "initial_access": "Adversary uses an unreviewed or orphaned privileged account.",
                "primary_tactics": ["Initial Access", "Privilege Escalation", "Lateral Movement", "Impact"],
                "stages": [
                    {
                        "name": "Initial Access – Valid Accounts",
                        "tactic": "Initial Access",
                        "technique": "T1078 – Valid Accounts",
                        "action": "Logon with an orphaned or overly privileged account that was never disabled.",
                        "network_path": "VPN / Console → Domain",
                        "defender_miss": "Account management (AC) review cycle not performed."
                    },
                    {
                        "name": "Privilege Escalation",
                        "tactic": "Privilege Escalation",
                        "technique": "T1078.002 – Domain Accounts / T1134 – Access Token Manipulation",
                        "action": "Adversary elevates to Domain Admin or equivalent using the privileged account.",
                        "network_path": "Domain Controller",
                        "defender_miss": "Excessive privileges and missing just-in-time access."
                    },
                    {
                        "name": "Lateral Movement & Discovery",
                        "tactic": "Lateral Movement / Discovery",
                        "technique": "T1021.002 – SMB/Windows Admin Shares / T1087 – Account Discovery",
                        "action": "Enumeration of shares, users, and sensitive data stores.",
                        "network_path": "DC → File Servers → Workstations",
                        "defender_miss": "No behavioral monitoring on privileged sessions."
                    },
                    {
                        "name": "Impact – Data Access / Destruction",
                        "tactic": "Impact / Collection",
                        "technique": "T1005 – Data from Local System / T1485 – Data Destruction",
                        "action": "Sensitive data accessed, staged, or destroyed.",
                        "network_path": "File servers holding CUI",
                        "defender_miss": "Missing least-privilege and data-loss prevention."
                    }
                ],
                "systems_affected": ["Domain Controllers", "File Servers", "Privileged Workstations"],
                "data_at_risk": "Domain credentials, CUI, administrative secrets",
                "detection_likelihood": "Low (trusted account)",
                "time_to_compromise": "Minutes to hours",
                "est_systems": int(12 * sev_multiplier),
                "est_cost": int(480_000 * sev_multiplier),
                "est_downtime_hrs": int(48 * sev_multiplier)
            })

        elif any(x in cid for x in ["IA.", "IA-"]):
            scenario.update({
                "title": "Authentication Bypass / MFA Failure Exploitation",
                "initial_access": "Adversary authenticates without required multi-factor controls.",
                "primary_tactics": ["Initial Access", "Credential Access", "Lateral Movement"],
                "stages": [
                    {
                        "name": "Initial Access – MFA Bypass",
                        "tactic": "Initial Access",
                        "technique": "T1078 – Valid Accounts / T1556 – Modify Authentication Process",
                        "action": "Password-only or legacy authentication path is used because MFA is not enforced.",
                        "network_path": "Internet → VPN / OWA / RDP gateway",
                        "defender_miss": "IA control requiring MFA not implemented on all paths."
                    },
                    {
                        "name": "Credential Access",
                        "tactic": "Credential Access",
                        "technique": "T1003 – OS Credential Dumping / T1555 – Credentials from Password Stores",
                        "action": "Credentials harvested from the initially compromised session.",
                        "network_path": "Compromised host memory / LSASS",
                        "defender_miss": "No credential-guard or privileged-access workstation controls."
                    },
                    {
                        "name": "Lateral Movement",
                        "tactic": "Lateral Movement",
                        "technique": "T1021 – Remote Services",
                        "action": "Re-use of harvested credentials to reach internal systems.",
                        "network_path": "VPN host → Internal servers",
                        "defender_miss": "Missing network segmentation and MFA for lateral movement."
                    },
                    {
                        "name": "Impact",
                        "tactic": "Impact",
                        "technique": "T1486 – Data Encrypted for Impact / T1048 – Exfiltration Over Alternative Protocol",
                        "action": "Ransomware deployment or data exfiltration.",
                        "network_path": "Critical servers → External",
                        "defender_miss": "Delayed detection due to trusted authentication path."
                    }
                ],
                "systems_affected": ["VPN concentrators", "Remote access hosts", "Internal servers"],
                "data_at_risk": "User credentials, session tokens, CUI",
                "detection_likelihood": "Low–Moderate",
                "time_to_compromise": "Hours",
                "est_systems": int(10 * sev_multiplier),
                "est_cost": int(410_000 * sev_multiplier),
                "est_downtime_hrs": int(40 * sev_multiplier)
            })

        elif any(x in cid for x in ["SI.", "SI-"]):
            scenario.update({
                "title": "Unpatched Vulnerability / Malicious Code Exploitation",
                "initial_access": "Publicly known CVE on an unpatched system is exploited.",
                "primary_tactics": ["Initial Access", "Execution", "Persistence", "Impact"],
                "stages": [
                    {
                        "name": "Initial Access – Exploit Public-Facing / Client",
                        "tactic": "Initial Access",
                        "technique": "T1190 – Exploit Public-Facing Application / T1203 – Exploitation for Client Execution",
                        "action": "Exploit of a critical/high CVE that exceeded the remediation SLA.",
                        "network_path": "Internet → Vulnerable application / endpoint",
                        "defender_miss": "Flaw remediation (SI) control not met; patching delayed."
                    },
                    {
                        "name": "Execution & Defense Evasion",
                        "tactic": "Execution / Defense Evasion",
                        "technique": "T1059 – Command and Scripting Interpreter / T1218 – System Binary Proxy Execution",
                        "action": "Payload executed; security tools disabled or bypassed.",
                        "network_path": "Compromised host",
                        "defender_miss": "Real-time protection or application control gaps."
                    },
                    {
                        "name": "Persistence & Privilege Escalation",
                        "tactic": "Persistence / Privilege Escalation",
                        "technique": "T1547 – Boot or Logon Autostart Execution / T1068 – Exploitation for Privilege Escalation",
                        "action": "Persistence mechanism installed; privileges elevated.",
                        "network_path": "Local system → Domain if possible",
                        "defender_miss": "Missing host hardening and least privilege."
                    },
                    {
                        "name": "Impact – Ransomware / Data Destruction",
                        "tactic": "Impact",
                        "technique": "T1486 – Data Encrypted for Impact / T1490 – Inhibit System Recovery",
                        "action": "Encryption of data stores and deletion of backups/shadow copies.",
                        "network_path": "File servers, databases, backups",
                        "defender_miss": "Unpatched systems + incomplete backup testing."
                    }
                ],
                "systems_affected": ["Application servers", "Workstations", "Database tier"],
                "data_at_risk": "Application data, CUI, system integrity",
                "detection_likelihood": "Moderate (if EDR present) / Low (if disabled)",
                "time_to_compromise": "Minutes to hours after exploit",
                "est_systems": int(15 * sev_multiplier),
                "est_cost": int(620_000 * sev_multiplier),
                "est_downtime_hrs": int(72 * sev_multiplier)
            })

        elif any(x in cid for x in ["SC.", "SC-"]):
            scenario.update({
                "title": "Boundary Protection Failure / Network Filtering Bypass",
                "initial_access": "Adversary traverses weak or legacy boundary rules.",
                "primary_tactics": ["Initial Access", "Command and Control", "Lateral Movement", "Exfiltration"],
                "stages": [
                    {
                        "name": "Initial Access – Boundary Bypass",
                        "tactic": "Initial Access",
                        "technique": "T1190 – Exploit Public-Facing Application / T1133 – External Remote Services",
                        "action": "Inbound connection allowed by overly permissive or legacy firewall rule.",
                        "network_path": "Internet → Boundary firewall → DMZ / Internal",
                        "defender_miss": "SC boundary protection rules not reviewed or hardened."
                    },
                    {
                        "name": "Command and Control",
                        "tactic": "Command and Control",
                        "technique": "T1071 – Application Layer Protocol / T1572 – Protocol Tunneling",
                        "action": "C2 channel established through permitted outbound ports.",
                        "network_path": "Compromised host → External C2",
                        "defender_miss": "Insufficient egress filtering and protocol inspection."
                    },
                    {
                        "name": "Lateral Movement",
                        "tactic": "Lateral Movement",
                        "technique": "T1021 – Remote Services / T1210 – Exploitation of Remote Services",
                        "action": "Movement deeper into the network from the initially reached segment.",
                        "network_path": "DMZ → Internal servers",
                        "defender_miss": "Flat network or missing micro-segmentation."
                    },
                    {
                        "name": "Exfiltration",
                        "tactic": "Exfiltration",
                        "technique": "T1041 – Exfiltration Over C2 Channel / T1048 – Exfiltration Over Alternative Protocol",
                        "action": "Sensitive data transferred out through the same weak boundary.",
                        "network_path": "Internal → Boundary → Internet",
                        "defender_miss": "No DLP or anomalous egress detection."
                    }
                ],
                "systems_affected": ["Boundary firewalls", "DMZ hosts", "Internal servers"],
                "data_at_risk": "Any data reachable from the breached segment",
                "detection_likelihood": "Low–Moderate",
                "time_to_compromise": "Hours",
                "est_systems": int(11 * sev_multiplier),
                "est_cost": int(390_000 * sev_multiplier),
                "est_downtime_hrs": int(36 * sev_multiplier)
            })

        elif any(x in cid for x in ["MP.", "MP-"]):
            scenario.update({
                "title": "Removable Media / Data Theft via USB",
                "initial_access": "Unauthorized USB device used to remove or introduce data.",
                "primary_tactics": ["Initial Access", "Collection", "Exfiltration"],
                "stages": [
                    {
                        "name": "Initial Access – Removable Media",
                        "tactic": "Initial Access",
                        "technique": "T1091 – Replication Through Removable Media",
                        "action": "USB device connected to a workstation that lacks device-control policy.",
                        "network_path": "Physical USB → Workstation",
                        "defender_miss": "MP control restricting removable media not enforced."
                    },
                    {
                        "name": "Collection",
                        "tactic": "Collection",
                        "technique": "T1005 – Data from Local System / T1039 – Data from Network Shared Drive",
                        "action": "Sensitive files copied to the removable device.",
                        "network_path": "Local disk / mapped shares → USB",
                        "defender_miss": "No endpoint DLP or USB write blocking."
                    },
                    {
                        "name": "Exfiltration (Physical)",
                        "tactic": "Exfiltration",
                        "technique": "T1052 – Exfiltration Over Physical Medium",
                        "action": "Device removed from the facility with CUI.",
                        "network_path": "Workstation → Physical removal",
                        "defender_miss": "Missing physical and logical media controls."
                    },
                    {
                        "name": "Impact – Data Loss / Introduction of Malware",
                        "tactic": "Impact",
                        "technique": "T1485 – Data Destruction (or malware introduction)",
                        "action": "Data leaves the organization or malware is introduced on next insertion.",
                        "network_path": "External / other networks",
                        "defender_miss": "No inventory or scanning of removable media."
                    }
                ],
                "systems_affected": ["Workstations handling CUI", "File shares"],
                "data_at_risk": "CUI / FCI stored on endpoints or accessible shares",
                "detection_likelihood": "Low (physical vector)",
                "time_to_compromise": "Minutes",
                "est_systems": int(4 * sev_multiplier),
                "est_cost": int(180_000 * sev_multiplier),
                "est_downtime_hrs": int(12 * sev_multiplier)
            })

        elif any(x in cid for x in ["AU.", "AU-"]):
            scenario.update({
                "title": "Audit Failure – Covering Tracks & Undetected Activity",
                "initial_access": "Adversary operates knowing critical events are not logged or reviewed.",
                "primary_tactics": ["Defense Evasion", "Persistence", "Impact"],
                "stages": [
                    {
                        "name": "Defense Evasion – Impair Defenses",
                        "tactic": "Defense Evasion",
                        "technique": "T1562.002 – Impair Defenses: Disable Windows Event Logging / T1070 – Indicator Removal",
                        "action": "Adversary clears or avoids generating audit events on systems with incomplete logging.",
                        "network_path": "Compromised host",
                        "defender_miss": "AU controls for audit generation and retention not fully implemented."
                    },
                    {
                        "name": "Persistence without Detection",
                        "tactic": "Persistence",
                        "technique": "T1547 – Boot or Logon Autostart Execution",
                        "action": "Persistence installed; no corresponding audit trail reaches the SIEM.",
                        "network_path": "Local system",
                        "defender_miss": "Missing advanced auditing and log forwarding."
                    },
                    {
                        "name": "Long-dwell Lateral Movement",
                        "tactic": "Lateral Movement",
                        "technique": "T1021 – Remote Services",
                        "action": "Quiet movement across the network over days/weeks.",
                        "network_path": "Multiple internal hosts",
                        "defender_miss": "No reliable authentication or process creation logs."
                    },
                    {
                        "name": "Impact – Delayed Discovery",
                        "tactic": "Impact",
                        "technique": "T1486 – Data Encrypted for Impact / T1041 – Exfiltration",
                        "action": "Final impact occurs long after initial compromise; forensics hampered.",
                        "network_path": "Critical data stores",
                        "defender_miss": "Inability to reconstruct the attack timeline."
                    }
                ],
                "systems_affected": ["Any system with incomplete audit policy", "SIEM coverage gaps"],
                "data_at_risk": "All data on systems lacking reliable audit trails",
                "detection_likelihood": "Very Low",
                "time_to_compromise": "Days to weeks (dwell time)",
                "est_systems": int(14 * sev_multiplier),
                "est_cost": int(550_000 * sev_multiplier),
                "est_downtime_hrs": int(96 * sev_multiplier)
            })

        elif any(x in cid for x in ["CP.", "CP-"]):
            scenario.update({
                "title": "Contingency / Backup Failure – Recovery Impossible",
                "initial_access": "Adversary destroys or encrypts data knowing backups are untested or incomplete.",
                "primary_tactics": ["Impact", "Inhibit System Recovery"],
                "stages": [
                    {
                        "name": "Impact – Data Encryption / Destruction",
                        "tactic": "Impact",
                        "technique": "T1486 – Data Encrypted for Impact",
                        "action": "Ransomware or destructive malware targets production data.",
                        "network_path": "Production servers",
                        "defender_miss": "Primary impact; recovery path is the control failure."
                    },
                    {
                        "name": "Inhibit System Recovery",
                        "tactic": "Impact",
                        "technique": "T1490 – Inhibit System Recovery",
                        "action": "Shadow copies, backups, and recovery environments are deleted or encrypted.",
                        "network_path": "Backup repositories / recovery servers",
                        "defender_miss": "Backup systems not isolated or immutable."
                    },
                    {
                        "name": "Failed Restore Attempt",
                        "tactic": "Impact",
                        "technique": "T1490 – Inhibit System Recovery (continued)",
                        "action": "Restore testing has not been performed; backups are incomplete or corrupt.",
                        "network_path": "Backup infrastructure → Failed recovery",
                        "defender_miss": "CP control requiring regular restore testing not met."
                    },
                    {
                        "name": "Prolonged Mission Outage",
                        "tactic": "Impact",
                        "technique": "T1496 – Resource Hijacking / business impact",
                        "action": "Extended downtime while data is rebuilt from other sources or paid ransom.",
                        "network_path": "Entire mission capability",
                        "defender_miss": "No validated contingency capability."
                    }
                ],
                "systems_affected": ["Production servers", "Backup infrastructure", "Recovery environment"],
                "data_at_risk": "All data dependent on the untested backups",
                "detection_likelihood": "High (impact is obvious) but recovery fails",
                "time_to_compromise": "Hours (impact) + days/weeks (recovery)",
                "est_systems": int(20 * sev_multiplier),
                "est_cost": int(1_100_000 * sev_multiplier),
                "est_downtime_hrs": int(168 * sev_multiplier)
            })

        return scenario

    scenario = build_attack_scenario(
        selected["Control ID"],
        selected["Severity"],
        selected["Finding"]
    )

    # ------------------------------------------------------------------
    # Scenario Header
    # ------------------------------------------------------------------
    st.markdown(f"### {scenario['title']}")
    st.markdown(
        f"**Control:** `{selected['Control ID']}` &nbsp;|&nbsp; "
        f"**Status:** {selected['Status']} &nbsp;|&nbsp; "
        f"**Severity:** {selected['Severity']}"
    )
    st.markdown(f"**Finding snapshot:** {selected['Finding']}")
    st.markdown(f"**Initial Access Vector:** {scenario['initial_access']}")
    st.markdown(
        "**Primary MITRE ATT&CK Tactics:** "
        + " → ".join(f"`{t}`" for t in scenario["primary_tactics"])
    )

    # ------------------------------------------------------------------
    # Stage-by-stage navigation
    # ------------------------------------------------------------------
    stages = scenario["stages"]
    n_stages = len(stages)

    if "play_stage" not in st.session_state:
        st.session_state.play_stage = 0
    # Reset stage when control changes
    if st.session_state.get("last_play_control") != selected["Control ID"]:
        st.session_state.play_stage = 0
        st.session_state.last_play_control = selected["Control ID"]

    current = st.session_state.play_stage

    # Progress
    st.progress((current + 1) / n_stages)
    st.caption(f"Stage {current + 1} of {n_stages}")

    # Navigation buttons
    nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 3])
    with nav1:
        if st.button("⏮ Reset", use_container_width=True):
            st.session_state.play_stage = 0
            st.rerun()
    with nav2:
        if st.button("◀ Previous", use_container_width=True, disabled=(current <= 0)):
            st.session_state.play_stage = max(0, current - 1)
            st.rerun()
    with nav3:
        if st.button("Next Stage ▶", use_container_width=True, disabled=(current >= n_stages - 1)):
            st.session_state.play_stage = min(n_stages - 1, current + 1)
            st.rerun()

    # Display stages up to current (expanders)
    for i, stage in enumerate(stages):
        is_current = (i == current)
        label = f"{'▶️ ' if is_current else ''}{stage['name']}"
        with st.expander(label, expanded=is_current):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**MITRE Tactic**  \n`{stage['tactic']}`")
            with c2:
                st.markdown(f"**MITRE Technique**  \n`{stage['technique']}`")
            st.markdown(f"**Adversary Action**  \n{stage['action']}")
            st.markdown(f"**Network Path**  \n`{stage['network_path']}`")
            st.markdown(f"**What the Defender Missed**  \n{stage['defender_miss']}")

    if current >= n_stages - 1:
        st.success(
            "✅ Full impact stage reached. "
            "This concludes the simulated kill chain for the selected control."
        )

    # ------------------------------------------------------------------
    # Impact Summary
    # ------------------------------------------------------------------
    st.markdown("#### Network & Mission Impact Summary")
    impact_df = pd.DataFrame([
        {"Attribute": "Systems Likely Affected", "Value": ", ".join(scenario["systems_affected"])},
        {"Attribute": "Data at Risk", "Value": scenario["data_at_risk"]},
        {"Attribute": "Detection Likelihood", "Value": scenario["detection_likelihood"]},
        {"Attribute": "Typical Time-to-Compromise", "Value": scenario["time_to_compromise"]},
        {"Attribute": "Primary CMMC Gap", "Value": selected["Control ID"]},
    ])
    st.table(impact_df)

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Est. Systems Touched", scenario["est_systems"])
    with m2:
        st.metric("Est. Direct Cost", f"${scenario['est_cost']:,}")
    with m3:
        st.metric("Est. Downtime (hours)", scenario["est_downtime_hrs"])

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  "
    "Notional model for illustration and decision-support purposes only.  "
    "Does not constitute formal risk acceptance, ATO guidance, or operational direction.  "
    "MITRE ATT&CK® is a registered trademark of The MITRE Corporation."
)
