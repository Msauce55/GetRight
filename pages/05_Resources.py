#Input how to and CMMC information for customers
import streamlit as st
import pandas as pd
import io

# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="CMMC Resources",
    page_icon="📚",
    layout="wide"
)

# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("📚 Cybersecurity & CMMC Resources")
st.write(
    "Use the resources below to learn about CMMC requirements "
    "and collect cybersecurity logs from common operating systems."
)

st.divider()

# =========================================================
# CMMC RESOURCES
# =========================================================

st.header("🛡️ CMMC Resources")
st.write(
    "The Cybersecurity Maturity Model Certification (CMMC) "
    "establishes cybersecurity requirements for organizations "
    "that work with Federal Contract Information (FCI) and "
    "Controlled Unclassified Information (CUI)."
)

# ---------------------------------------------------------
# CMMC LEVEL BUTTONS
# ---------------------------------------------------------

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("🟢 CMMC Level 1", use_container_width=True):
        st.session_state["show_cmmc_level"] = 1

with col2:
    if st.button("🟡 CMMC Level 2", use_container_width=True):
        st.session_state["show_cmmc_level"] = 2

with col3:
    if st.button("🔴 CMMC Level 3", use_container_width=True):
        st.session_state["show_cmmc_level"] = 3


# ---------------------------------------------------------
# CMMC LEVEL INFORMATION
# ---------------------------------------------------------

level = st.session_state.get("show_cmmc_level", None)

if level == 1:

    st.subheader("🟢 CMMC Level 1 — Foundational")

    st.markdown("""
    **Purpose**

    CMMC Level 1 is designed primarily for organizations that
    handle **Federal Contract Information (FCI)**.

    **Security Focus**

    Level 1 focuses on basic cybersecurity hygiene and requires
    organizations to implement the applicable security practices
    derived from **FAR 52.204-21**.

    **Examples of Security Practices**

    - Limit system access to authorized users
    - Control external system connections
    - Identify and authenticate users
    - Protect system communications
    - Perform basic system monitoring
    - Maintain appropriate security protections
    - Protect information from unauthorized access

    **Assessment**

    Level 1 generally involves an annual self-assessment.

    **Typical Organizations**

    - Small defense contractors
    - Subcontractors handling FCI
    - Organizations that do not process CUI
    """)

    st.info(
        "Level 1 is primarily focused on basic safeguarding of "
        "Federal Contract Information (FCI)."
    )


elif level == 2:

    st.subheader("🟡 CMMC Level 2 — Advanced")

    st.markdown("""
    **Purpose**

    CMMC Level 2 applies to organizations that handle
    **Controlled Unclassified Information (CUI)**.

    Level 2 aligns with the security requirements in
    **NIST SP 800-171**.

    **Security Focus**

    Organizations must implement the applicable NIST SP 800-171
    security requirements across areas such as:

    - Access Control
    - Awareness and Training
    - Audit and Accountability
    - Configuration Management
    - Identification and Authentication
    - Incident Response
    - Maintenance
    - Media Protection
    - Personnel Security
    - Physical Protection
    - Risk Assessment
    - Security Assessment
    - System and Communications Protection
    - System and Information Integrity

    **Assessment**

    Depending on the contract and applicable requirements,
    organizations may undergo either a self-assessment or
    a third-party assessment.

    **Typical Organizations**

    - Defense contractors handling CUI
    - Manufacturing contractors
    - Engineering organizations
    - Technology contractors
    - Subcontractors processing CUI
    """)

    st.info(
        "Level 2 is centered around protecting CUI and "
        "implementing NIST SP 800-171 security requirements."
    )


elif level == 3:

    st.subheader("🔴 CMMC Level 3 — Expert")

    st.markdown("""
    **Purpose**

    CMMC Level 3 is intended for organizations handling
    particularly sensitive CUI associated with contracts
    involving higher cybersecurity risk.

    **Security Focus**

    Level 3 builds upon the requirements of Level 2 and
    incorporates additional protections derived from
    **NIST SP 800-172**.

    Additional emphasis is placed on:

    - Advanced threat protection
    - Continuous monitoring
    - Advanced incident response
    - Threat hunting
    - System resilience
    - Protection against sophisticated cyber threats
    - Advanced access control
    - Security architecture
    - Cybersecurity risk management

    **Assessment**

    Level 3 requires a higher level of assessment rigor and
    is intended for organizations facing sophisticated
    cybersecurity threats.

    **Typical Organizations**

    - Major defense contractors
    - Organizations handling highly sensitive CUI
    - Organizations supporting high-priority defense programs
    - Organizations targeted by advanced persistent threats
    """)

    st.warning(
        "Level 3 represents the highest CMMC maturity level and "
        "is intended for organizations facing advanced threats."
    )


st.divider()

# =========================================================
# CYBERSECURITY LOG COLLECTION
# =========================================================

st.header("💻 Cybersecurity Log Collection")

st.write(
    "Use the resources below to collect operating-system logs "
    "for cybersecurity assessments, incident response, "
    "auditing, and compliance documentation."
)

st.warning(
    "Run commands with appropriate administrative privileges. "
    "Only collect logs from systems you are authorized to assess."
)

# ---------------------------------------------------------
# OPERATING SYSTEM BUTTONS
# ---------------------------------------------------------

os1, os2, os3 = st.columns(3)

with os1:
    if st.button("🪟 Windows", use_container_width=True):
        st.session_state["show_os"] = "Windows"

with os2:
    if st.button("🐧 Linux", use_container_width=True):
        st.session_state["show_os"] = "Linux"

with os3:
    if st.button("🍎 macOS", use_container_width=True):
        st.session_state["show_os"] = "macOS"


operating_system = st.session_state.get("show_os", None)


# =========================================================
# WINDOWS
# =========================================================

if operating_system == "Windows":

    st.subheader("🪟 Windows Log Collection")

    st.markdown("""
    Windows stores many important cybersecurity events in the
    **Windows Event Log** system.

    Common logs include:

    - Security
    - System
    - Application
    - Windows Defender
    - PowerShell
    - Microsoft-Windows-Sysmon
    """)

    st.markdown("### Option 1 — Export Security Events to CSV")

    st.code(
        r'''Get-WinEvent -LogName Security |
Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
Export-Csv -Path "C:\SecurityLogs.csv" -NoTypeInformation''',
        language="powershell"
    )

    st.markdown("### Option 2 — Export Security Events to XML")

    st.code(
        r'''Get-WinEvent -LogName Security |
Export-Clixml -Path "C:\SecurityLogs.xml"''',
        language="powershell"
    )

    st.markdown("### Option 3 — Export Multiple Windows Logs")

    st.code(
        r'''$logs = @(
    "Security",
    "System",
    "Application"
)

foreach ($log in $logs) {

    $safeName = $log.Replace("/", "_")

    Get-WinEvent -LogName $log |
    Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
    Export-Csv `
        -Path "C:\${safeName}_Logs.csv" `
        -NoTypeInformation
}''',
        language="powershell"
    )

    st.info(
        "The Windows Event Viewer can also export EVTX files, "
        "which can be preserved as the original forensic log format."
    )


# =========================================================
# LINUX
# =========================================================

elif operating_system == "Linux":

    st.subheader("🐧 Linux Log Collection")

    st.markdown("""
    Linux systems commonly use **systemd-journald** and/or
    traditional log files stored under:

    `/var/log/`

    Common logs include:

    - Authentication logs
    - System logs
    - Kernel logs
    - SSH logs
    - Cron logs
    - Application logs
    """)

    st.markdown("### Option 1 — Export Journal Logs to CSV")

    st.code(
        r'''journalctl --no-pager -o json |
jq -r '
[
    .__REALTIME_TIMESTAMP,
    ._HOSTNAME,
    ._SYSTEMD_UNIT,
    .MESSAGE
] | @csv
' > security_logs.csv''',
        language="bash"
    )

    st.markdown("### Option 2 — Export Journal Logs to JSON/XML-Compatible Data")

    st.code(
        r'''journalctl --no-pager -o json > security_logs.json''',
        language="bash"
    )

    st.markdown("### Option 3 — Export Traditional Log Files")

    st.code(
        r'''sudo cp /var/log/auth.log ./auth.log
sudo cp /var/log/syslog ./syslog''',
        language="bash"
    )

    st.markdown("### Convert a Log File to CSV")

    st.code(
        r'''awk 'BEGIN {OFS=","}
{
    print $1,$2,$3,$0
}' /var/log/auth.log > auth_logs.csv''',
        language="bash"
    )

    st.info(
        "Log locations vary by Linux distribution. Ubuntu/Debian "
        "systems commonly use /var/log/auth.log, while RHEL-based "
        "systems commonly use /var/log/secure."
    )


# =========================================================
# MACOS
# =========================================================

elif operating_system == "macOS":

    st.subheader("🍎 macOS Log Collection")

    st.markdown("""
    macOS uses Apple's **Unified Logging System**.

    Logs can be queried using the `log` command from Terminal.
    """)

    st.markdown("### Option 1 — Export Logs to JSON")

    st.code(
        r'''log show --style json --last 24h > macos_logs.json''',
        language="bash"
    )

    st.markdown("### Option 2 — Export Logs to CSV")

    st.code(
        r'''log show --last 24h --style syslog |
awk 'BEGIN {OFS=","}
{
    print $1,$2,$3,$0
}' > macos_logs.csv''',
        language="bash"
    )

    st.markdown("### Option 3 — Export Specific Security-Related Events")

    st.code(
        r'''log show \
--last 24h \
--predicate 'eventMessage CONTAINS[c] "authentication"' \
--style syslog > authentication_logs.txt''',
        language="bash"
    )

    st.markdown("### Option 4 — Export Logs for a Specific Time Period")

    st.code(
        r'''log show \
--start "2026-08-08 00:00:00" \
--end "2026-08-08 23:59:59" \
--style json > daily_logs.json''',
        language="bash"
    )

    st.info(
        "For forensic preservation, retain the original macOS "
        "log output in addition to any CSV conversion."
    )


# =========================================================
# DOWNLOADABLE LOG TEMPLATE
# =========================================================

st.divider()

st.header("📄 Cybersecurity Log Collection Template")

st.write(
    "Use this template to document logs collected during "
    "a cybersecurity or CMMC assessment."
)

log_template = pd.DataFrame({
    "Operating System": [],
    "Hostname": [],
    "Log Type": [],
    "Collection Date": [],
    "Collection Method": [],
    "File Name": [],
    "File Format": [],
    "Collected By": [],
    "Notes": []
})

csv_buffer = io.StringIO()
log_template.to_csv(csv_buffer, index=False)

st.download_button(
    label="⬇️ Download Log Collection CSV Template",
    data=csv_buffer.getvalue(),
    file_name="Cybersecurity_Log_Collection_Template.csv",
    mime="text/csv",
    use_container_width=True
)

st.divider()

st.caption(
    "CMMC Resources | Cybersecurity Log Collection | "
    "GetRight: CMMC Compliance Auditor"
)