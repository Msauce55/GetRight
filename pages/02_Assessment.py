import streamlit as st
import pandas as pd
import json
import os
import io
import re
import time
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image
)

from dotenv import load_dotenv
from openai import OpenAI
from impact_utils import log_assessment_run


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="GetRight CMMC Assessment",
    page_icon="🛡️",
    layout="wide"
)


# ============================================================
# LOAD ENVIRONMENT VARIABLES / SECRETS
# ============================================================

load_dotenv()

# Check Streamlit secrets first (for Streamlit Community Cloud),
# then fall back to a local .env file (for local development).
# st.secrets raises an error (rather than returning None) if no
# secrets.toml file exists at all, so this is wrapped in a try/except.

try:

    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

except Exception:

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# ============================================================
# GROQ CLIENT (OpenAI-compatible endpoint)
# ============================================================

if GROQ_API_KEY:

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

else:

    client = None

# ============================================================
# GROQ MODEL SELECTOR + AUTOMATIC FALLBACK
# ============================================================
AVAILABLE_MODELS = [
    "openai/gpt-oss-120b",                          # Best quality (recommended)
    "openai/gpt-oss-20b",                           # Fast + high quality
    "meta-llama/llama-4-maverick-17b-128e-instruct", # Strong reasoning
    "meta-llama/llama-4-scout-17b-16e-instruct",     # Fast
    "qwen/qwen3-32b",                               # Excellent alternative
]

selected_model = st.sidebar.selectbox(
    "LLM Model (Groq)",
    options=AVAILABLE_MODELS,
    index=0,
    help="If the primary model fails, the system will automatically try the next ones."
)

st.sidebar.caption("Models listed in recommended order. Fallback is automatic.")


def call_groq_with_fallback(messages, temperature=0, max_tokens=800):
    """
    Tries the selected model first, then automatically falls back
    through the remaining models if a 404 / model_not_found occurs.
    """
    models_to_try = [selected_model] + [m for m in AVAILABLE_MODELS if m != selected_model]
    last_error = None

    for model in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return response, model
        except Exception as e:
            error_str = str(e).lower()
            if "model_not_found" in error_str or "does not exist" in error_str or "404" in error_str:
                st.warning(f"Model `{model}` is unavailable. Trying next model...")
                last_error = e
                continue
            else:
                raise e

    raise Exception(f"All models failed. Last error: {last_error}")
# ============================================================
# CMMC CONTROL DATABASE
# ============================================================
#
# Full control sets for all three CMMC levels:
#
#   CMMC Level 1  — 15 requirements  (FAR 52.204-21(b)(1)(i)-(xv))
#   CMMC Level 2  — 110 requirements (NIST SP 800-171 Rev. 2,
#                    14 control families)
#   CMMC Level 3  — 134 requirements (the same 110 Level 2
#                    requirements, since Level 3 first requires a
#                    Final Level 2 status, PLUS the 24 enhanced
#                    requirements DoD selected from NIST SP 800-172
#                    Feb 2021 — see 32 CFR 170.14(c)(4), Table 1)
#
# Assessment objectives for Level 1 and the Level 3 enhanced
# requirements are tailored to each requirement. Level 2 objectives
# are derived programmatically from the NIST SP 800-171 requirement
# text; for the authoritative, fully-decomposed assessment
# objectives (NIST counts 320 across the 110 Level 2 requirements),
# consult NIST SP 800-171A directly.
#
# ============================================================

CMMC_CONTROLS = {
    "CMMC Level 1": [
        {
            "id": "AC.L1-b.1.i",
            "family": "Access Control",
            "requirement": "Limit information system access to authorized users, processes acting on behalf of authorized users, or devices (including other information systems).",
            "assessment_objectives": [
                "Determine whether authorized users, processes, and devices are identified.",
                "Determine whether system access is limited to those authorized users, processes, and devices.",
                "Determine whether shared, generic, or leftover accounts (e.g. former employees) are prevented from retaining access."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L1-b.1.ii",
            "family": "Access Control",
            "requirement": "Limit information system access to the types of transactions and functions that authorized users are permitted to execute.",
            "assessment_objectives": [
                "Determine whether the transactions and functions authorized users are permitted to execute are defined.",
                "Determine whether system access is limited to those permitted transactions and functions (role-based / least privilege).",
                "Determine whether standard users lack administrative rights beyond what their role requires."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L1-b.1.iii",
            "family": "Access Control",
            "requirement": "Verify and control/limit connections to and use of external information systems.",
            "assessment_objectives": [
                "Determine whether connections to external information systems are identified.",
                "Determine whether the use of external information systems is verified and controlled/limited.",
                "Determine whether a documented approval process exists for connecting external or personal devices."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L1-b.1.iv",
            "family": "Access Control",
            "requirement": "Control information posted or processed on publicly accessible information systems.",
            "assessment_objectives": [
                "Determine whether individuals authorized to post or process information on publicly accessible systems are identified.",
                "Determine whether a review process exists prior to posting to ensure no FCI is included.",
                "Determine whether publicly accessible content is periodically reviewed to remove information that should not be public."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "IA.L1-b.1.v",
            "family": "Identification and Authentication",
            "requirement": "Identify information system users, processes acting on behalf of users, and devices.",
            "assessment_objectives": [
                "Determine whether system users are identified.",
                "Determine whether processes acting on behalf of users are identified.",
                "Determine whether devices accessing the system are identified."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L1-b.1.vi",
            "family": "Identification and Authentication",
            "requirement": "Authenticate (or verify) the identities of those users, processes, or devices, as a prerequisite to allowing access to organizational information systems.",
            "assessment_objectives": [
                "Determine whether the identity of each user is authenticated or verified as a prerequisite to system access.",
                "Determine whether the identity of each process acting on behalf of a user is authenticated or verified.",
                "Determine whether the identity of each device is authenticated or verified prior to connection."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "MP.L1-b.1.vii",
            "family": "Media Protection",
            "requirement": "Sanitize or destroy information system media containing Federal Contract Information before disposal or reuse.",
            "assessment_objectives": [
                "Determine whether system media containing FCI is identified.",
                "Determine whether such media is sanitized or destroyed before disposal or reuse.",
                "Determine whether sanitization/destruction is documented (e.g. logs, certificates of destruction)."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "PE.L1-b.1.viii",
            "family": "Physical Protection",
            "requirement": "Limit physical access to organizational information systems, equipment, and the respective operating environments to authorized individuals.",
            "assessment_objectives": [
                "Determine whether authorized individuals allowed physical access are identified.",
                "Determine whether physical access to systems, equipment, and operating environments is limited to those authorized individuals.",
                "Determine whether unattended, unlocked access points to equipment are prevented."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L1-b.1.ix",
            "family": "Physical Protection",
            "requirement": "Escort visitors and monitor visitor activity; maintain audit logs of physical access; and control and manage physical access devices (e.g., keys, locks, combinations, and card readers).",
            "assessment_objectives": [
                "Determine whether visitors are escorted and their activity monitored.",
                "Determine whether audit logs of physical access are maintained.",
                "Determine whether physical access devices (keys, locks, combinations, card readers) are controlled and managed, including revocation when no longer needed."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "SC.L1-b.1.x",
            "family": "System and Communications Protection",
            "requirement": "Monitor, control, and protect organizational communications (i.e., information transmitted or received by organizational information systems) at the external boundaries and key internal boundaries of the information systems.",
            "assessment_objectives": [
                "Determine whether the external and key internal system boundaries are defined.",
                "Determine whether communications at those boundaries are monitored.",
                "Determine whether communications at those boundaries are controlled and protected (e.g. firewall with a default-deny posture)."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L1-b.1.xi",
            "family": "System and Communications Protection",
            "requirement": "Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.",
            "assessment_objectives": [
                "Determine whether publicly accessible system components are identified.",
                "Determine whether subnetworks for those publicly accessible components are implemented.",
                "Determine whether those subnetworks are physically or logically separated from internal networks (e.g. DMZ, VLAN segmentation)."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SI.L1-b.1.xii",
            "family": "System and Information Integrity",
            "requirement": "Identify, report, and correct information and information system flaws in a timely manner.",
            "assessment_objectives": [
                "Determine whether system flaws are identified in a timely manner (e.g. vulnerability scanning).",
                "Determine whether identified flaws are reported.",
                "Determine whether identified flaws are corrected in a timely manner (e.g. documented patch cadence)."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L1-b.1.xiii",
            "family": "System and Information Integrity",
            "requirement": "Provide protection from malicious code at appropriate locations within organizational information systems.",
            "assessment_objectives": [
                "Determine whether designated locations for malicious code protection are identified (e.g. endpoints, servers, email gateway).",
                "Determine whether malicious code protection is deployed at those designated locations.",
                "Determine whether the deployed protection is actively enabled (e.g. real-time scanning)."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L1-b.1.xiv",
            "family": "System and Information Integrity",
            "requirement": "Update malicious code protection mechanisms when new releases are available.",
            "assessment_objectives": [
                "Determine whether malicious code protection mechanisms are updated when new releases are available.",
                "Determine whether definition/signature updates are applied automatically or on a defined cadence.",
                "Determine whether endpoints that fall behind on updates are detected and remediated."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L1-b.1.xv",
            "family": "System and Information Integrity",
            "requirement": "Perform periodic scans of the information system and real-time scans of files from external sources as files are downloaded, opened, or executed.",
            "assessment_objectives": [
                "Determine whether periodic scans of the information system are performed.",
                "Determine whether real-time scans of files from external sources are performed as those files are downloaded, opened, or executed.",
                "Determine whether scan results and detections are logged."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        }
    ],
    "CMMC Level 2": [
        {
            "id": "AC.L2-3.1.1",
            "family": "Access Control",
            "requirement": "Limit system access to authorized users, processes acting on behalf of authorized users, and devices (including other systems).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit system access to authorized users, processes acting on behalf of authorized users, and devices (including other systems).",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.2",
            "family": "Access Control",
            "requirement": "Limit system access to the types of transactions and functions that authorized users are permitted to execute.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit system access to the types of transactions and functions that authorized users are permitted to execute.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.3",
            "family": "Access Control",
            "requirement": "Control the flow of CUI in accordance with approved authorizations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control the flow of CUI in accordance with approved authorizations.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.4",
            "family": "Access Control",
            "requirement": "Separate the duties of individuals to reduce the risk of malevolent activity without collusion.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Separate the duties of individuals to reduce the risk of malevolent activity without collusion.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.5",
            "family": "Access Control",
            "requirement": "Employ the principle of least privilege, including for specific security functions and privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ the principle of least privilege, including for specific security functions and privileged accounts.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.6",
            "family": "Access Control",
            "requirement": "Use non-privileged accounts or roles when accessing nonsecurity functions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use non-privileged accounts or roles when accessing nonsecurity functions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.7",
            "family": "Access Control",
            "requirement": "Prevent non-privileged users from executing privileged functions and capture the execution of such functions in audit logs.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent non-privileged users from executing privileged functions and capture the execution of such functions in audit logs.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.8",
            "family": "Access Control",
            "requirement": "Limit unsuccessful logon attempts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit unsuccessful logon attempts.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.9",
            "family": "Access Control",
            "requirement": "Provide privacy and security notices consistent with applicable CUI rules.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide privacy and security notices consistent with applicable CUI rules.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.10",
            "family": "Access Control",
            "requirement": "Use session lock with pattern-hiding displays to prevent access and viewing of data after a period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use session lock with pattern-hiding displays to prevent access and viewing of data after a period of inactivity.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.11",
            "family": "Access Control",
            "requirement": "Terminate (automatically) a user session after a defined condition.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Terminate (automatically) a user session after a defined condition.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.12",
            "family": "Access Control",
            "requirement": "Monitor and control remote access sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor and control remote access sessions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.13",
            "family": "Access Control",
            "requirement": "Employ cryptographic mechanisms to protect the confidentiality of remote access sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ cryptographic mechanisms to protect the confidentiality of remote access sessions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.14",
            "family": "Access Control",
            "requirement": "Route remote access via managed access control points.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Route remote access via managed access control points.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.15",
            "family": "Access Control",
            "requirement": "Authorize remote execution of privileged commands and remote access to security-relevant information.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authorize remote execution of privileged commands and remote access to security-relevant information.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.16",
            "family": "Access Control",
            "requirement": "Authorize wireless access prior to allowing such connections.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authorize wireless access prior to allowing such connections.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.17",
            "family": "Access Control",
            "requirement": "Protect wireless access using authentication and encryption.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect wireless access using authentication and encryption.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.18",
            "family": "Access Control",
            "requirement": "Control connection of mobile devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control connection of mobile devices.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.19",
            "family": "Access Control",
            "requirement": "Encrypt CUI on mobile devices and mobile computing platforms.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Encrypt CUI on mobile devices and mobile computing platforms.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.20",
            "family": "Access Control",
            "requirement": "Verify and control/limit connections to and use of external systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Verify and control/limit connections to and use of external systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.21",
            "family": "Access Control",
            "requirement": "Limit use of portable storage devices on external systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit use of portable storage devices on external systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.22",
            "family": "Access Control",
            "requirement": "Control CUI posted or processed on publicly accessible systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control CUI posted or processed on publicly accessible systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AT.L2-3.2.1",
            "family": "Awareness and Training",
            "requirement": "Ensure that managers, systems administrators, and users of organizational systems are made aware of the security risks associated with their activities and of the applicable policies, standards, and procedures related to the security of those systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that managers, systems administrators, and users of organizational systems are made aware of the security risks associated with their activities and of the applicable policies, standards, and procedures related to the security of those systems.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AT.L2-3.2.2",
            "family": "Awareness and Training",
            "requirement": "Ensure that personnel are trained to carry out their assigned information security-related duties and responsibilities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that personnel are trained to carry out their assigned information security-related duties and responsibilities.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AT.L2-3.2.3",
            "family": "Awareness and Training",
            "requirement": "Provide security awareness training on recognizing and reporting potential indicators of insider threat.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide security awareness training on recognizing and reporting potential indicators of insider threat.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AU.L2-3.3.1",
            "family": "Audit and Accountability",
            "requirement": "Create and retain system audit logs and records to the extent needed to enable the monitoring, analysis, investigation, and reporting of unlawful or unauthorized system activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Create and retain system audit logs and records to the extent needed to enable the monitoring, analysis, investigation, and reporting of unlawful or unauthorized system activity.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.2",
            "family": "Audit and Accountability",
            "requirement": "Ensure that the actions of individual system users can be uniquely traced to those users, so they can be held accountable for their actions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that the actions of individual system users can be uniquely traced to those users, so they can be held accountable for their actions.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.3",
            "family": "Audit and Accountability",
            "requirement": "Review and update logged events.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Review and update logged events.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.4",
            "family": "Audit and Accountability",
            "requirement": "Alert in the event of an audit logging process failure.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Alert in the event of an audit logging process failure.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.5",
            "family": "Audit and Accountability",
            "requirement": "Correlate audit record review, analysis, and reporting processes for investigation and response to indications of unlawful, unauthorized, suspicious, or unusual activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Correlate audit record review, analysis, and reporting processes for investigation and response to indications of unlawful, unauthorized, suspicious, or unusual activity.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.6",
            "family": "Audit and Accountability",
            "requirement": "Provide audit record reduction and report generation to support on-demand analysis and reporting.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide audit record reduction and report generation to support on-demand analysis and reporting.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.7",
            "family": "Audit and Accountability",
            "requirement": "Provide a system capability that compares and synchronizes internal system clocks with an authoritative source to generate time stamps for audit records.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide a system capability that compares and synchronizes internal system clocks with an authoritative source to generate time stamps for audit records.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.8",
            "family": "Audit and Accountability",
            "requirement": "Protect audit information and audit logging tools from unauthorized access, modification, and deletion.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect audit information and audit logging tools from unauthorized access, modification, and deletion.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.9",
            "family": "Audit and Accountability",
            "requirement": "Limit management of audit logging functionality to a subset of privileged users.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit management of audit logging functionality to a subset of privileged users.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "CM.L2-3.4.1",
            "family": "Configuration Management",
            "requirement": "Establish and maintain baseline configurations and inventories of organizational systems (including hardware, software, firmware, and documentation) throughout the respective system development life cycles.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and maintain baseline configurations and inventories of organizational systems (including hardware, software, firmware, and documentation) throughout the respective system development life cycles.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.2",
            "family": "Configuration Management",
            "requirement": "Establish and enforce security configuration settings for information technology products employed in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and enforce security configuration settings for information technology products employed in organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.3",
            "family": "Configuration Management",
            "requirement": "Track, review, approve or disapprove, and log changes to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Track, review, approve or disapprove, and log changes to organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.4",
            "family": "Configuration Management",
            "requirement": "Analyze the security impact of changes prior to implementation.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Analyze the security impact of changes prior to implementation.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.5",
            "family": "Configuration Management",
            "requirement": "Define, document, approve, and enforce physical and logical access restrictions associated with changes to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Define, document, approve, and enforce physical and logical access restrictions associated with changes to organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.6",
            "family": "Configuration Management",
            "requirement": "Employ the principle of least functionality by configuring organizational systems to provide only essential capabilities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ the principle of least functionality by configuring organizational systems to provide only essential capabilities.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.7",
            "family": "Configuration Management",
            "requirement": "Restrict, disable, or prevent the use of nonessential programs, functions, ports, protocols, and services.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Restrict, disable, or prevent the use of nonessential programs, functions, ports, protocols, and services.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.8",
            "family": "Configuration Management",
            "requirement": "Apply deny-by-exception (blacklisting) policy to prevent the use of unauthorized software or deny-all, permit-by-exception (whitelisting) policy to allow the execution of authorized software.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Apply deny-by-exception (blacklisting) policy to prevent the use of unauthorized software or deny-all, permit-by-exception (whitelisting) policy to allow the execution of authorized software.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.9",
            "family": "Configuration Management",
            "requirement": "Control and monitor user-installed software.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor user-installed software.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "IA.L2-3.5.1",
            "family": "Identification and Authentication",
            "requirement": "Identify system users, processes acting on behalf of users, and devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify system users, processes acting on behalf of users, and devices.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.2",
            "family": "Identification and Authentication",
            "requirement": "Authenticate (or verify) the identities of users, processes, or devices, as a prerequisite to allowing access to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authenticate (or verify) the identities of users, processes, or devices, as a prerequisite to allowing access to organizational systems.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.3",
            "family": "Identification and Authentication",
            "requirement": "Use multifactor authentication for local and network access to privileged accounts and for network access to non-privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use multifactor authentication for local and network access to privileged accounts and for network access to non-privileged accounts.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.4",
            "family": "Identification and Authentication",
            "requirement": "Employ replay-resistant authentication mechanisms for network access to privileged and non-privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ replay-resistant authentication mechanisms for network access to privileged and non-privileged accounts.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.5",
            "family": "Identification and Authentication",
            "requirement": "Prevent reuse of identifiers for a defined period.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent reuse of identifiers for a defined period.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.6",
            "family": "Identification and Authentication",
            "requirement": "Disable identifiers after a defined period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Disable identifiers after a defined period of inactivity.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.7",
            "family": "Identification and Authentication",
            "requirement": "Enforce a minimum password complexity and change of characters when new passwords are created.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Enforce a minimum password complexity and change of characters when new passwords are created.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.8",
            "family": "Identification and Authentication",
            "requirement": "Prohibit password reuse for a specified number of generations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit password reuse for a specified number of generations.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.9",
            "family": "Identification and Authentication",
            "requirement": "Allow temporary password use for system logons with an immediate change to a permanent password.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Allow temporary password use for system logons with an immediate change to a permanent password.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.10",
            "family": "Identification and Authentication",
            "requirement": "Store and transmit only cryptographically-protected passwords.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Store and transmit only cryptographically-protected passwords.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.11",
            "family": "Identification and Authentication",
            "requirement": "Obscure feedback of authentication information.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Obscure feedback of authentication information.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IR.L2-3.6.1",
            "family": "Incident Response",
            "requirement": "Establish an operational incident-handling capability for organizational systems that includes preparation, detection, analysis, containment, recovery, and user response activities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish an operational incident-handling capability for organizational systems that includes preparation, detection, analysis, containment, recovery, and user response activities.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "IR.L2-3.6.2",
            "family": "Incident Response",
            "requirement": "Track, document, and report incidents to designated officials and/or authorities both internal and external to the organization.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Track, document, and report incidents to designated officials and/or authorities both internal and external to the organization.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "IR.L2-3.6.3",
            "family": "Incident Response",
            "requirement": "Test the organizational incident response capability.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Test the organizational incident response capability.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "MA.L2-3.7.1",
            "family": "Maintenance",
            "requirement": "Perform maintenance on organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Perform maintenance on organizational systems.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.2",
            "family": "Maintenance",
            "requirement": "Provide controls on the tools, techniques, mechanisms, and personnel used to conduct system maintenance.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide controls on the tools, techniques, mechanisms, and personnel used to conduct system maintenance.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.3",
            "family": "Maintenance",
            "requirement": "Ensure equipment removed for off-site maintenance is sanitized of any CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure equipment removed for off-site maintenance is sanitized of any CUI.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.4",
            "family": "Maintenance",
            "requirement": "Check media containing diagnostic and test programs for malicious code before the media are used in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Check media containing diagnostic and test programs for malicious code before the media are used in organizational systems.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.5",
            "family": "Maintenance",
            "requirement": "Require multifactor authentication to establish nonlocal maintenance sessions via external network connections and terminate such connections when nonlocal maintenance is complete.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Require multifactor authentication to establish nonlocal maintenance sessions via external network connections and terminate such connections when nonlocal maintenance is complete.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.6",
            "family": "Maintenance",
            "requirement": "Supervise the maintenance activities of maintenance personnel without required access authorization.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Supervise the maintenance activities of maintenance personnel without required access authorization.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MP.L2-3.8.1",
            "family": "Media Protection",
            "requirement": "Protect (i.e., physically control and securely store) system media containing CUI, both paper and digital.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect (i.e., physically control and securely store) system media containing CUI, both paper and digital.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.2",
            "family": "Media Protection",
            "requirement": "Limit access to CUI on system media to authorized users.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit access to CUI on system media to authorized users.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.3",
            "family": "Media Protection",
            "requirement": "Sanitize or destroy system media containing CUI before disposal or release for reuse.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Sanitize or destroy system media containing CUI before disposal or release for reuse.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.4",
            "family": "Media Protection",
            "requirement": "Mark media with necessary CUI markings and distribution limitations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Mark media with necessary CUI markings and distribution limitations.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.5",
            "family": "Media Protection",
            "requirement": "Control access to media containing CUI and maintain accountability for media during transport outside of controlled areas.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control access to media containing CUI and maintain accountability for media during transport outside of controlled areas.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.6",
            "family": "Media Protection",
            "requirement": "Implement cryptographic mechanisms to protect the confidentiality of CUI stored on digital media during transport unless otherwise protected by alternative physical safeguards.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement cryptographic mechanisms to protect the confidentiality of CUI stored on digital media during transport unless otherwise protected by alternative physical safeguards.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.7",
            "family": "Media Protection",
            "requirement": "Control the use of removable media on system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control the use of removable media on system components.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.8",
            "family": "Media Protection",
            "requirement": "Prohibit the use of portable storage devices when such devices have no identifiable owner.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit the use of portable storage devices when such devices have no identifiable owner.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.9",
            "family": "Media Protection",
            "requirement": "Protect the confidentiality of backup CUI at storage locations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the confidentiality of backup CUI at storage locations.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "PS.L2-3.9.1",
            "family": "Personnel Security",
            "requirement": "Screen individuals prior to authorizing access to organizational systems containing CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Screen individuals prior to authorizing access to organizational systems containing CUI.",
                "Determine whether this Personnel Security requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "background screening records",
                "personnel termination/transfer checklists"
            ]
        },
        {
            "id": "PS.L2-3.9.2",
            "family": "Personnel Security",
            "requirement": "Ensure that organizational systems containing CUI are protected during and after personnel actions such as terminations and transfers.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that organizational systems containing CUI are protected during and after personnel actions such as terminations and transfers.",
                "Determine whether this Personnel Security requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "background screening records",
                "personnel termination/transfer checklists"
            ]
        },
        {
            "id": "PE.L2-3.10.1",
            "family": "Physical Protection",
            "requirement": "Limit physical access to organizational systems, equipment, and the respective operating environments to authorized individuals.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit physical access to organizational systems, equipment, and the respective operating environments to authorized individuals.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.2",
            "family": "Physical Protection",
            "requirement": "Protect and monitor the physical facility and support infrastructure for organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect and monitor the physical facility and support infrastructure for organizational systems.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.3",
            "family": "Physical Protection",
            "requirement": "Escort visitors and monitor visitor activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Escort visitors and monitor visitor activity.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.4",
            "family": "Physical Protection",
            "requirement": "Maintain audit logs of physical access.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Maintain audit logs of physical access.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.5",
            "family": "Physical Protection",
            "requirement": "Control and manage physical access devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and manage physical access devices.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.6",
            "family": "Physical Protection",
            "requirement": "Enforce safeguarding measures for CUI at alternate work sites.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Enforce safeguarding measures for CUI at alternate work sites.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "RA.L2-3.11.1",
            "family": "Risk Assessment",
            "requirement": "Periodically assess the risk to organizational operations (including mission, functions, image, or reputation), organizational assets, and individuals, resulting from the operation of organizational systems and the associated processing, storage, or transmission of CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Periodically assess the risk to organizational operations (including mission, functions, image, or reputation), organizational assets, and individuals, resulting from the operation of organizational systems and the associated processing, storage, or transmission of CUI.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "RA.L2-3.11.2",
            "family": "Risk Assessment",
            "requirement": "Scan for vulnerabilities in organizational systems and applications periodically and when new vulnerabilities affecting those systems and applications are identified.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Scan for vulnerabilities in organizational systems and applications periodically and when new vulnerabilities affecting those systems and applications are identified.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "RA.L2-3.11.3",
            "family": "Risk Assessment",
            "requirement": "Remediate vulnerabilities in accordance with risk assessments.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Remediate vulnerabilities in accordance with risk assessments.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "CA.L2-3.12.1",
            "family": "Security Assessment",
            "requirement": "Periodically assess the security controls in organizational systems to determine if the controls are effective in their application.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Periodically assess the security controls in organizational systems to determine if the controls are effective in their application.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.2",
            "family": "Security Assessment",
            "requirement": "Develop and implement plans of action designed to correct deficiencies and reduce or eliminate vulnerabilities in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Develop and implement plans of action designed to correct deficiencies and reduce or eliminate vulnerabilities in organizational systems.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.3",
            "family": "Security Assessment",
            "requirement": "Monitor security controls on an ongoing basis to ensure the continued effectiveness of the controls.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor security controls on an ongoing basis to ensure the continued effectiveness of the controls.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.4",
            "family": "Security Assessment",
            "requirement": "Develop, document, and periodically update system security plans that describe system boundaries, system environments of operation, how security requirements are implemented, and the relationships with or connections to other systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Develop, document, and periodically update system security plans that describe system boundaries, system environments of operation, how security requirements are implemented, and the relationships with or connections to other systems.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "SC.L2-3.13.1",
            "family": "System and Communications Protection",
            "requirement": "Monitor, control, and protect communications (i.e., information transmitted or received by organizational systems) at the external boundaries and key internal boundaries of organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor, control, and protect communications (i.e., information transmitted or received by organizational systems) at the external boundaries and key internal boundaries of organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.2",
            "family": "System and Communications Protection",
            "requirement": "Employ architectural designs, software development techniques, and systems engineering principles that promote effective information security within organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ architectural designs, software development techniques, and systems engineering principles that promote effective information security within organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.3",
            "family": "System and Communications Protection",
            "requirement": "Separate user functionality from system management functionality.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Separate user functionality from system management functionality.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.4",
            "family": "System and Communications Protection",
            "requirement": "Prevent unauthorized and unintended information transfer via shared system resources.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent unauthorized and unintended information transfer via shared system resources.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.5",
            "family": "System and Communications Protection",
            "requirement": "Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.6",
            "family": "System and Communications Protection",
            "requirement": "Deny network communications traffic by default and allow network communications traffic by exception (i.e., deny all, permit by exception).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Deny network communications traffic by default and allow network communications traffic by exception (i.e., deny all, permit by exception).",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.7",
            "family": "System and Communications Protection",
            "requirement": "Prevent remote devices from simultaneously establishing non-remote connections with organizational systems and communicating via some other connection to resources in external networks (i.e., split tunneling).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent remote devices from simultaneously establishing non-remote connections with organizational systems and communicating via some other connection to resources in external networks (i.e., split tunneling).",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.8",
            "family": "System and Communications Protection",
            "requirement": "Implement cryptographic mechanisms to prevent unauthorized disclosure of CUI during transmission unless otherwise protected by alternative physical safeguards.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement cryptographic mechanisms to prevent unauthorized disclosure of CUI during transmission unless otherwise protected by alternative physical safeguards.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.9",
            "family": "System and Communications Protection",
            "requirement": "Terminate network connections associated with communications sessions at the end of the session or after a defined period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Terminate network connections associated with communications sessions at the end of the session or after a defined period of inactivity.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.10",
            "family": "System and Communications Protection",
            "requirement": "Establish and manage cryptographic keys for cryptography employed in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and manage cryptographic keys for cryptography employed in organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.11",
            "family": "System and Communications Protection",
            "requirement": "Employ FIPS-validated cryptography when used to protect the confidentiality of CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ FIPS-validated cryptography when used to protect the confidentiality of CUI.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.12",
            "family": "System and Communications Protection",
            "requirement": "Prohibit remote activation of collaborative computing devices and provide indication of devices in use to users present at the device.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit remote activation of collaborative computing devices and provide indication of devices in use to users present at the device.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.13",
            "family": "System and Communications Protection",
            "requirement": "Control and monitor the use of mobile code.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor the use of mobile code.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.14",
            "family": "System and Communications Protection",
            "requirement": "Control and monitor the use of Voice over Internet Protocol (VoIP) technologies.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor the use of Voice over Internet Protocol (VoIP) technologies.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.15",
            "family": "System and Communications Protection",
            "requirement": "Protect the authenticity of communications sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the authenticity of communications sessions.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.16",
            "family": "System and Communications Protection",
            "requirement": "Protect the confidentiality of CUI at rest.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the confidentiality of CUI at rest.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SI.L2-3.14.1",
            "family": "System and Information Integrity",
            "requirement": "Identify, report, and correct system flaws in a timely manner.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify, report, and correct system flaws in a timely manner.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.2",
            "family": "System and Information Integrity",
            "requirement": "Provide protection from malicious code at designated locations within organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide protection from malicious code at designated locations within organizational systems.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.3",
            "family": "System and Information Integrity",
            "requirement": "Monitor system security alerts and advisories and take action in response.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor system security alerts and advisories and take action in response.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.4",
            "family": "System and Information Integrity",
            "requirement": "Update malicious code protection mechanisms when new releases are available.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Update malicious code protection mechanisms when new releases are available.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.5",
            "family": "System and Information Integrity",
            "requirement": "Perform periodic scans of organizational systems and real-time scans of files from external sources as files are downloaded, opened, or executed.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Perform periodic scans of organizational systems and real-time scans of files from external sources as files are downloaded, opened, or executed.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.6",
            "family": "System and Information Integrity",
            "requirement": "Monitor organizational systems, including inbound and outbound communications traffic, to detect attacks and indicators of potential attacks.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor organizational systems, including inbound and outbound communications traffic, to detect attacks and indicators of potential attacks.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.7",
            "family": "System and Information Integrity",
            "requirement": "Identify unauthorized use of organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify unauthorized use of organizational systems.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        }
    ],
    "CMMC Level 3": [
        {
            "id": "AC.L2-3.1.1",
            "family": "Access Control",
            "requirement": "Limit system access to authorized users, processes acting on behalf of authorized users, and devices (including other systems).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit system access to authorized users, processes acting on behalf of authorized users, and devices (including other systems).",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.2",
            "family": "Access Control",
            "requirement": "Limit system access to the types of transactions and functions that authorized users are permitted to execute.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit system access to the types of transactions and functions that authorized users are permitted to execute.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.3",
            "family": "Access Control",
            "requirement": "Control the flow of CUI in accordance with approved authorizations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control the flow of CUI in accordance with approved authorizations.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.4",
            "family": "Access Control",
            "requirement": "Separate the duties of individuals to reduce the risk of malevolent activity without collusion.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Separate the duties of individuals to reduce the risk of malevolent activity without collusion.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.5",
            "family": "Access Control",
            "requirement": "Employ the principle of least privilege, including for specific security functions and privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ the principle of least privilege, including for specific security functions and privileged accounts.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.6",
            "family": "Access Control",
            "requirement": "Use non-privileged accounts or roles when accessing nonsecurity functions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use non-privileged accounts or roles when accessing nonsecurity functions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.7",
            "family": "Access Control",
            "requirement": "Prevent non-privileged users from executing privileged functions and capture the execution of such functions in audit logs.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent non-privileged users from executing privileged functions and capture the execution of such functions in audit logs.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.8",
            "family": "Access Control",
            "requirement": "Limit unsuccessful logon attempts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit unsuccessful logon attempts.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.9",
            "family": "Access Control",
            "requirement": "Provide privacy and security notices consistent with applicable CUI rules.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide privacy and security notices consistent with applicable CUI rules.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.10",
            "family": "Access Control",
            "requirement": "Use session lock with pattern-hiding displays to prevent access and viewing of data after a period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use session lock with pattern-hiding displays to prevent access and viewing of data after a period of inactivity.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.11",
            "family": "Access Control",
            "requirement": "Terminate (automatically) a user session after a defined condition.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Terminate (automatically) a user session after a defined condition.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.12",
            "family": "Access Control",
            "requirement": "Monitor and control remote access sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor and control remote access sessions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.13",
            "family": "Access Control",
            "requirement": "Employ cryptographic mechanisms to protect the confidentiality of remote access sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ cryptographic mechanisms to protect the confidentiality of remote access sessions.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.14",
            "family": "Access Control",
            "requirement": "Route remote access via managed access control points.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Route remote access via managed access control points.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.15",
            "family": "Access Control",
            "requirement": "Authorize remote execution of privileged commands and remote access to security-relevant information.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authorize remote execution of privileged commands and remote access to security-relevant information.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.16",
            "family": "Access Control",
            "requirement": "Authorize wireless access prior to allowing such connections.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authorize wireless access prior to allowing such connections.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.17",
            "family": "Access Control",
            "requirement": "Protect wireless access using authentication and encryption.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect wireless access using authentication and encryption.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.18",
            "family": "Access Control",
            "requirement": "Control connection of mobile devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control connection of mobile devices.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.19",
            "family": "Access Control",
            "requirement": "Encrypt CUI on mobile devices and mobile computing platforms.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Encrypt CUI on mobile devices and mobile computing platforms.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.20",
            "family": "Access Control",
            "requirement": "Verify and control/limit connections to and use of external systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Verify and control/limit connections to and use of external systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.21",
            "family": "Access Control",
            "requirement": "Limit use of portable storage devices on external systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit use of portable storage devices on external systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AC.L2-3.1.22",
            "family": "Access Control",
            "requirement": "Control CUI posted or processed on publicly accessible systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control CUI posted or processed on publicly accessible systems.",
                "Determine whether this Access Control requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations"
            ]
        },
        {
            "id": "AT.L2-3.2.1",
            "family": "Awareness and Training",
            "requirement": "Ensure that managers, systems administrators, and users of organizational systems are made aware of the security risks associated with their activities and of the applicable policies, standards, and procedures related to the security of those systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that managers, systems administrators, and users of organizational systems are made aware of the security risks associated with their activities and of the applicable policies, standards, and procedures related to the security of those systems.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AT.L2-3.2.2",
            "family": "Awareness and Training",
            "requirement": "Ensure that personnel are trained to carry out their assigned information security-related duties and responsibilities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that personnel are trained to carry out their assigned information security-related duties and responsibilities.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AT.L2-3.2.3",
            "family": "Awareness and Training",
            "requirement": "Provide security awareness training on recognizing and reporting potential indicators of insider threat.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide security awareness training on recognizing and reporting potential indicators of insider threat.",
                "Determine whether this Awareness and Training requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records"
            ]
        },
        {
            "id": "AU.L2-3.3.1",
            "family": "Audit and Accountability",
            "requirement": "Create and retain system audit logs and records to the extent needed to enable the monitoring, analysis, investigation, and reporting of unlawful or unauthorized system activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Create and retain system audit logs and records to the extent needed to enable the monitoring, analysis, investigation, and reporting of unlawful or unauthorized system activity.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.2",
            "family": "Audit and Accountability",
            "requirement": "Ensure that the actions of individual system users can be uniquely traced to those users, so they can be held accountable for their actions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that the actions of individual system users can be uniquely traced to those users, so they can be held accountable for their actions.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.3",
            "family": "Audit and Accountability",
            "requirement": "Review and update logged events.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Review and update logged events.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.4",
            "family": "Audit and Accountability",
            "requirement": "Alert in the event of an audit logging process failure.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Alert in the event of an audit logging process failure.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.5",
            "family": "Audit and Accountability",
            "requirement": "Correlate audit record review, analysis, and reporting processes for investigation and response to indications of unlawful, unauthorized, suspicious, or unusual activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Correlate audit record review, analysis, and reporting processes for investigation and response to indications of unlawful, unauthorized, suspicious, or unusual activity.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.6",
            "family": "Audit and Accountability",
            "requirement": "Provide audit record reduction and report generation to support on-demand analysis and reporting.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide audit record reduction and report generation to support on-demand analysis and reporting.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.7",
            "family": "Audit and Accountability",
            "requirement": "Provide a system capability that compares and synchronizes internal system clocks with an authoritative source to generate time stamps for audit records.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide a system capability that compares and synchronizes internal system clocks with an authoritative source to generate time stamps for audit records.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.8",
            "family": "Audit and Accountability",
            "requirement": "Protect audit information and audit logging tools from unauthorized access, modification, and deletion.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect audit information and audit logging tools from unauthorized access, modification, and deletion.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "AU.L2-3.3.9",
            "family": "Audit and Accountability",
            "requirement": "Limit management of audit logging functionality to a subset of privileged users.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit management of audit logging functionality to a subset of privileged users.",
                "Determine whether this Audit and Accountability requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "Windows Event Logs",
                "Linux/macOS audit logs",
                "SIEM records",
                "audit log retention policy",
                "clock synchronization (NTP) configuration"
            ]
        },
        {
            "id": "CM.L2-3.4.1",
            "family": "Configuration Management",
            "requirement": "Establish and maintain baseline configurations and inventories of organizational systems (including hardware, software, firmware, and documentation) throughout the respective system development life cycles.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and maintain baseline configurations and inventories of organizational systems (including hardware, software, firmware, and documentation) throughout the respective system development life cycles.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.2",
            "family": "Configuration Management",
            "requirement": "Establish and enforce security configuration settings for information technology products employed in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and enforce security configuration settings for information technology products employed in organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.3",
            "family": "Configuration Management",
            "requirement": "Track, review, approve or disapprove, and log changes to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Track, review, approve or disapprove, and log changes to organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.4",
            "family": "Configuration Management",
            "requirement": "Analyze the security impact of changes prior to implementation.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Analyze the security impact of changes prior to implementation.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.5",
            "family": "Configuration Management",
            "requirement": "Define, document, approve, and enforce physical and logical access restrictions associated with changes to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Define, document, approve, and enforce physical and logical access restrictions associated with changes to organizational systems.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.6",
            "family": "Configuration Management",
            "requirement": "Employ the principle of least functionality by configuring organizational systems to provide only essential capabilities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ the principle of least functionality by configuring organizational systems to provide only essential capabilities.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.7",
            "family": "Configuration Management",
            "requirement": "Restrict, disable, or prevent the use of nonessential programs, functions, ports, protocols, and services.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Restrict, disable, or prevent the use of nonessential programs, functions, ports, protocols, and services.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.8",
            "family": "Configuration Management",
            "requirement": "Apply deny-by-exception (blacklisting) policy to prevent the use of unauthorized software or deny-all, permit-by-exception (whitelisting) policy to allow the execution of authorized software.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Apply deny-by-exception (blacklisting) policy to prevent the use of unauthorized software or deny-all, permit-by-exception (whitelisting) policy to allow the execution of authorized software.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "CM.L2-3.4.9",
            "family": "Configuration Management",
            "requirement": "Control and monitor user-installed software.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor user-installed software.",
                "Determine whether this Configuration Management requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results"
            ]
        },
        {
            "id": "IA.L2-3.5.1",
            "family": "Identification and Authentication",
            "requirement": "Identify system users, processes acting on behalf of users, and devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify system users, processes acting on behalf of users, and devices.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.2",
            "family": "Identification and Authentication",
            "requirement": "Authenticate (or verify) the identities of users, processes, or devices, as a prerequisite to allowing access to organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Authenticate (or verify) the identities of users, processes, or devices, as a prerequisite to allowing access to organizational systems.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.3",
            "family": "Identification and Authentication",
            "requirement": "Use multifactor authentication for local and network access to privileged accounts and for network access to non-privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Use multifactor authentication for local and network access to privileged accounts and for network access to non-privileged accounts.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.4",
            "family": "Identification and Authentication",
            "requirement": "Employ replay-resistant authentication mechanisms for network access to privileged and non-privileged accounts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ replay-resistant authentication mechanisms for network access to privileged and non-privileged accounts.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.5",
            "family": "Identification and Authentication",
            "requirement": "Prevent reuse of identifiers for a defined period.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent reuse of identifiers for a defined period.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.6",
            "family": "Identification and Authentication",
            "requirement": "Disable identifiers after a defined period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Disable identifiers after a defined period of inactivity.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.7",
            "family": "Identification and Authentication",
            "requirement": "Enforce a minimum password complexity and change of characters when new passwords are created.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Enforce a minimum password complexity and change of characters when new passwords are created.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.8",
            "family": "Identification and Authentication",
            "requirement": "Prohibit password reuse for a specified number of generations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit password reuse for a specified number of generations.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.9",
            "family": "Identification and Authentication",
            "requirement": "Allow temporary password use for system logons with an immediate change to a permanent password.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Allow temporary password use for system logons with an immediate change to a permanent password.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.10",
            "family": "Identification and Authentication",
            "requirement": "Store and transmit only cryptographically-protected passwords.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Store and transmit only cryptographically-protected passwords.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IA.L2-3.5.11",
            "family": "Identification and Authentication",
            "requirement": "Obscure feedback of authentication information.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Obscure feedback of authentication information.",
                "Determine whether this Identification and Authentication requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records"
            ]
        },
        {
            "id": "IR.L2-3.6.1",
            "family": "Incident Response",
            "requirement": "Establish an operational incident-handling capability for organizational systems that includes preparation, detection, analysis, containment, recovery, and user response activities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish an operational incident-handling capability for organizational systems that includes preparation, detection, analysis, containment, recovery, and user response activities.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "IR.L2-3.6.2",
            "family": "Incident Response",
            "requirement": "Track, document, and report incidents to designated officials and/or authorities both internal and external to the organization.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Track, document, and report incidents to designated officials and/or authorities both internal and external to the organization.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "IR.L2-3.6.3",
            "family": "Incident Response",
            "requirement": "Test the organizational incident response capability.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Test the organizational incident response capability.",
                "Determine whether this Incident Response requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts"
            ]
        },
        {
            "id": "MA.L2-3.7.1",
            "family": "Maintenance",
            "requirement": "Perform maintenance on organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Perform maintenance on organizational systems.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.2",
            "family": "Maintenance",
            "requirement": "Provide controls on the tools, techniques, mechanisms, and personnel used to conduct system maintenance.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide controls on the tools, techniques, mechanisms, and personnel used to conduct system maintenance.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.3",
            "family": "Maintenance",
            "requirement": "Ensure equipment removed for off-site maintenance is sanitized of any CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure equipment removed for off-site maintenance is sanitized of any CUI.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.4",
            "family": "Maintenance",
            "requirement": "Check media containing diagnostic and test programs for malicious code before the media are used in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Check media containing diagnostic and test programs for malicious code before the media are used in organizational systems.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.5",
            "family": "Maintenance",
            "requirement": "Require multifactor authentication to establish nonlocal maintenance sessions via external network connections and terminate such connections when nonlocal maintenance is complete.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Require multifactor authentication to establish nonlocal maintenance sessions via external network connections and terminate such connections when nonlocal maintenance is complete.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MA.L2-3.7.6",
            "family": "Maintenance",
            "requirement": "Supervise the maintenance activities of maintenance personnel without required access authorization.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Supervise the maintenance activities of maintenance personnel without required access authorization.",
                "Determine whether this Maintenance requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "maintenance logs",
                "maintenance tool/media control records",
                "remote maintenance session logs"
            ]
        },
        {
            "id": "MP.L2-3.8.1",
            "family": "Media Protection",
            "requirement": "Protect (i.e., physically control and securely store) system media containing CUI, both paper and digital.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect (i.e., physically control and securely store) system media containing CUI, both paper and digital.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.2",
            "family": "Media Protection",
            "requirement": "Limit access to CUI on system media to authorized users.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit access to CUI on system media to authorized users.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.3",
            "family": "Media Protection",
            "requirement": "Sanitize or destroy system media containing CUI before disposal or release for reuse.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Sanitize or destroy system media containing CUI before disposal or release for reuse.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.4",
            "family": "Media Protection",
            "requirement": "Mark media with necessary CUI markings and distribution limitations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Mark media with necessary CUI markings and distribution limitations.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.5",
            "family": "Media Protection",
            "requirement": "Control access to media containing CUI and maintain accountability for media during transport outside of controlled areas.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control access to media containing CUI and maintain accountability for media during transport outside of controlled areas.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.6",
            "family": "Media Protection",
            "requirement": "Implement cryptographic mechanisms to protect the confidentiality of CUI stored on digital media during transport unless otherwise protected by alternative physical safeguards.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement cryptographic mechanisms to protect the confidentiality of CUI stored on digital media during transport unless otherwise protected by alternative physical safeguards.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.7",
            "family": "Media Protection",
            "requirement": "Control the use of removable media on system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control the use of removable media on system components.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.8",
            "family": "Media Protection",
            "requirement": "Prohibit the use of portable storage devices when such devices have no identifiable owner.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit the use of portable storage devices when such devices have no identifiable owner.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "MP.L2-3.8.9",
            "family": "Media Protection",
            "requirement": "Protect the confidentiality of backup CUI at storage locations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the confidentiality of backup CUI at storage locations.",
                "Determine whether this Media Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "media sanitization/destruction logs",
                "media inventory and marking records",
                "media access/transport logs",
                "backup encryption configuration"
            ]
        },
        {
            "id": "PS.L2-3.9.1",
            "family": "Personnel Security",
            "requirement": "Screen individuals prior to authorizing access to organizational systems containing CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Screen individuals prior to authorizing access to organizational systems containing CUI.",
                "Determine whether this Personnel Security requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "background screening records",
                "personnel termination/transfer checklists"
            ]
        },
        {
            "id": "PS.L2-3.9.2",
            "family": "Personnel Security",
            "requirement": "Ensure that organizational systems containing CUI are protected during and after personnel actions such as terminations and transfers.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Ensure that organizational systems containing CUI are protected during and after personnel actions such as terminations and transfers.",
                "Determine whether this Personnel Security requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "background screening records",
                "personnel termination/transfer checklists"
            ]
        },
        {
            "id": "PE.L2-3.10.1",
            "family": "Physical Protection",
            "requirement": "Limit physical access to organizational systems, equipment, and the respective operating environments to authorized individuals.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Limit physical access to organizational systems, equipment, and the respective operating environments to authorized individuals.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.2",
            "family": "Physical Protection",
            "requirement": "Protect and monitor the physical facility and support infrastructure for organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect and monitor the physical facility and support infrastructure for organizational systems.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.3",
            "family": "Physical Protection",
            "requirement": "Escort visitors and monitor visitor activity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Escort visitors and monitor visitor activity.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.4",
            "family": "Physical Protection",
            "requirement": "Maintain audit logs of physical access.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Maintain audit logs of physical access.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.5",
            "family": "Physical Protection",
            "requirement": "Control and manage physical access devices.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and manage physical access devices.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "PE.L2-3.10.6",
            "family": "Physical Protection",
            "requirement": "Enforce safeguarding measures for CUI at alternate work sites.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Enforce safeguarding measures for CUI at alternate work sites.",
                "Determine whether this Physical Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "visitor logs",
                "physical access control (badge) logs",
                "facility access device inventory",
                "alternate work site policy"
            ]
        },
        {
            "id": "RA.L2-3.11.1",
            "family": "Risk Assessment",
            "requirement": "Periodically assess the risk to organizational operations (including mission, functions, image, or reputation), organizational assets, and individuals, resulting from the operation of organizational systems and the associated processing, storage, or transmission of CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Periodically assess the risk to organizational operations (including mission, functions, image, or reputation), organizational assets, and individuals, resulting from the operation of organizational systems and the associated processing, storage, or transmission of CUI.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "RA.L2-3.11.2",
            "family": "Risk Assessment",
            "requirement": "Scan for vulnerabilities in organizational systems and applications periodically and when new vulnerabilities affecting those systems and applications are identified.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Scan for vulnerabilities in organizational systems and applications periodically and when new vulnerabilities affecting those systems and applications are identified.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "RA.L2-3.11.3",
            "family": "Risk Assessment",
            "requirement": "Remediate vulnerabilities in accordance with risk assessments.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Remediate vulnerabilities in accordance with risk assessments.",
                "Determine whether this Risk Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking"
            ]
        },
        {
            "id": "CA.L2-3.12.1",
            "family": "Security Assessment",
            "requirement": "Periodically assess the security controls in organizational systems to determine if the controls are effective in their application.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Periodically assess the security controls in organizational systems to determine if the controls are effective in their application.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.2",
            "family": "Security Assessment",
            "requirement": "Develop and implement plans of action designed to correct deficiencies and reduce or eliminate vulnerabilities in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Develop and implement plans of action designed to correct deficiencies and reduce or eliminate vulnerabilities in organizational systems.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.3",
            "family": "Security Assessment",
            "requirement": "Monitor security controls on an ongoing basis to ensure the continued effectiveness of the controls.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor security controls on an ongoing basis to ensure the continued effectiveness of the controls.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "CA.L2-3.12.4",
            "family": "Security Assessment",
            "requirement": "Develop, document, and periodically update system security plans that describe system boundaries, system environments of operation, how security requirements are implemented, and the relationships with or connections to other systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Develop, document, and periodically update system security plans that describe system boundaries, system environments of operation, how security requirements are implemented, and the relationships with or connections to other systems.",
                "Determine whether this Security Assessment requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)"
            ]
        },
        {
            "id": "SC.L2-3.13.1",
            "family": "System and Communications Protection",
            "requirement": "Monitor, control, and protect communications (i.e., information transmitted or received by organizational systems) at the external boundaries and key internal boundaries of organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor, control, and protect communications (i.e., information transmitted or received by organizational systems) at the external boundaries and key internal boundaries of organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.2",
            "family": "System and Communications Protection",
            "requirement": "Employ architectural designs, software development techniques, and systems engineering principles that promote effective information security within organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ architectural designs, software development techniques, and systems engineering principles that promote effective information security within organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.3",
            "family": "System and Communications Protection",
            "requirement": "Separate user functionality from system management functionality.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Separate user functionality from system management functionality.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.4",
            "family": "System and Communications Protection",
            "requirement": "Prevent unauthorized and unintended information transfer via shared system resources.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent unauthorized and unintended information transfer via shared system resources.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.5",
            "family": "System and Communications Protection",
            "requirement": "Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.6",
            "family": "System and Communications Protection",
            "requirement": "Deny network communications traffic by default and allow network communications traffic by exception (i.e., deny all, permit by exception).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Deny network communications traffic by default and allow network communications traffic by exception (i.e., deny all, permit by exception).",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.7",
            "family": "System and Communications Protection",
            "requirement": "Prevent remote devices from simultaneously establishing non-remote connections with organizational systems and communicating via some other connection to resources in external networks (i.e., split tunneling).",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prevent remote devices from simultaneously establishing non-remote connections with organizational systems and communicating via some other connection to resources in external networks (i.e., split tunneling).",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.8",
            "family": "System and Communications Protection",
            "requirement": "Implement cryptographic mechanisms to prevent unauthorized disclosure of CUI during transmission unless otherwise protected by alternative physical safeguards.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Implement cryptographic mechanisms to prevent unauthorized disclosure of CUI during transmission unless otherwise protected by alternative physical safeguards.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.9",
            "family": "System and Communications Protection",
            "requirement": "Terminate network connections associated with communications sessions at the end of the session or after a defined period of inactivity.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Terminate network connections associated with communications sessions at the end of the session or after a defined period of inactivity.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.10",
            "family": "System and Communications Protection",
            "requirement": "Establish and manage cryptographic keys for cryptography employed in organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Establish and manage cryptographic keys for cryptography employed in organizational systems.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.11",
            "family": "System and Communications Protection",
            "requirement": "Employ FIPS-validated cryptography when used to protect the confidentiality of CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Employ FIPS-validated cryptography when used to protect the confidentiality of CUI.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.12",
            "family": "System and Communications Protection",
            "requirement": "Prohibit remote activation of collaborative computing devices and provide indication of devices in use to users present at the device.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Prohibit remote activation of collaborative computing devices and provide indication of devices in use to users present at the device.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.13",
            "family": "System and Communications Protection",
            "requirement": "Control and monitor the use of mobile code.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor the use of mobile code.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.14",
            "family": "System and Communications Protection",
            "requirement": "Control and monitor the use of Voice over Internet Protocol (VoIP) technologies.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Control and monitor the use of Voice over Internet Protocol (VoIP) technologies.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.15",
            "family": "System and Communications Protection",
            "requirement": "Protect the authenticity of communications sessions.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the authenticity of communications sessions.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SC.L2-3.13.16",
            "family": "System and Communications Protection",
            "requirement": "Protect the confidentiality of CUI at rest.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Protect the confidentiality of CUI at rest.",
                "Determine whether this System and Communications Protection requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy"
            ]
        },
        {
            "id": "SI.L2-3.14.1",
            "family": "System and Information Integrity",
            "requirement": "Identify, report, and correct system flaws in a timely manner.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify, report, and correct system flaws in a timely manner.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.2",
            "family": "System and Information Integrity",
            "requirement": "Provide protection from malicious code at designated locations within organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Provide protection from malicious code at designated locations within organizational systems.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.3",
            "family": "System and Information Integrity",
            "requirement": "Monitor system security alerts and advisories and take action in response.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor system security alerts and advisories and take action in response.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.4",
            "family": "System and Information Integrity",
            "requirement": "Update malicious code protection mechanisms when new releases are available.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Update malicious code protection mechanisms when new releases are available.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.5",
            "family": "System and Information Integrity",
            "requirement": "Perform periodic scans of organizational systems and real-time scans of files from external sources as files are downloaded, opened, or executed.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Perform periodic scans of organizational systems and real-time scans of files from external sources as files are downloaded, opened, or executed.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.6",
            "family": "System and Information Integrity",
            "requirement": "Monitor organizational systems, including inbound and outbound communications traffic, to detect attacks and indicators of potential attacks.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Monitor organizational systems, including inbound and outbound communications traffic, to detect attacks and indicators of potential attacks.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "SI.L2-3.14.7",
            "family": "System and Information Integrity",
            "requirement": "Identify unauthorized use of organizational systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented: Identify unauthorized use of organizational systems.",
                "Determine whether this System and Information Integrity requirement is documented in policy or procedure and consistently applied across in-scope systems.",
                "Determine whether evidence demonstrates ongoing, operational effectiveness of this requirement, not just a point-in-time configuration snapshot."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking"
            ]
        },
        {
            "id": "AC.L3-3.1.2e",
            "family": "Access Control",
            "requirement": "Restrict access to systems and system components to only those information resources that are owned, provisioned, or issued by the organization.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Restrict access to systems and system components to only those information resources that are owned, provisioned, or issued by the organization.",
                "Determine whether this Access Control enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "AC.L3-3.1.3e",
            "family": "Access Control",
            "requirement": "Employ secure information transfer solutions to control information flows between security domains on connected systems.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ secure information transfer solutions to control information flows between security domains on connected systems.",
                "Determine whether this Access Control enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "authentication logs",
                "account/user list",
                "access control logs",
                "privilege / role assignment records",
                "remote access (VPN) logs",
                "firewall or ACL configurations",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "AT.L3-3.2.1e",
            "family": "Awareness and Training",
            "requirement": "Provide awareness training upon initial hire, following a significant cyber event, and at least annually, focused on recognizing and responding to threats from social engineering, advanced persistent threat actors, breaches, and suspicious behaviors; update the training at least annually or when there are significant changes to the threat.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Provide awareness training upon initial hire, following a significant cyber event, and at least annually, focused on recognizing and responding to threats from social engineering, advanced persistent threat actors, breaches, and suspicious behaviors; update the training at least annually or when there are significant changes to the threat.",
                "Determine whether this Awareness and Training enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "AT.L3-3.2.2e",
            "family": "Awareness and Training",
            "requirement": "Include practical exercises in awareness training for all users, tailored by roles, to include general users, users with specialized roles, and privileged users, that are aligned with current threat scenarios and provide feedback to individuals involved in the training and their supervisors.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Include practical exercises in awareness training for all users, tailored by roles, to include general users, users with specialized roles, and privileged users, that are aligned with current threat scenarios and provide feedback to individuals involved in the training and their supervisors.",
                "Determine whether this Awareness and Training enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "training completion records",
                "training curriculum/materials",
                "training sign-in sheets or LMS records",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "CM.L3-3.4.1e",
            "family": "Configuration Management",
            "requirement": "Establish and maintain an authoritative source and repository to provide a trusted source and accountability for approved and implemented system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Establish and maintain an authoritative source and repository to provide a trusted source and accountability for approved and implemented system components.",
                "Determine whether this Configuration Management enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "CM.L3-3.4.2e",
            "family": "Configuration Management",
            "requirement": "Employ automated mechanisms to detect misconfigured or unauthorized system components; after detection, remove the components or place the components in a quarantine or remediation network to facilitate patching, re-configuration, or other mitigations.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ automated mechanisms to detect misconfigured or unauthorized system components; after detection, remove the components or place the components in a quarantine or remediation network to facilitate patching, re-configuration, or other mitigations.",
                "Determine whether this Configuration Management enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "CM.L3-3.4.3e",
            "family": "Configuration Management",
            "requirement": "Employ automated discovery and management tools to maintain an up-to-date, complete, accurate, and readily available inventory of system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ automated discovery and management tools to maintain an up-to-date, complete, accurate, and readily available inventory of system components.",
                "Determine whether this Configuration Management enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "configuration baselines",
                "change management/change control records",
                "software inventory",
                "hardening/benchmark scan results",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "IA.L3-3.5.1e",
            "family": "Identification and Authentication",
            "requirement": "Identify and authenticate systems and system components, where possible, before establishing a network connection using bidirectional authentication that is cryptographically based and replay resistant.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Identify and authenticate systems and system components, where possible, before establishing a network connection using bidirectional authentication that is cryptographically based and replay resistant.",
                "Determine whether this Identification and Authentication enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "IA.L3-3.5.3e",
            "family": "Identification and Authentication",
            "requirement": "Employ automated or manual/procedural mechanisms to prohibit system components from connecting to organizational systems unless the components are known, authenticated, in a properly configured state, or in a trust profile.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ automated or manual/procedural mechanisms to prohibit system components from connecting to organizational systems unless the components are known, authenticated, in a properly configured state, or in a trust profile.",
                "Determine whether this Identification and Authentication enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "authentication logs",
                "MFA logs",
                "login events",
                "password policy configuration",
                "identifier/account lifecycle records",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "IR.L3-3.6.1e",
            "family": "Incident Response",
            "requirement": "Establish and maintain a security operations center capability that operates 24/7, with allowance for remote/on-call staff.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Establish and maintain a security operations center capability that operates 24/7, with allowance for remote/on-call staff.",
                "Determine whether this Incident Response enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "IR.L3-3.6.2e",
            "family": "Incident Response",
            "requirement": "Establish and maintain a cyber-incident response team that can be deployed by the organization within 24 hours.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Establish and maintain a cyber-incident response team that can be deployed by the organization within 24 hours.",
                "Determine whether this Incident Response enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "incident response plan",
                "incident logs/tickets",
                "incident response test/exercise records",
                "security alerts",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "PS.L3-3.9.2e",
            "family": "Personnel Security",
            "requirement": "Ensure that organizational systems are protected if adverse information develops or is obtained about individuals with access to CUI.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Ensure that organizational systems are protected if adverse information develops or is obtained about individuals with access to CUI.",
                "Determine whether this Personnel Security enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "background screening records",
                "personnel termination/transfer checklists",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.1e",
            "family": "Risk Assessment",
            "requirement": "Employ threat intelligence, at a minimum from open or commercial sources, and any DoD-provided sources, as part of a risk assessment to guide and inform the development of organizational systems, security architectures, selection of security solutions, monitoring, threat hunting, and response and recovery activities.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ threat intelligence, at a minimum from open or commercial sources, and any DoD-provided sources, as part of a risk assessment to guide and inform the development of organizational systems, security architectures, selection of security solutions, monitoring, threat hunting, and response and recovery activities.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.2e",
            "family": "Risk Assessment",
            "requirement": "Conduct cyber threat hunting activities on an on-going aperiodic basis or when indications warrant, to search for indicators of compromise in organizational systems and detect, track, and disrupt threats that evade existing controls.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Conduct cyber threat hunting activities on an on-going aperiodic basis or when indications warrant, to search for indicators of compromise in organizational systems and detect, track, and disrupt threats that evade existing controls.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.3e",
            "family": "Risk Assessment",
            "requirement": "Employ advanced automation and analytics capabilities in support of analysts to predict and identify risks to organizations, systems, and system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ advanced automation and analytics capabilities in support of analysts to predict and identify risks to organizations, systems, and system components.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.4e",
            "family": "Risk Assessment",
            "requirement": "Document or reference in the system security plan the security solution selected, the rationale for the security solution, and the risk determination.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Document or reference in the system security plan the security solution selected, the rationale for the security solution, and the risk determination.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.5e",
            "family": "Risk Assessment",
            "requirement": "Assess the effectiveness of security solutions at least annually or upon receipt of relevant cyber threat information, or in response to a relevant cyber incident, to address anticipated risk to organizational systems and the organization based on current and accumulated threat intelligence.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Assess the effectiveness of security solutions at least annually or upon receipt of relevant cyber threat information, or in response to a relevant cyber incident, to address anticipated risk to organizational systems and the organization based on current and accumulated threat intelligence.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.6e",
            "family": "Risk Assessment",
            "requirement": "Assess, respond to, and monitor supply chain risks associated with organizational systems and system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Assess, respond to, and monitor supply chain risks associated with organizational systems and system components.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "RA.L3-3.11.7e",
            "family": "Risk Assessment",
            "requirement": "Develop a plan for managing supply chain risks associated with organizational systems and system components; update the plan at least annually, and upon receipt of relevant cyber threat information, or in response to a relevant cyber incident.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Develop a plan for managing supply chain risks associated with organizational systems and system components; update the plan at least annually, and upon receipt of relevant cyber threat information, or in response to a relevant cyber incident.",
                "Determine whether this Risk Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "risk assessment reports",
                "vulnerability scan results",
                "POA&M/remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "CA.L3-3.12.1e",
            "family": "Security Assessment",
            "requirement": "Conduct penetration testing at least annually or when significant security changes are made to the system, leveraging automated scanning tools and ad hoc tests using subject matter experts.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Conduct penetration testing at least annually or when significant security changes are made to the system, leveraging automated scanning tools and ad hoc tests using subject matter experts.",
                "Determine whether this Security Assessment enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "security assessment reports",
                "POA&M records",
                "continuous monitoring reports",
                "system security plan (SSP)",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "SC.L3-3.13.4e",
            "family": "System and Communications Protection",
            "requirement": "Employ physical isolation techniques or logical isolation techniques or both in organizational systems and system components.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Employ physical isolation techniques or logical isolation techniques or both in organizational systems and system components.",
                "Determine whether this System and Communications Protection enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "firewall logs",
                "IDS/IPS logs",
                "network architecture diagrams",
                "encryption/key management configuration",
                "VoIP/mobile code policy",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "SI.L3-3.14.1e",
            "family": "System and Information Integrity",
            "requirement": "Verify the integrity of security critical and essential software using root of trust mechanisms or cryptographic signatures.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Verify the integrity of security critical and essential software using root of trust mechanisms or cryptographic signatures.",
                "Determine whether this System and Information Integrity enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "SI.L3-3.14.3e",
            "family": "System and Information Integrity",
            "requirement": "Ensure that specialized assets including IoT, IIoT, OT, GFE, Restricted Information Systems, and test equipment are included in the scope of the specified enhanced security requirements or are segregated in purpose-specific networks.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Ensure that specialized assets including IoT, IIoT, OT, GFE, Restricted Information Systems, and test equipment are included in the scope of the specified enhanced security requirements or are segregated in purpose-specific networks.",
                "Determine whether this System and Information Integrity enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        },
        {
            "id": "SI.L3-3.14.6e",
            "family": "System and Information Integrity",
            "requirement": "Use threat indicator information and effective mitigations obtained from, at a minimum, open or commercial sources, and any DoD-provided sources, to guide and inform intrusion detection and threat hunting.",
            "assessment_objectives": [
                "Determine whether the organization has implemented the enhanced requirement: Use threat indicator information and effective mitigations obtained from, at a minimum, open or commercial sources, and any DoD-provided sources, to guide and inform intrusion detection and threat hunting.",
                "Determine whether this System and Information Integrity enhanced requirement is operating for the specific high-value assets or critical program systems in scope for Level 3, not merely the Level 2 baseline.",
                "Determine whether any DoD-assigned Organization-Defined Parameter (ODP) associated with this requirement is being met.",
                "Determine whether the control is demonstrably operational (e.g. produces logs, alerts, or reports) rather than only documented as a policy."
            ],
            "evidence_types": [
                "vulnerability scans",
                "patch logs",
                "endpoint/antivirus alerts",
                "system/network monitoring logs",
                "flaw remediation tracking",
                "threat intelligence / open-source or DoD-provided threat feeds",
                "24/7 SOC monitoring or on-call staffing records",
                "penetration test or advanced analytics/automation output"
            ]
        }
    ]
}


# ============================================================
# HELPER: GET CONTROLS
# ============================================================

def get_controls(level):

    return CMMC_CONTROLS.get(
        level,
        []
    )


# ============================================================
# EVIDENCE REDACTION (privacy protection before AI submission)
# ============================================================
#
# Strips sensitive identifiers out of evidence text BEFORE it is
# sent to the third-party Groq API for analysis. Each unique
# value found is replaced with a stable placeholder token for the
# duration of one assessment run (e.g. "10.0.0.5" -> "[IP_1]"),
# so the same real value always maps to the same token across all
# batches and controls in this run — this preserves the AI's
# ability to reason about the evidence ("the same host appears in
# 3 events") without exposing the real value. The token mapping
# lives only in st.session_state for this browser session; it is
# never sent to the AI, never written to disk, and is cleared
# whenever the session is cleared.
#
# Categories covered: IPv4/IPv6 addresses, MAC addresses, email
# addresses, Windows SIDs, Windows/Unix file paths, phone
# numbers, internal hostnames/FQDNs, and DOMAIN\username pairs.
# This is a heuristic, defense-in-depth pass — not a guarantee
# that every possible identifier is caught — so it complements,
# rather than replaces, your organization's own data-handling
# policy for what evidence should be uploaded in the first place.
#
# ============================================================

REDACTION_PATTERNS = [
    ("IP", re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')),
    ("IPV6", re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b')),
    ("MAC", re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b')),
    ("EMAIL", re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')),
    ("SID", re.compile(r'\bS-1-5-\d{2}(?:-\d+){3,}\b')),
    ("WINPATH", re.compile(r'\b[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*')),
    ("UNIXPATH", re.compile(r'(?<![\w.])/(?:[\w.\-]+/)+[\w.\-]*')),
    ("DOMAINUSER", re.compile(r'\b[A-Za-z0-9_.\-]+\\[A-Za-z0-9_.\-]+\b')),
    ("PHONE", re.compile(r'\b\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')),
    ("HOSTNAME", re.compile(
        r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+'
        r'(?:corp|local|internal|lan|com|net|org|io)\b',
        re.IGNORECASE
    )),
]


def get_redaction_state():
    """
    Returns the per-session token map + counters used by
    redact_evidence_text, creating them on first use. Both live
    only in st.session_state — never persisted to disk, never
    sent to the AI — so the mapping between a placeholder token
    and the real value it stands for exists only in this browser
    session.
    """

    if "redaction_token_map" not in st.session_state:

        st.session_state["redaction_token_map"] = {}

    if "redaction_counters" not in st.session_state:

        st.session_state["redaction_counters"] = {}

    return (
        st.session_state["redaction_token_map"],
        st.session_state["redaction_counters"]
    )


def redact_evidence_text(text, token_map, counters):
    """
    Replaces sensitive identifiers in `text` with stable
    placeholder tokens, e.g. "10.0.0.5" -> "[IP_1]". The same
    real value always maps to the same token within one run
    (via `token_map`), so the AI can still reason about repeated
    identifiers ("this IP shows up 3 times") without ever seeing
    the real value.
    """

    if not text:

        return text

    def _replace(match, label):

        value = match.group(0)

        key = (label, value)

        if key not in token_map:

            counters[label] = counters.get(label, 0) + 1

            token_map[key] = f"[{label}_{counters[label]}]"

        return token_map[key]

    redacted = text

    for label, pattern in REDACTION_PATTERNS:

        redacted = pattern.sub(
            lambda m, label=label: _replace(m, label),
            redacted
        )

    return redacted


# ============================================================
# LOG PARSER
# ============================================================

def parse_log_file(uploaded_file):

    filename = uploaded_file.name.lower()

    content = uploaded_file.read()


    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    if filename.endswith(".csv"):

        df = pd.read_csv(
            io.BytesIO(content)
        )

        return normalize_dataframe(df)


    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    elif filename.endswith(".json"):

        data = json.loads(
            content.decode(
                "utf-8",
                errors="ignore"
            )
        )

        if isinstance(data, list):

            df = pd.DataFrame(data)

        else:

            df = pd.json_normalize(data)

        return normalize_dataframe(df)


    # --------------------------------------------------------
    # XML
    # --------------------------------------------------------

    elif filename.endswith(".xml"):

        try:

            root = ET.fromstring(
                content
            )

            records = []

            for element in root.iter():

                record = {

                    child.tag:
                        child.text

                    for child in element

                    if child.text

                }

                if record:

                    records.append(
                        record
                    )


            if records:

                df = pd.DataFrame(
                    records
                )

                return normalize_dataframe(
                    df
                )

            return content.decode(
                "utf-8",
                errors="ignore"
            )

        except Exception:

            return content.decode(
                "utf-8",
                errors="ignore"
            )


    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    elif filename.endswith(".txt"):

        return content.decode(
            "utf-8",
            errors="ignore"
        )


    else:

        raise ValueError(
            "Unsupported file type. "
            "Use CSV, XML, JSON, or TXT."
        )


# ============================================================
# NORMALIZE LOG DATA
# ============================================================

def normalize_dataframe(df):

    df.columns = [

        str(column)
        .strip()
        .lower()
        .replace(" ", "_")

        for column in df.columns

    ]


    df = df.fillna("")


    for column in df.columns:

        df[column] = (

            df[column]
            .astype(str)
            .str.strip()

        )


    return df


# ============================================================
# PREPARE EVIDENCE FOR AI
# ============================================================

def chunk_evidence(
    parsed_data,
    rows_per_chunk=12,
    chars_per_chunk=3500,
    max_chunks=12
):

    # --------------------------------------------------------
    # DATAFRAME EVIDENCE (CSV / JSON / XML parsed to rows)
    # --------------------------------------------------------

    if isinstance(
        parsed_data,
        pd.DataFrame
    ):

        chunks = []

        for start in range(
            0,
            len(parsed_data),
            rows_per_chunk
        ):

            chunk_df = parsed_data.iloc[
                start:start + rows_per_chunk
            ]

            chunks.append(
                json.dumps(
                    chunk_df.to_dict(
                        orient="records"
                    ),
                    indent=2
                )
            )

        if not chunks:

            chunks = [
                json.dumps([])
            ]

        return chunks[:max_chunks]


    # --------------------------------------------------------
    # RAW TEXT EVIDENCE (TXT / unparsed XML)
    # --------------------------------------------------------

    if isinstance(
        parsed_data,
        str
    ):

        chunks = [

            parsed_data[i:i + chars_per_chunk]

            for i in range(
                0,
                len(parsed_data),
                chars_per_chunk
            )

        ]

        if not chunks:

            chunks = [""]

        return chunks[:max_chunks]


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    text = str(parsed_data)

    chunks = [

        text[i:i + chars_per_chunk]

        for i in range(
            0,
            len(text),
            chars_per_chunk
        )

    ]

    return (chunks or [""])[:max_chunks]


# ============================================================
# AGGREGATE MULTI-BATCH RESULTS INTO ONE FINDING PER CONTROL
# ============================================================

STATUS_PRIORITY = {

    "NON-COMPLIANT": 0,
    "PARTIALLY COMPLIANT": 1,
    "INSUFFICIENT EVIDENCE": 2,
    "COMPLIANT": 3

}


def aggregate_chunk_results(
    control,
    chunk_results
):

    if len(chunk_results) == 1:

        return chunk_results[0]


    statuses = [

        result.get(
            "status",
            "INSUFFICIENT EVIDENCE"
        )

        for result in chunk_results

    ]

    worst_status = min(

        statuses,

        key=lambda status: STATUS_PRIORITY.get(
            status,
            2
        )

    )


    severity = "UNKNOWN"

    for result in chunk_results:

        if result.get("status") == worst_status:

            severity = result.get(
                "severity",
                "UNKNOWN"
            )

            break


    confidences = [

        result.get("confidence", 0)

        for result in chunk_results

        if isinstance(
            result.get("confidence"),
            (int, float)
        )

    ]

    avg_confidence = (

        int(sum(confidences) / len(confidences))

        if confidences

        else 0

    )


    supporting = []

    missing = []

    reasoning_parts = []


    for index, result in enumerate(chunk_results):

        for item in result.get("supporting_evidence", []):

            if item not in supporting:

                supporting.append(item)


        for item in result.get("missing_evidence", []):

            if item not in missing:

                missing.append(item)


        if result.get("assessment_reasoning"):

            reasoning_parts.append(

                f"[Batch {index + 1}] "
                f"{result['assessment_reasoning']}"

            )


    return {

        "control_id":
            control["id"],

        "status":
            worst_status,

        "severity":
            severity,

        "confidence":
            avg_confidence,

        "evidence_summary":
            f"Aggregated across {len(chunk_results)} "
            "evidence batches from this file.",

        "supporting_evidence":
            supporting,

        "missing_evidence":
            missing,

        "assessment_reasoning":
            " ".join(reasoning_parts),

        "remediation":
            chunk_results[0].get(
                "remediation",
                ""
            ),

        "recommended_assessor_action":
            chunk_results[0].get(
                "recommended_assessor_action",
                ""
            )

    }


# ============================================================
# AI CONTROL ANALYSIS
# ============================================================

def analyze_control(
    control,
    evidence,
    cmmc_level,
    framework_version
):

    if client is None:

        return {

            "control_id":
                control["id"],

            "status":
                "INSUFFICIENT EVIDENCE",

            "severity":
                "UNKNOWN",

            "confidence":
                0,

            "evidence_summary":
                "Groq API key is not configured.",

            "supporting_evidence": [],

            "missing_evidence": [

                "Configure GROQ_API_KEY."

            ],

            "assessment_reasoning":
                "AI analysis could not be performed.",

            "remediation":
                "Configure the Groq API key.",

            "recommended_assessor_action":
                "Verify API configuration."

        }


    system_prompt = """
You are GetRight, an AI-assisted cybersecurity
assessment analyst.

You assist a qualified human assessor.

Analyze evidence against ONE specific cybersecurity
requirement.

RULES:

1. Never fabricate evidence.

2. Never assume compliance because no violation
appears in the supplied logs.

3. Logs are evidence, not automatically proof
of organizational compliance.

4. Use only these statuses:

COMPLIANT
PARTIALLY COMPLIANT
NON-COMPLIANT
INSUFFICIENT EVIDENCE

5. Requirements involving policies, procedures,
configurations, interviews, documentation,
personnel, or physical controls may require
evidence beyond logs.

6. Identify evidence supporting the finding.

7. Identify missing evidence.

8. Recommend remediation.

9. Do not make a final certification decision.

10. When evidence is ambiguous, use
INSUFFICIENT EVIDENCE.

11. Confidence must be between 0 and 100.

12. Use only these severity values:

CRITICAL
HIGH
MEDIUM
LOW

Severity should be "LOW" (not "UNKNOWN") when
status is COMPLIANT.

Return ONLY valid JSON.
"""


    user_prompt = f"""

CMMC LEVEL:

{cmmc_level}


FRAMEWORK VERSION:

{framework_version}


CONTROL ID:

{control['id']}


CONTROL FAMILY:

{control['family']}


REQUIREMENT:

{control['requirement']}


ASSESSMENT OBJECTIVES:

{json.dumps(
    control['assessment_objectives'],
    indent=2
)}


EXPECTED EVIDENCE:

{json.dumps(
    control['evidence_types'],
    indent=2
)}


COLLECTED LOG EVIDENCE:

{evidence}


Return JSON using this exact structure:

{{
    "control_id": "{control['id']}",
    "status": "",
    "severity": "",
    "confidence": 0,
    "evidence_summary": "",
    "supporting_evidence": [],
    "missing_evidence": [],
    "assessment_reasoning": "",
    "remediation": "",
    "recommended_assessor_action": ""
}}
"""


    try:
        response, used_model = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            max_tokens=800
        )
        result = response.choices[0].message.content
        return json.loads(result)

    except Exception as error:
        return {

            "control_id":
                control["id"],

            "status":
                "INSUFFICIENT EVIDENCE",

            "severity":
                "UNKNOWN",

            "confidence":
                0,

            "evidence_summary":
                "AI analysis failed.",

            "supporting_evidence": [],

            "missing_evidence": [],

            "assessment_reasoning":
                str(error),

            "remediation":
                "Correct the AI configuration "
                "and rerun the assessment.",

            "recommended_assessor_action":
                "Review application/API configuration."

        }


# ============================================================
# TIME FORMATTING HELPER
# ============================================================

def format_elapsed(seconds):

    seconds = int(seconds)

    minutes, seconds = divmod(seconds, 60)

    hours, minutes = divmod(minutes, 60)

    if hours > 0:

        return f"{hours}h {minutes}m {seconds}s"

    if minutes > 0:

        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


# ============================================================
# RUN ASSESSMENT
# ============================================================

def run_assessment(
    parsed_data,
    cmmc_level,
    framework_version
):

    controls = get_controls(
        cmmc_level
    )


    if not controls:

        raise ValueError(
            "No controls are configured for "
            f"{cmmc_level}."
        )


    evidence_chunks = chunk_evidence(
        parsed_data
    )


    results = []


    progress = st.progress(
        0
    )


    status_text = st.empty()


    elapsed_text = st.empty()


    total = len(
        controls
    )


    start_time = time.time()


    for index, control in enumerate(
        controls
    ):

        status_text.write(

            f"Analyzing "
            f"{control['id']} "
            f"({index + 1}/{total}) "
            f"across {len(evidence_chunks)} "
            "evidence batch(es)..."

        )


        elapsed_text.caption(

            f"⏱️ Time elapsed: "
            f"{format_elapsed(time.time() - start_time)}"

        )


        chunk_results = []


        for chunk in evidence_chunks:

            if st.session_state.get("redact_evidence_enabled", True):

                token_map, counters = get_redaction_state()

                evidence_to_send = redact_evidence_text(
                    chunk,
                    token_map,
                    counters
                )

            else:

                evidence_to_send = chunk

            chunk_result = analyze_control(

                control=control,

                evidence=evidence_to_send,

                cmmc_level=cmmc_level,

                framework_version=framework_version

            )


            chunk_results.append(
                chunk_result
            )


            elapsed_text.caption(

                f"⏱️ Time elapsed: "
                f"{format_elapsed(time.time() - start_time)}"

            )


            # Pause between requests. Groq's free tier for this
            # model allows only 6000 tokens/minute total, so
            # requests need real spacing, not just smaller size.

            time.sleep(5)


        aggregated_result = aggregate_chunk_results(

            control,

            chunk_results

        )


        results.append(
            aggregated_result
        )


        progress.progress(
            (index + 1) / total
        )


    file_elapsed_seconds = time.time() - start_time


    status_text.success(

        f"AI analysis completed in "
        f"{format_elapsed(file_elapsed_seconds)}."

    )


    elapsed_text.caption(

        f"⏱️ Total time elapsed: "
        f"{format_elapsed(file_elapsed_seconds)}"

    )


    return results, file_elapsed_seconds


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title(
    "🛡️ GetRight CMMC Assessment"
)

st.caption(
    "AI-assisted cybersecurity evidence analysis "
    "for CMMC assessments."
)


# ============================================================
# API STATUS
# ============================================================

if client:

    st.success(
        "🤖 AI Analyzer: Connected (Groq)"
    )

else:

    st.warning(
        "⚠️ AI Analyzer: API key not configured. "
        "Add GROQ_API_KEY to your Streamlit secrets "
        "(or a local .env file)."
    )


# ============================================================
# PRIVACY & SESSION CONTROLS
# ============================================================

with st.expander("🔐 Privacy & Session Controls"):

    st.caption(
        "Company info, uploaded evidence, and assessment results "
        "are held only in this browser session's memory — this "
        "app does not write your log files or findings to disk. "
        "They persist only until you close this tab, click "
        "'Clear all session data' below, or (if you choose to) "
        "log summary counts to the Customer Impact Dashboard."
    )

    redact_evidence_enabled = st.checkbox(
        "🔒 Redact sensitive identifiers before sending evidence "
        "to the AI",
        value=st.session_state.get("redact_evidence_enabled", True),
        key="redact_evidence_enabled",
        help=(
            "When enabled, IPs, MAC addresses, emails, hostnames, "
            "file paths, phone numbers, Windows SIDs, and "
            "DOMAIN\\username pairs found in your evidence are "
            "replaced with placeholder tokens (e.g. \"[IP_1]\") "
            "before any content leaves this app for the Groq API. "
            "The same real value always maps to the same token "
            "within one run, so the AI can still reason about "
            "repeated identifiers. The token-to-real-value mapping "
            "stays in this browser session only — never sent to "
            "the AI, never written to disk."
        )
    )

    if st.button("🗑️ Clear all session data now"):

        for key in list(st.session_state.keys()):

            del st.session_state[key]

        st.rerun()


# ============================================================
# CMMC SELECTION
# ============================================================
if "company_info" not in st.session_state:
    st.session_state.company_info = {
        "company_name": "",
        "representative": "",
        "representative_email": "",
    }

with st.form("company_info_form"):
    st.header("Company Information")
    company_name = st.text_input("Company Name", value=st.session_state.company_info["company_name"])
    representative = st.text_input("Company Representative", value=st.session_state.company_info["representative"])
    representative_email = st.text_input("Representative's Email", value=st.session_state.company_info["representative_email"])
    submitted = st.form_submit_button("Save company info")

    if submitted:
        st.session_state.company_info["company_name"] = company_name.strip()
        st.session_state.company_info["representative"] = representative.strip()
        st.session_state.company_info["representative_email"] = representative_email.strip()

        if not company_name or not representative or not representative_email:
            st.error("All fields are required before you can analyze evidence for CMMC compliance.")
        else:
            st.success("Company information saved. You can now analyze evidence.")

is_complete = all(
    st.session_state.company_info[field] 
    for field in ("company_name", "representative", "representative_email")
)

st.divider()

cmmc_level = st.selectbox(

    "Which CMMC Level Are We Auditing?",

    [
        "CMMC Level 1",
        "CMMC Level 2",
        "CMMC Level 3"
    ],

    index=None,

    placeholder=
        "Select a CMMC Level..."

)


framework_version = st.selectbox(

    "Assessment Framework",

    [
        "CMMC Current / DoW Requirements",
        "NIST SP 800-171 Rev. 2",
        "NIST SP 800-171 Rev. 3"
    ]

)


# ============================================================
# SHOW CONTROL COUNT
# ============================================================

if cmmc_level:

    controls = get_controls(
        cmmc_level
    )

    st.info(

        f"{cmmc_level} currently has "
        f"{len(controls)} configured controls "
        "in this application."

    )


# ============================================================
# FILE UPLOAD
# ============================================================

st.subheader(
    "Cybersecurity Evidence"
)


uploaded_files = st.file_uploader(

    "Upload cybersecurity log files",

    type=[
        "csv",
        "xml",
        "json",
        "txt"
    ],

    accept_multiple_files=True,

    help=(
        "Upload Windows, Linux, macOS, "
        "firewall, SIEM, EDR, authentication, "
        "or other cybersecurity logs. Large files "
        "are automatically split into batches and "
        "analyzed sequentially (this takes longer "
        "but works within the free Groq API tier)."
    )

)


st.caption(

    "Note: large files are processed in small batches "
    "(up to 12 batches per file) to stay within Groq's "
    "free-tier rate limit (6,000 tokens/minute for this "
    "model). This means analysis can take a while — "
    "roughly 5-10 seconds per batch, per control. A file "
    "with several controls and multiple batches may take "
    "several minutes to fully process."

)


# ============================================================
# FILE PREVIEW
# ============================================================

if uploaded_files:

    st.write(
        f"**{len(uploaded_files)} file(s) uploaded**"
    )


    for file in uploaded_files:

        st.write(
            f"📄 {file.name}"
        )


# ============================================================
# ANALYZE BUTTON
# ============================================================

st.divider()


analyze_button = st.button(

    "🤖 Analyze Evidence for CMMC Compliance",

    type="primary",

    use_container_width=True

)


if analyze_button:

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not cmmc_level:

        st.error(
            "Please select a CMMC Level."
        )

        st.stop()


    if not uploaded_files:

        st.error(
            "Please upload at least one "
            "cybersecurity log file."
        )

        st.stop()


    if not client:

        st.error(

            "Groq API key is not configured. "

            "Add GROQ_API_KEY to your Streamlit secrets."

        )

        st.stop()


    # --------------------------------------------------------
    # ANALYSIS
    # --------------------------------------------------------

    all_results = []


    overall_start_time = time.time()


    for uploaded_file in uploaded_files:

        try:

            st.markdown(
                f"**Processing {uploaded_file.name}**"
            )


            parsed_data = parse_log_file(
                uploaded_file
            )


            results, file_elapsed_seconds = run_assessment(

                parsed_data,

                cmmc_level,

                framework_version

            )


            all_results.append({

                "filename":
                    uploaded_file.name,

                "results":
                    results,

                "elapsed_seconds":
                    file_elapsed_seconds

            })


        except Exception as error:

            st.error(

                f"Error processing "
                f"{uploaded_file.name}: "
                f"{error}"

            )


    total_elapsed_seconds = time.time() - overall_start_time


    # --------------------------------------------------------
    # STORE RESULTS
    # --------------------------------------------------------

    st.session_state[
        "assessment_results"
    ] = all_results


    st.session_state[
        "assessment_level"
    ] = cmmc_level


    st.session_state[
        "assessment_framework"
    ] = framework_version


    st.session_state[
        "assessment_total_elapsed_seconds"
    ] = total_elapsed_seconds

    # A fresh set of results invalidates any prior "logged to
    # dashboard" confirmation from an earlier assessment run.
    st.session_state["logged_to_dashboard"] = False


    st.success(

        f"Assessment analysis completed in "
        f"{format_elapsed(total_elapsed_seconds)} "
        f"total."

    )


# ============================================================
# CHART COLORS (matched to PDF status colors)
# ============================================================

STATUS_HEX = {

    "COMPLIANT":
        "#1a7f37",

    "PARTIALLY COMPLIANT":
        "#9a6700",

    "NON-COMPLIANT":
        "#cf222e",

    "INSUFFICIENT EVIDENCE":
        "#57606a"

}

STATUS_ORDER = [
    "COMPLIANT",
    "PARTIALLY COMPLIANT",
    "NON-COMPLIANT",
    "INSUFFICIENT EVIDENCE"
]


# ============================================================
# LOOK UP A CONTROL'S FAMILY BY ID
# ============================================================

def get_family_for_control(
    cmmc_level,
    control_id
):

    for control in get_controls(cmmc_level):

        if control["id"] == control_id:

            return control["family"]

    return "Unknown"


def get_control_definition(
    cmmc_level,
    control_id
):

    for control in get_controls(cmmc_level):

        if control["id"] == control_id:

            return control

    return None


# ============================================================
# RISK MANAGEMENT MATRIX HELPERS
# ============================================================
#
# Likelihood is derived from the compliance status (a
# NON-COMPLIANT finding is more likely to represent a real,
# actionable gap than one flagged INSUFFICIENT EVIDENCE).
#
# Impact is derived from the AI-assigned severity for that
# finding. Both are heuristics meant to help a human assessor
# triage — not a certified risk-scoring methodology.
#
# ============================================================

SEVERITY_IMPACT_SCORE = {

    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "UNKNOWN": 3,
    "ERROR": 3

}

STATUS_LIKELIHOOD_SCORE = {

    "NON-COMPLIANT": 5,
    "PARTIALLY COMPLIANT": 3,
    "INSUFFICIENT EVIDENCE": 2

}

# (score_threshold, label, hex_color) — checked high to low
PRIORITY_BANDS = [

    (20, "Critical", "#b91c1c"),
    (12, "High", "#c2410c"),
    (6, "Medium", "#a16207"),
    (0, "Low", "#4d7c0f")

]


def priority_band(score):

    for threshold, label, color in PRIORITY_BANDS:

        if score >= threshold:

            return label, color

    return "Low", "#4d7c0f"


def severity_to_impact_score(severity):

    if not severity:

        return 3

    return SEVERITY_IMPACT_SCORE.get(
        str(severity).upper().strip(),
        3
    )


def compute_risk_findings(all_findings):
    """
    Returns only findings that represent an OPEN risk
    (i.e. not COMPLIANT), each annotated with a likelihood
    score, impact score, priority score, and priority band —
    sorted highest priority first.
    """

    risk_findings = []

    for finding in all_findings:

        status = finding.get(
            "status",
            "INSUFFICIENT EVIDENCE"
        )

        if status not in STATUS_LIKELIHOOD_SCORE:

            continue  # COMPLIANT findings carry no open risk

        likelihood = STATUS_LIKELIHOOD_SCORE[status]

        impact = severity_to_impact_score(
            finding.get("severity")
        )

        score = likelihood * impact

        label, color = priority_band(score)

        annotated = finding.copy()

        annotated["likelihood_score"] = likelihood
        annotated["impact_score"] = impact
        annotated["priority_score"] = score
        annotated["priority_label"] = label
        annotated["priority_color"] = color

        risk_findings.append(annotated)

    risk_findings.sort(
        key=lambda item: item["priority_score"],
        reverse=True
    )

    return risk_findings


def build_risk_matrix_chart_image(risk_findings):

    if not risk_findings:

        return None

    fig, ax = plt.subplots(figsize=(7.5, 5))

    seen_coords = {}

    bands_labeled = set()

    for finding in risk_findings:

        x = finding["likelihood_score"]
        y = finding["impact_score"]

        key = (x, y)

        offset = seen_coords.get(key, 0) * 0.15

        seen_coords[key] = seen_coords.get(key, 0) + 1

        label = finding["priority_label"]

        plot_label = label if label not in bands_labeled else None

        bands_labeled.add(label)

        ax.scatter(
            x + offset,
            y + offset,
            s=180,
            color=finding["priority_color"],
            edgecolors="black",
            linewidths=0.6,
            zorder=3,
            label=plot_label
        )

        ax.annotate(
            finding.get("control_id", ""),
            (x + offset, y + offset),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=7
        )

    ax.set_xlim(1, 6)
    ax.set_ylim(1, 6)

    ax.set_xlabel(
        "Likelihood  (derived from compliance status)",
        fontsize=9
    )

    ax.set_ylabel(
        "Impact  (derived from AI-assigned severity)",
        fontsize=9
    )

    ax.set_title(
        "Risk Management Matrix — Open Findings",
        fontsize=12
    )

    ax.set_xticks([2, 3, 5])

    ax.set_xticklabels(
        ["Insufficient\nEvidence", "Partially\nCompliant", "Non-\nCompliant"],
        fontsize=7
    )

    ax.set_yticks([2, 3, 4, 5])

    ax.set_yticklabels(
        ["Low", "Medium", "High", "Critical"],
        fontsize=7
    )

    ax.grid(True, linestyle="--", alpha=0.3, zorder=0)

    ax.legend(loc="upper left", fontsize=7, frameon=True)

    fig.tight_layout()

    buffer = io.BytesIO()

    fig.savefig(buffer, format="png", dpi=150)

    plt.close(fig)

    buffer.seek(0)

    return buffer


def risk_recommended_timeframe(priority_label):

    if priority_label == "Critical":

        return "Immediate"

    if priority_label == "High":

        return "30 days"

    if priority_label == "Medium":

        return "90 days"

    return "Monitor"


# ============================================================
# OVERALL COMPLIANCE RATING (per CMMC Level)
# ============================================================
#
# This gives a single, easy-to-read score per CMMC Level: how
# many of the level's controls are compliant out of the total
# number of controls in that level, the resulting percentage,
# and a Compliant / Not Compliant rating.
#
# Because an assessment can include multiple evidence files,
# a single control may have been assessed once per file. Before
# scoring, findings are first aggregated to ONE finding per
# control (using the same worst-status-wins logic already used
# to combine evidence batches within a single file), so that a
# control is only counted as compliant if it is compliant across
# every file it was assessed against.
#
# This is a tool-level scoring convention for this application —
# a control must be found COMPLIANT to count toward the score,
# and the level is only rated "Compliant" at 100%. It is distinct
# from the official DoD/SPRS scoring methodology used in a
# certified CMMC assessment, which uses weighted point values
# per requirement rather than a simple percentage.
#
# ============================================================

def aggregate_findings_across_files(all_findings, cmmc_level):
    """
    Groups findings by control_id across every uploaded file and
    collapses each group to a single finding using the worst-status
    -wins aggregation already used for in-file evidence batches.
    """

    findings_by_control = {}

    for finding in all_findings:

        control_id = finding.get("control_id", "")

        findings_by_control.setdefault(control_id, []).append(finding)

    aggregated = []

    for control_id, findings_for_control in findings_by_control.items():

        control_def = get_control_definition(
            cmmc_level,
            control_id
        ) or {"id": control_id}

        aggregated.append(
            aggregate_chunk_results(
                control_def,
                findings_for_control
            )
        )

    return aggregated


def compute_overall_level_assessment(all_findings, cmmc_level):
    """
    Returns the overall compliance rating and projected remediation
    timeframe for a CMMC Level, based on every control defined for
    that level and every finding produced against it.
    """

    total_controls = len(get_controls(cmmc_level))

    aggregated_findings = aggregate_findings_across_files(
        all_findings,
        cmmc_level
    )

    controls_assessed = len(aggregated_findings)

    compliant_count = sum(

        1

        for finding in aggregated_findings

        if finding.get("status") == "COMPLIANT"

    )

    percentage = (

        (compliant_count / total_controls) * 100

        if total_controls > 0

        else 0

    )

    is_fully_compliant = (

        total_controls > 0
        and controls_assessed == total_controls
        and compliant_count == total_controls

    )

    rating_label = "Compliant" if is_fully_compliant else "Not Compliant"

    risk_findings = compute_risk_findings(aggregated_findings)

    if risk_findings:

        highest_priority_finding = risk_findings[0]

        highest_open_priority = highest_priority_finding["priority_label"]

        projected_remediation_timeframe = risk_recommended_timeframe(
            highest_open_priority
        )

    else:

        highest_open_priority = None

        projected_remediation_timeframe = (

            "Not applicable — no open findings"

            if controls_assessed > 0

            else "Not applicable — no controls assessed"

        )

    return {

        "cmmc_level": cmmc_level,
        "total_controls": total_controls,
        "controls_assessed": controls_assessed,
        "compliant_count": compliant_count,
        "percentage": percentage,
        "rating_label": rating_label,
        "highest_open_priority": highest_open_priority,
        "projected_remediation_timeframe": projected_remediation_timeframe,
        "aggregated_findings": aggregated_findings,
        "open_findings_count": len(risk_findings)

    }


# ============================================================
# COST SAVINGS / COST AVOIDANCE CALCULATIONS
# ============================================================
#
# These are ESTIMATES built entirely from user-supplied
# assumptions (rates, hours, contract value). The tool has no
# way to know a real consultant's rate or a real contract's
# legal exposure — the numbers below are only as good as the
# inputs the assessor provides, and should be reviewed by the
# assessor/legal counsel before being relied on. None of this
# constitutes financial or legal advice.
#
# ============================================================

def compute_consultant_savings(
    num_controls_assessed,
    consultant_hourly_rate,
    consultant_hours_per_control,
    tool_cost
):

    estimated_consultant_cost = (
        num_controls_assessed
        * consultant_hourly_rate
        * consultant_hours_per_control
    )

    net_savings = estimated_consultant_cost - tool_cost

    return {

        "estimated_consultant_cost": estimated_consultant_cost,
        "tool_cost": tool_cost,
        "net_savings": net_savings

    }


RISK_EXPOSURE_WEIGHT = {

    "Critical": 1.00,
    "High": 0.60,
    "Medium": 0.30,
    "Low": 0.10

}


def compute_risk_exposure_avoided(
    annual_contract_value,
    risk_findings
):

    if not risk_findings or annual_contract_value <= 0:

        return {

            "weighted_exposure_percentage": 0,
            "estimated_exposure_avoided": 0

        }

    # Use the single highest-priority open finding's weight as
    # the exposure baseline, since one severe unresolved finding
    # can be enough to jeopardize certification or a contract on
    # its own — this avoids double-counting risk across many
    # related findings.

    top_weight = max(

        RISK_EXPOSURE_WEIGHT.get(finding["priority_label"], 0.10)

        for finding in risk_findings

    )

    estimated_exposure_avoided = annual_contract_value * top_weight

    return {

        "weighted_exposure_percentage": top_weight * 100,
        "estimated_exposure_avoided": estimated_exposure_avoided

    }


# ============================================================
# CHART: STATUS DISTRIBUTION (BAR + PIE)
# ============================================================

def build_status_chart_image(counts):

    labels = [
        "Compliant",
        "Partially\nCompliant",
        "Non-\nCompliant",
        "Insufficient\nEvidence"
    ]

    values = [
        counts[status]
        for status in STATUS_ORDER
    ]

    bar_colors = [
        STATUS_HEX[status]
        for status in STATUS_ORDER
    ]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(7.5, 3)
    )

    axes[0].bar(
        labels,
        values,
        color=bar_colors
    )

    axes[0].set_title(
        "Findings by Status",
        fontsize=11
    )

    axes[0].set_ylabel("Count")

    axes[0].tick_params(
        axis="x",
        labelsize=8
    )

    for index, value in enumerate(values):

        axes[0].text(
            index,
            value + 0.05,
            str(value),
            ha="center",
            fontsize=9
        )

    total = sum(values)

    if total > 0:

        nonzero_labels = [
            label
            for label, value in zip(labels, values)
            if value > 0
        ]

        nonzero_values = [
            value
            for value in values
            if value > 0
        ]

        nonzero_colors = [
            color
            for color, value in zip(bar_colors, values)
            if value > 0
        ]

        axes[1].pie(
            nonzero_values,
            labels=nonzero_labels,
            colors=nonzero_colors,
            autopct="%1.0f%%",
            textprops={"fontsize": 8}
        )

        axes[1].set_title(
            "Status Distribution",
            fontsize=11
        )

    else:

        axes[1].axis("off")

    fig.tight_layout()

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=150
    )

    plt.close(fig)

    buffer.seek(0)

    return buffer


# ============================================================
# CHART: FINDINGS BY CONTROL FAMILY (STACKED BAR)
# ============================================================

def build_family_chart_image(
    all_findings,
    cmmc_level
):

    family_counts = {}

    for finding in all_findings:

        family = get_family_for_control(
            cmmc_level,
            finding.get("control_id", "")
        )

        status = finding.get(
            "status",
            "INSUFFICIENT EVIDENCE"
        )

        if family not in family_counts:

            family_counts[family] = {
                status_key: 0
                for status_key in STATUS_ORDER
            }

        if status not in family_counts[family]:

            status = "INSUFFICIENT EVIDENCE"

        family_counts[family][status] += 1

    families = list(family_counts.keys())

    if not families:

        return None

    fig, ax = plt.subplots(
        figsize=(7.5, max(2.5, 0.5 * len(families) + 1))
    )

    bottoms = [0] * len(families)

    for status in STATUS_ORDER:

        values = [
            family_counts[family][status]
            for family in families
        ]

        ax.barh(
            families,
            values,
            left=bottoms,
            color=STATUS_HEX[status],
            label=status.title()
        )

        bottoms = [
            bottom + value
            for bottom, value in zip(bottoms, values)
        ]

    ax.set_xlabel(
        "Number of Findings",
        fontsize=9,
        labelpad=8
    )

    ax.set_title(
        "Findings by Control Family",
        fontsize=11,
        pad=12
    )

    ax.tick_params(
        axis="y",
        labelsize=7
    )

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=4,
        fontsize=7,
        frameon=False
    )

    fig.subplots_adjust(
        bottom=0.32,
        top=0.88,
        left=0.4,
        right=0.95
    )

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=150
    )

    plt.close(fig)

    buffer.seek(0)

    return buffer


# ============================================================
# DISPLAY RESULTS
# ============================================================

if "assessment_results" in st.session_state:

    results = st.session_state[
        "assessment_results"
    ]


    st.divider()

    st.header(
        "📊 Assessment Results"
    )


    total_elapsed_seconds = st.session_state.get(
        "assessment_total_elapsed_seconds"
    )

    if total_elapsed_seconds is not None:

        st.caption(

            f"⏱️ Total processing time: "
            f"{format_elapsed(total_elapsed_seconds)}"

        )


    if len(results) > 1 and any(

        "elapsed_seconds" in file_result

        for file_result in results

    ):

        with st.expander("⏱️ Time elapsed per file"):

            for file_result in results:

                file_elapsed = file_result.get(
                    "elapsed_seconds"
                )

                if file_elapsed is not None:

                    st.write(

                        f"📄 {file_result['filename']}: "
                        f"{format_elapsed(file_elapsed)}"

                    )


    # ========================================================
    # BUILD FINDING LIST
    # ========================================================

    all_findings = []


    for file_result in results:

        for finding in file_result[
            "results"
        ]:

            finding_copy = finding.copy()

            finding_copy[
                "filename"
            ] = file_result[
                "filename"
            ]

            all_findings.append(
                finding_copy
            )


    # ========================================================
    # METRICS
    # ========================================================

    compliant = sum(

        1

        for finding in all_findings

        if finding["status"]
        == "COMPLIANT"

    )


    partial = sum(

        1

        for finding in all_findings

        if finding["status"]
        == "PARTIALLY COMPLIANT"

    )


    non_compliant = sum(

        1

        for finding in all_findings

        if finding["status"]
        == "NON-COMPLIANT"

    )


    insufficient = sum(

        1

        for finding in all_findings

        if finding["status"]
        == "INSUFFICIENT EVIDENCE"

    )


    col1, col2, col3, col4 = st.columns(4)


    col1.metric(
        "✅ Compliant",
        compliant
    )


    col2.metric(
        "⚠️ Partial",
        partial
    )


    col3.metric(
        "❌ Non-Compliant",
        non_compliant
    )


    col4.metric(
        "❓ Insufficient Evidence",
        insufficient
    )


    # ========================================================
    # OVERALL COMPLIANCE RATING
    # ========================================================

    st.divider()

    st.subheader(
        "🏁 Overall Compliance Rating"
    )

    overall_assessment = compute_overall_level_assessment(
        all_findings,
        st.session_state.get("assessment_level")
    )

    rating_col1, rating_col2, rating_col3, rating_col4 = st.columns(4)

    rating_col1.metric(
        "Controls Compliant",
        f"{overall_assessment['compliant_count']}/"
        f"{overall_assessment['total_controls']}"
    )

    rating_col2.metric(
        "Compliance Percentage",
        f"{overall_assessment['percentage']:.0f}%"
    )

    rating_col3.metric(
        "Overall Rating",
        overall_assessment["rating_label"]
    )

    rating_col4.metric(
        "Projected Remediation Timeframe",
        overall_assessment["projected_remediation_timeframe"]
    )

    if overall_assessment["rating_label"] == "Compliant":

        st.success(

            f"{overall_assessment['cmmc_level']}: "
            f"{overall_assessment['compliant_count']}/"
            f"{overall_assessment['total_controls']} controls compliant "
            f"({overall_assessment['percentage']:.0f}%) — Compliant."

        )

    else:

        st.warning(

            f"{overall_assessment['cmmc_level']}: "
            f"{overall_assessment['compliant_count']}/"
            f"{overall_assessment['total_controls']} controls compliant "
            f"({overall_assessment['percentage']:.0f}%) — Not Compliant. "
            f"Projected remediation timeframe: "
            f"{overall_assessment['projected_remediation_timeframe']}."

        )

    st.caption(

        "A level is rated \"Compliant\" only when 100% of its controls "
        "are found compliant. This score and timeframe are internal "
        "tool metrics to aid prioritization, and are distinct from the "
        "official DoD/SPRS scoring methodology used in a certified "
        "CMMC assessment."

    )


    # ========================================================
    # FINDING FILTER
    # ========================================================

    st.subheader(
        "Filter Findings"
    )


    status_filter = st.multiselect(

        "Show statuses",

        [
            "COMPLIANT",
            "PARTIALLY COMPLIANT",
            "NON-COMPLIANT",
            "INSUFFICIENT EVIDENCE"
        ],

        default=[
            "COMPLIANT",
            "PARTIALLY COMPLIANT",
            "NON-COMPLIANT",
            "INSUFFICIENT EVIDENCE"
        ]

    )


    filtered_findings = [

        finding

        for finding in all_findings

        if finding["status"]
        in status_filter

    ]

# ========================================================
# PUSH OPEN FINDINGS TO BLUF + POA&M PAGES
# ========================================================
st.divider()
st.subheader("Export Open Findings")

# Collect Non-Compliant + Partially Compliant findings
open_findings = [
    f for f in all_findings
    if str(f.get("status", "")).upper() in [
        "NON-COMPLIANT",
        "PARTIALLY COMPLIANT",
    ]
]

if open_findings:
    st.info(
        f"**{len(open_findings)} open finding(s)** "
        f"(Non-Compliant + Partially Compliant) are ready to send "
        f"to the BLUF and POA&M pages."
    )
else:
    st.success("No Non-Compliant or Partially Compliant findings to push.")

# ---- Shared keys (used by both pages) ----
st.session_state["assessment_open_findings"] = open_findings
st.session_state["assessment_cmmc_level"] = st.session_state.get("assessment_level")
st.session_state["assessment_framework"] = st.session_state.get("assessment_framework")

# ---- BLUF keys (backward compatible) ----
st.session_state["bluf_open_findings"] = open_findings
st.session_state["bluf_cmmc_level"] = st.session_state.get("assessment_level")
st.session_state["bluf_framework"] = st.session_state.get("assessment_framework")

# ---- POA&M keys (explicit) ----
st.session_state["poam_open_findings"] = open_findings
st.session_state["poam_cmmc_level"] = st.session_state.get("assessment_level")
st.session_state["poam_framework"] = st.session_state.get("assessment_framework")

col_bluf, col_poam = st.columns(2)

with col_bluf:
    if st.button(
        "⚠️  Go to BLUF – Model Consequences",
        type="primary",
        width="stretch",
        key="goto_bluf_from_assessment",
    ):
        st.switch_page("pages/03_BLUF.py")

with col_poam:
    if st.button(
        "📋  Go to POA&M – Build Remediation Plan",
        type="primary",
        width="stretch",
        key="goto_poam_from_assessment",
    ):
        st.switch_page("pages/04_POAM.py")
        
    # ========================================================
    # FINDINGS
    # ========================================================

    st.subheader(
        "Detailed Findings"
    )


    for finding in filtered_findings:

        status = finding[
            "status"
        ]


        if status == "COMPLIANT":

            icon = "✅"

        elif status == "PARTIALLY COMPLIANT":

            icon = "⚠️"

        elif status == "NON-COMPLIANT":

            icon = "❌"

        else:

            icon = "❓"


        with st.expander(

            f"{icon} "
            f"{finding['control_id']} — "
            f"{status} — "
            f"{finding['filename']}"

        ):

            st.write(
                f"**Severity:** "
                f"{finding['severity']}"
            )


            st.write(
                f"**AI Confidence:** "
                f"{finding['confidence']}%"
            )


            st.markdown(
                "### Evidence Summary"
            )


            st.write(
                finding[
                    "evidence_summary"
                ]
            )


            st.markdown(
                "### Supporting Evidence"
            )


            evidence_list = finding.get(
                "supporting_evidence",
                []
            )


            if evidence_list:

                for evidence in evidence_list:

                    st.write(
                        f"• {evidence}"
                    )

            else:

                st.write(
                    "No supporting evidence identified."
                )


            st.markdown(
                "### Missing Evidence"
            )


            missing = finding.get(
                "missing_evidence",
                []
            )


            if missing:

                for evidence in missing:

                    st.write(
                        f"• {evidence}"
                    )

            else:

                st.write(
                    "No missing evidence identified."
                )


            st.markdown(
                "### Assessment Reasoning"
            )


            st.write(
                finding[
                    "assessment_reasoning"
                ]
            )


            st.markdown(
                "### Recommended Remediation"
            )


            st.info(
                finding[
                    "remediation"
                ]
            )


            st.markdown(
                "### Recommended Assessor Action"
            )


            st.warning(
                finding[
                    "recommended_assessor_action"
                ]
            )


    # ========================================================
    # RISK MANAGEMENT MATRIX
    # ========================================================

    st.divider()

    st.header(
        "🎯 Risk Management Matrix"
    )

    st.caption(
        "Open findings (non-compliant, partially compliant, or "
        "insufficient evidence) plotted by likelihood and impact "
        "to help prioritize remediation. Likelihood is derived "
        "from compliance status; impact is derived from the "
        "AI-assigned severity for each finding."
    )

    risk_findings = compute_risk_findings(all_findings)

    if risk_findings:

        risk_chart = build_risk_matrix_chart_image(risk_findings)

        if risk_chart:

            st.image(risk_chart, use_container_width=True)

        st.markdown("### Findings by Priority")

        risk_table_rows = [

            {
                "Priority": finding["priority_label"],
                "Control ID": finding.get("control_id", ""),
                "Status": finding.get("status", ""),
                "Severity": finding.get("severity", ""),
                "File": finding.get("filename", ""),
                "Recommended Timeframe":
                    risk_recommended_timeframe(finding["priority_label"])
            }

            for finding in risk_findings

        ]

        st.dataframe(
            pd.DataFrame(risk_table_rows),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.success(
            "No open findings — nothing to prioritize."
        )


    # ========================================================
    # COST SAVINGS: TOOL VS. CONSULTANT
    # ========================================================

    st.divider()

    st.header(
        "💰 Cost Savings vs. Hiring a Consultant"
    )

    st.caption(
        "These figures are ESTIMATES based on the assumptions "
        "below — adjust them to reflect your organization's "
        "actual market rates. This is not a guarantee of savings "
        "and is not financial advice."
    )

    num_controls_assessed = len(all_findings)

    cost_col1, cost_col2, cost_col3 = st.columns(3)

    with cost_col1:

        consultant_hourly_rate = st.number_input(
            "Assumed consultant hourly rate ($)",
            min_value=0,
            value=250,
            step=25,
            key="consultant_hourly_rate"
        )

    with cost_col2:

        consultant_hours_per_control = st.number_input(
            "Assumed consultant hours per control",
            min_value=0.0,
            value=1.5,
            step=0.25,
            key="consultant_hours_per_control"
        )

    with cost_col3:

        tool_cost = st.number_input(
            "Your actual cost to run this assessment ($)",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key="tool_cost",
            help="API usage cost, staff time, subscription cost, etc."
        )

    savings = compute_consultant_savings(
        num_controls_assessed=num_controls_assessed,
        consultant_hourly_rate=consultant_hourly_rate,
        consultant_hours_per_control=consultant_hours_per_control,
        tool_cost=tool_cost
    )

    savings_col1, savings_col2, savings_col3 = st.columns(3)

    savings_col1.metric(
        "Est. Consultant Cost",
        f"${savings['estimated_consultant_cost']:,.0f}"
    )

    savings_col2.metric(
        "Your Tool Cost",
        f"${savings['tool_cost']:,.0f}"
    )

    savings_col3.metric(
        "Estimated Net Savings",
        f"${savings['net_savings']:,.0f}"
    )


    # ========================================================
    # ESTIMATED RISK EXPOSURE AVOIDED
    # ========================================================

    st.divider()

    st.header(
        "🛡️ Estimated Risk Exposure Avoided"
    )

    st.caption(
        "Identifying compliance gaps before an official "
        "assessment can help avoid failed certifications, "
        "contract losses, or legal exposure. The figure below "
        "is a rough, user-configured ESTIMATE, not a legal or "
        "financial determination — consult your legal and "
        "compliance counsel for an authoritative assessment "
        "of your exposure."
    )

    annual_contract_value = st.number_input(
        "Annual contract value dependent on CMMC compliance ($)",
        min_value=0,
        value=0,
        step=10000,
        key="annual_contract_value",
        help=(
            "The value of DoD/prime contracts that require this "
            "level of CMMC compliance to maintain."
        )
    )

    exposure = compute_risk_exposure_avoided(
        annual_contract_value=annual_contract_value,
        risk_findings=risk_findings
    )

    if risk_findings and annual_contract_value > 0:

        exp_col1, exp_col2 = st.columns(2)

        exp_col1.metric(
            "Highest Priority Finding Weight",
            f"{exposure['weighted_exposure_percentage']:.0f}%"
        )

        exp_col2.metric(
            "Estimated Exposure Identified & Avoidable",
            f"${exposure['estimated_exposure_avoided']:,.0f}"
        )

        st.caption(
            "Calculated as: contract value × the risk weight of "
            "your single highest-priority open finding. This is "
            "a simplified heuristic intended to communicate "
            "relative urgency, not a precise dollar figure."
        )

    else:

        st.info(
            "Enter an annual contract value above to see an "
            "estimated exposure figure, once open findings exist."
        )


    # ========================================================
    # LOG TO CUSTOMER IMPACT DASHBOARD
    # ========================================================
    #
    # Placed here (inside the results block, after savings and
    # exposure are computed) so all_findings/savings/exposure are
    # guaranteed to exist. This is a manual action rather than an
    # automatic one, since number_input widgets above rerun this
    # whole script on every change — auto-logging here would create
    # a duplicate history entry every time an assessor tweaks an
    # assumption. The button lets them finalize inputs once, then
    # log the final numbers.
    #
    # ========================================================

    st.divider()

    st.subheader(
        "📈 Customer Impact Dashboard"
    )

    st.caption(
        "Log this assessment's findings, savings, and exposure "
        "estimates to the Customer Impact Dashboard so they're "
        "reflected in the aggregate trends and totals shown there."
    )

    if st.button(
        "💾 Log This Assessment to Customer Impact Dashboard",
        use_container_width=True
    ):

        log_assessment_run(
            company_name=st.session_state.company_info["company_name"],
            representative=st.session_state.company_info["representative"],
            cmmc_level=st.session_state.get("assessment_level"),
            framework_version=st.session_state.get("assessment_framework"),
            all_findings=all_findings,
            savings=savings,
            exposure=exposure
        )

        st.session_state["logged_to_dashboard"] = True

        st.success(
            "Logged! View it on the Customer Impact Dashboard page."
        )

    elif st.session_state.get("logged_to_dashboard"):

        st.caption(
            "✅ This assessment has already been logged to the "
            "dashboard. Click the button again if you've since "
            "adjusted the cost or exposure assumptions above and "
            "want to log the updated figures."
        )


# ============================================================
# PDF EXPORT — SHARED HELPERS
# ============================================================

def build_pdf_styles():

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="FindingHeading",
            parent=styles["Heading3"],
            spaceBefore=14,
            spaceAfter=4
        )
    )

    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            spaceAfter=6,
            leading=14
        )
    )

    styles.add(
        ParagraphStyle(
            name="Disclaimer",
            parent=styles["Normal"],
            spaceAfter=8,
            leading=12,
            fontSize=8,
            textColor=colors.HexColor("#57606a")
        )
    )

    styles.add(
        ParagraphStyle(
            name="ExecBody",
            parent=styles["Normal"],
            spaceAfter=10,
            leading=16,
            fontSize=11
        )
    )

    styles.add(
        ParagraphStyle(
            name="VisualCaption",
            parent=styles["Normal"],
            spaceAfter=6,
            leading=14,
            fontSize=10,
            alignment=1  # centered
        )
    )

    styles.add(
        ParagraphStyle(
            name="MethodBullet",
            parent=styles["Normal"],
            spaceAfter=4,
            leading=13,
            leftIndent=14
        )
    )

    return styles


def flatten_findings(all_results):

    all_findings = []

    for file_result in all_results:

        for finding in file_result["results"]:

            finding_copy = finding.copy()

            finding_copy["filename"] = file_result["filename"]

            all_findings.append(finding_copy)

    return all_findings


def compute_status_counts(all_findings):

    counts = {

        "COMPLIANT": 0,
        "PARTIALLY COMPLIANT": 0,
        "NON-COMPLIANT": 0,
        "INSUFFICIENT EVIDENCE": 0

    }

    for finding in all_findings:

        status = finding.get(
            "status",
            "INSUFFICIENT EVIDENCE"
        )

        if status in counts:

            counts[status] += 1

    return counts


def build_pdf_title_block(
    story,
    styles,
    title_text,
    subtitle_text,
    assessment_level,
    framework_version
):

    story.append(
        Paragraph(title_text, styles["Title"])
    )

    if subtitle_text:

        story.append(
            Paragraph(subtitle_text, styles["Heading3"])
        )

    story.append(Spacer(1, 12))

    if assessment_level:

        story.append(
            Paragraph(
                f"<b>CMMC Level:</b> {assessment_level}",
                styles["Body"]
            )
        )

    if framework_version:

        story.append(
            Paragraph(
                f"<b>Framework:</b> {framework_version}",
                styles["Body"]
            )
        )

    story.append(Spacer(1, 20))


def build_summary_table(counts):

    summary_table_data = [
        ["Status", "Count"],
        ["Compliant", str(counts["COMPLIANT"])],
        ["Partially Compliant", str(counts["PARTIALLY COMPLIANT"])],
        ["Non-Compliant", str(counts["NON-COMPLIANT"])],
        ["Insufficient Evidence", str(counts["INSUFFICIENT EVIDENCE"])]
    ]

    summary_table = Table(
        summary_table_data,
        colWidths=[3 * inch, 1.5 * inch]
    )

    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6)
        ])
    )

    return summary_table


def build_risk_matrix_pdf_section(
    story,
    styles,
    risk_findings,
    include_severity_column=True
):

    story.append(
        Paragraph("Risk Management Matrix", styles["Heading2"])
    )

    story.append(
        Paragraph(
            "Open findings prioritized by likelihood (derived "
            "from compliance status) and impact (derived from "
            "AI-assigned severity). This is a triage heuristic, "
            "not a certified risk-scoring methodology.",
            styles["Disclaimer"]
        )
    )

    if not risk_findings:

        story.append(
            Paragraph(
                "No open findings to prioritize.",
                styles["Body"]
            )
        )

        return

    risk_chart = build_risk_matrix_chart_image(risk_findings)

    if risk_chart:

        story.append(Spacer(1, 8))

        story.append(
            Image(
                risk_chart,
                width=6.5 * inch,
                height=6.5 * inch * (5 / 7.5)
            )
        )

    story.append(Spacer(1, 12))

    if include_severity_column:

        risk_table_data = [
            ["Priority", "Control ID", "Status", "File", "Timeframe"]
        ]

        for finding in risk_findings:

            risk_table_data.append([
                finding["priority_label"],
                finding.get("control_id", ""),
                finding.get("status", ""),
                finding.get("filename", ""),
                risk_recommended_timeframe(finding["priority_label"])
            ])

        col_widths = [0.9 * inch, 1.3 * inch, 1.6 * inch, 1.6 * inch, 1.1 * inch]

    else:

        risk_table_data = [
            ["Priority", "Reference ID", "Status", "Timeframe"]
        ]

        for finding in risk_findings:

            risk_table_data.append([
                finding["priority_label"],
                finding.get("control_id", ""),
                STATUS_PLAIN_LANGUAGE.get(
                    finding.get("status", ""),
                    finding.get("status", "")
                ),
                risk_recommended_timeframe(finding["priority_label"])
            ])

        col_widths = [1.1 * inch, 1.5 * inch, 2.2 * inch, 1.2 * inch]

    risk_table = Table(
        risk_table_data,
        colWidths=col_widths
    )

    risk_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5)
        ])
    )

    story.append(risk_table)


def build_overall_rating_pdf_section(
    story,
    styles,
    overall_assessment,
    plain_language=False
):
    """
    Renders the Overall Compliance Rating & Projected Remediation
    Timeframe block used across the technical, executive, and
    visual PDF exports.
    """

    story.append(
        Paragraph("Overall Compliance Rating", styles["Heading2"])
    )

    rating_color = (

        colors.HexColor("#1a7f37")

        if overall_assessment["rating_label"] == "Compliant"

        else colors.HexColor("#cf222e")

    )

    story.append(
        Paragraph(
            f"<b>{overall_assessment['cmmc_level']} Score:</b> "
            f"{overall_assessment['compliant_count']}/"
            f"{overall_assessment['total_controls']} controls compliant "
            f"(<font color='{rating_color.hexval()}'><b>"
            f"{overall_assessment['percentage']:.0f}% — "
            f"{overall_assessment['rating_label']}</b></font>)",
            styles["ExecBody"] if plain_language else styles["Body"]
        )
    )

    story.append(
        Paragraph(
            f"<b>Projected Remediation Timeframe:</b> "
            f"{overall_assessment['projected_remediation_timeframe']}",
            styles["ExecBody"] if plain_language else styles["Body"]
        )
    )

    story.append(
        Paragraph(
            "A level is rated \"Compliant\" only when 100% of its "
            "controls are found compliant; any control short of fully "
            "compliant yields a \"Not Compliant\" rating. The projected "
            "remediation timeframe reflects the recommended timeframe "
            "for the single highest-priority open finding at this "
            "level (see the Risk Management Matrix). This is an "
            "internal tool metric intended to aid prioritization, and "
            "is distinct from the official DoD/SPRS scoring "
            "methodology used in a certified CMMC assessment.",
            styles["Disclaimer"]
        )
    )

    story.append(Spacer(1, 12))


STATUS_PLAIN_LANGUAGE = {

    "COMPLIANT":
        "Requirement Met",

    "PARTIALLY COMPLIANT":
        "Partially Met — Needs Attention",

    "NON-COMPLIANT":
        "Requirement Not Met",

    "INSUFFICIENT EVIDENCE":
        "Needs More Evidence"

}


# ============================================================
# PDF PASSWORD PROTECTION
# ============================================================
#
# These reports can contain proprietary log evidence, company
# names, and findings — if the assessor sets a password, all
# four exports below require it to open. The same password is
# used as both user and owner password (these reports are meant
# to be opened only by people who already have the password
# shared with them, not partially restricted for a "logged in"
# viewer), and printing is allowed while copying/editing/
# annotating are blocked by default so the content can't be
# easily lifted out of a password-protected file once opened.
#
# ============================================================

def build_pdf_encryption(password):
    """
    Returns a reportlab StandardEncryption object if a password
    was supplied, else None (no encryption — the historical,
    unprotected behavior). Pass the result as the `encrypt=`
    argument to SimpleDocTemplate.
    """

    if not password:

        return None

    return StandardEncryption(
        userPassword=password,
        ownerPassword=password,
        canPrint=1,
        canModify=0,
        canCopy=0,
        canAnnotate=0
    )


# ============================================================
# EXPORT 1: TECHNICAL FINDINGS REPORT
# ============================================================
#
# Audience: cybersecurity / compliance professionals who will
# use this to actually remediate findings. Includes full
# per-control technical detail: requirement text, assessment
# objectives, evidence reviewed, AI reasoning, and remediation
# guidance.
#
# ============================================================

def build_technical_pdf_report(
    assessment_level,
    framework_version,
    all_results,
    pdf_password=None
):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        encrypt=build_pdf_encryption(pdf_password)
    )

    styles = build_pdf_styles()

    status_colors = {

        status: colors.HexColor(hex_value)

        for status, hex_value in STATUS_HEX.items()

    }

    story = []

    build_pdf_title_block(
        story,
        styles,
        "GetRight CMMC Assessment",
        "Technical Findings Report",
        assessment_level,
        framework_version
    )

    all_findings = flatten_findings(all_results)

    counts = compute_status_counts(all_findings)

    story.append(
        Paragraph("Summary", styles["Heading2"])
    )

    story.append(
        build_summary_table(counts)
    )

    story.append(Spacer(1, 16))

    overall_assessment = compute_overall_level_assessment(
        all_findings,
        assessment_level
    )

    build_overall_rating_pdf_section(
        story,
        styles,
        overall_assessment
    )

    status_chart = build_status_chart_image(counts)

    story.append(
        Image(
            status_chart,
            width=6.5 * inch,
            height=6.5 * inch * (3 / 7.5)
        )
    )

    family_chart = build_family_chart_image(
        all_findings,
        assessment_level
    )

    if family_chart:

        story.append(Spacer(1, 16))

        family_count = len(
            set(

                get_family_for_control(
                    assessment_level,
                    finding.get("control_id", "")
                )

                for finding in all_findings

            )

        )

        chart_height = (
            6.5 * inch
            * (max(2.5, 0.5 * family_count + 1) / 7.5)
        )

        story.append(
            Image(
                family_chart,
                width=6.5 * inch,
                height=chart_height
            )
        )

    story.append(PageBreak())


    # --------------------------------------------------------
    # DETAILED TECHNICAL FINDINGS
    # --------------------------------------------------------

    story.append(
        Paragraph("Detailed Technical Findings", styles["Heading2"])
    )

    for finding in all_findings:

        status = finding.get(
            "status",
            "INSUFFICIENT EVIDENCE"
        )

        color = status_colors.get(status, colors.black)

        control_def = get_control_definition(
            assessment_level,
            finding.get("control_id", "")
        )

        story.append(
            Paragraph(
                f"{finding.get('control_id', '')} "
                f"&mdash; "
                f"<font color='{color.hexval()}'>{status}</font> "
                f"&mdash; {finding.get('filename', '')}",
                styles["FindingHeading"]
            )
        )

        if control_def:

            story.append(
                Paragraph(
                    f"<b>Control Family:</b> {control_def.get('family', '')}",
                    styles["Body"]
                )
            )

            story.append(
                Paragraph(
                    f"<b>Requirement:</b> {control_def.get('requirement', '')}",
                    styles["Body"]
                )
            )

            objectives = control_def.get("assessment_objectives", [])

            if objectives:

                story.append(
                    Paragraph(
                        "<b>Assessment Objectives:</b> "
                        + "; ".join(objectives),
                        styles["Body"]
                    )
                )

            evidence_types = control_def.get("evidence_types", [])

            if evidence_types:

                story.append(
                    Paragraph(
                        "<b>Expected Evidence Types:</b> "
                        + "; ".join(evidence_types),
                        styles["Body"]
                    )
                )

        story.append(
            Paragraph(
                f"<b>Severity:</b> {finding.get('severity', '')} "
                f"&nbsp;&nbsp; "
                f"<b>AI Confidence:</b> {finding.get('confidence', 0)}%",
                styles["Body"]
            )
        )

        story.append(
            Paragraph(
                f"<b>Evidence Summary:</b> "
                f"{finding.get('evidence_summary', '')}",
                styles["Body"]
            )
        )

        supporting = finding.get("supporting_evidence", [])

        supporting_clean = [str(item) for item in supporting if item]

        if supporting_clean:

            story.append(
                Paragraph(
                    "<b>Supporting Evidence:</b> "
                    + "; ".join(supporting_clean),
                    styles["Body"]
                )
            )

        missing = finding.get("missing_evidence", [])

        missing_clean = [str(item) for item in missing if item]

        if missing_clean:

            story.append(
                Paragraph(
                    "<b>Missing Evidence:</b> "
                    + "; ".join(missing_clean),
                    styles["Body"]
                )
            )

        story.append(
            Paragraph(
                f"<b>Assessment Reasoning:</b> "
                f"{finding.get('assessment_reasoning', '')}",
                styles["Body"]
            )
        )

        story.append(
            Paragraph(
                f"<b>Recommended Remediation:</b> "
                f"{finding.get('remediation', '')}",
                styles["Body"]
            )
        )

        story.append(
            Paragraph(
                f"<b>Recommended Assessor Action:</b> "
                f"{finding.get('recommended_assessor_action', '')}",
                styles["Body"]
            )
        )

        story.append(Spacer(1, 6))


    # --------------------------------------------------------
    # RISK MANAGEMENT MATRIX
    # --------------------------------------------------------

    risk_findings = compute_risk_findings(all_findings)

    story.append(PageBreak())

    build_risk_matrix_pdf_section(
        story,
        styles,
        risk_findings,
        include_severity_column=True
    )

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# EXPORT 2: EXECUTIVE / STAKEHOLDER SUMMARY
# ============================================================
#
# Audience: non-technical stakeholders (leadership, contracts,
# legal). Plain-language framing, no raw log evidence or AI
# reasoning text, no control-specific technical jargon beyond a
# reference ID. Includes the cost-savings and risk-exposure
# estimates, both clearly labeled as user-configured estimates.
#
# ============================================================

def build_executive_pdf_report(
    assessment_level,
    framework_version,
    all_results,
    consultant_hourly_rate=250,
    consultant_hours_per_control=1.5,
    tool_cost=0.0,
    annual_contract_value=0,
    pdf_password=None
):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        encrypt=build_pdf_encryption(pdf_password)
    )

    styles = build_pdf_styles()

    story = []

    build_pdf_title_block(
        story,
        styles,
        "GetRight CMMC Assessment",
        "Executive Summary",
        assessment_level,
        framework_version
    )

    story.append(
        Paragraph(
            "This report summarizes the results of an AI-assisted "
            "review of cybersecurity evidence against CMMC "
            "requirements. It is intended to give leadership a "
            "plain-language view of where the organization stands "
            "and what needs attention before an official "
            "assessment. It is not itself a certification and does "
            "not replace review by a qualified assessor.",
            styles["ExecBody"]
        )
    )

    all_findings = flatten_findings(all_results)

    counts = compute_status_counts(all_findings)

    total_reviewed = len(all_findings)

    open_issues = (
        counts["NON-COMPLIANT"]
        + counts["PARTIALLY COMPLIANT"]
        + counts["INSUFFICIENT EVIDENCE"]
    )

    if total_reviewed == 0:

        posture_sentence = "No requirements were reviewed."

    elif open_issues == 0:

        posture_sentence = (
            f"All {total_reviewed} requirements reviewed currently "
            "appear to be met based on the evidence provided."
        )

    else:

        posture_sentence = (
            f"Of {total_reviewed} requirements reviewed, "
            f"{counts['COMPLIANT']} currently appear to be met and "
            f"{open_issues} need attention before an official "
            "assessment — see the priorities below."
        )

    story.append(
        Paragraph(
            f"<b>Overall Compliance Posture:</b> {posture_sentence}",
            styles["ExecBody"]
        )
    )

    story.append(Spacer(1, 10))

    overall_assessment = compute_overall_level_assessment(
        all_findings,
        assessment_level
    )

    build_overall_rating_pdf_section(
        story,
        styles,
        overall_assessment,
        plain_language=True
    )

    story.append(
        build_summary_table(counts)
    )

    story.append(Spacer(1, 16))

    status_chart = build_status_chart_image(counts)

    story.append(
        Image(
            status_chart,
            width=6.5 * inch,
            height=6.5 * inch * (3 / 7.5)
        )
    )

    story.append(PageBreak())


    # --------------------------------------------------------
    # TOP PRIORITIES, IN PLAIN LANGUAGE
    # --------------------------------------------------------

    risk_findings = compute_risk_findings(all_findings)

    story.append(
        Paragraph("Top Priorities", styles["Heading2"])
    )

    story.append(
        Paragraph(
            "Issues below are ordered by urgency, based on how "
            "likely each is to represent a real gap and how "
            "significant the impact would be if left unaddressed.",
            styles["Disclaimer"]
        )
    )

    if risk_findings:

        top_findings = risk_findings[:10]

        priority_table_data = [
            ["Priority", "Reference ID", "Status", "Timeframe"]
        ]

        for finding in top_findings:

            priority_table_data.append([
                finding["priority_label"],
                finding.get("control_id", ""),
                STATUS_PLAIN_LANGUAGE.get(
                    finding.get("status", ""),
                    finding.get("status", "")
                ),
                risk_recommended_timeframe(finding["priority_label"])
            ])

        priority_table = Table(
            priority_table_data,
            colWidths=[1.1 * inch, 1.5 * inch, 2.6 * inch, 1.3 * inch]
        )

        priority_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6)
            ])
        )

        story.append(Spacer(1, 8))

        story.append(priority_table)

        if len(risk_findings) > len(top_findings):

            story.append(
                Paragraph(
                    f"...and {len(risk_findings) - len(top_findings)} "
                    "additional lower-priority items — see the "
                    "Technical Findings Report for the complete list.",
                    styles["Disclaimer"]
                )
            )

    else:

        story.append(
            Paragraph(
                "No outstanding issues were identified.",
                styles["Body"]
            )
        )


    # --------------------------------------------------------
    # COST SAVINGS VS. CONSULTANT
    # --------------------------------------------------------

    story.append(Spacer(1, 24))

    story.append(
        Paragraph("Cost Savings vs. Hiring a Consultant", styles["Heading2"])
    )

    story.append(
        Paragraph(
            "Figures below are ESTIMATES based on the assumptions "
            "shown, adjustable by the assessor. They are not a "
            "guarantee of savings and do not constitute financial "
            "advice.",
            styles["Disclaimer"]
        )
    )

    savings = compute_consultant_savings(
        num_controls_assessed=len(all_findings),
        consultant_hourly_rate=consultant_hourly_rate,
        consultant_hours_per_control=consultant_hours_per_control,
        tool_cost=tool_cost
    )

    savings_table_data = [
        ["Assumption / Metric", "Value"],
        ["Requirements assessed", str(len(all_findings))],
        ["Assumed consultant rate", f"${consultant_hourly_rate:,.0f}/hr"],
        ["Assumed hours per requirement", f"{consultant_hours_per_control:g}"],
        ["Estimated consultant cost", f"${savings['estimated_consultant_cost']:,.0f}"],
        ["Actual tool cost", f"${savings['tool_cost']:,.0f}"],
        ["Estimated net savings", f"${savings['net_savings']:,.0f}"]
    ]

    savings_table = Table(
        savings_table_data,
        colWidths=[3.2 * inch, 2 * inch]
    )

    savings_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6)
        ])
    )

    story.append(Spacer(1, 8))

    story.append(savings_table)


    # --------------------------------------------------------
    # ESTIMATED RISK EXPOSURE AVOIDED
    # --------------------------------------------------------

    story.append(Spacer(1, 20))

    story.append(
        Paragraph("Estimated Risk Exposure Avoided", styles["Heading2"])
    )

    story.append(
        Paragraph(
            "This figure estimates the contract or legal exposure "
            "associated with unresolved findings, weighted by "
            "priority. It is a simplified, user-configured "
            "heuristic intended to communicate relative urgency, "
            "not a precise legal or financial determination. "
            "Consult qualified legal and compliance counsel for an "
            "authoritative assessment.",
            styles["Disclaimer"]
        )
    )

    exposure = compute_risk_exposure_avoided(
        annual_contract_value=annual_contract_value,
        risk_findings=risk_findings
    )

    exposure_table_data = [
        ["Assumption / Metric", "Value"],
        ["Annual contract value entered", f"${annual_contract_value:,.0f}"],
        ["Open issues identified", str(len(risk_findings))],
        ["Highest-priority issue weight", f"{exposure['weighted_exposure_percentage']:.0f}%"],
        ["Estimated exposure avoidable", f"${exposure['estimated_exposure_avoided']:,.0f}"]
    ]

    exposure_table = Table(
        exposure_table_data,
        colWidths=[3.2 * inch, 2 * inch]
    )

    exposure_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6)
        ])
    )

    story.append(Spacer(1, 8))

    story.append(exposure_table)

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# EXPORT 3: VISUALS-ONLY REPORT
# ============================================================
#
# Audience: anyone who just wants the charts — for slides, a
# board deck, etc. No findings text, no dollar figures, no
# tables beyond what's inside the chart images themselves.
#
# ============================================================

def build_visuals_pdf_report(
    assessment_level,
    framework_version,
    all_results,
    pdf_password=None
):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        encrypt=build_pdf_encryption(pdf_password)
    )

    styles = build_pdf_styles()

    story = []

    build_pdf_title_block(
        story,
        styles,
        "GetRight CMMC Assessment",
        "Visual Report",
        assessment_level,
        framework_version
    )

    all_findings = flatten_findings(all_results)

    counts = compute_status_counts(all_findings)

    overall_assessment = compute_overall_level_assessment(
        all_findings,
        assessment_level
    )

    rating_color_hex = (

        "#1a7f37"

        if overall_assessment["rating_label"] == "Compliant"

        else "#cf222e"

    )

    story.append(
        Paragraph(
            f"<b>{overall_assessment['compliant_count']}/"
            f"{overall_assessment['total_controls']} Controls Compliant "
            f"&mdash; <font color='{rating_color_hex}'>"
            f"{overall_assessment['percentage']:.0f}% "
            f"({overall_assessment['rating_label']})</font></b>",
            styles["VisualCaption"]
        )
    )

    story.append(
        Paragraph(
            f"Projected Remediation Timeframe: "
            f"{overall_assessment['projected_remediation_timeframe']}",
            styles["VisualCaption"]
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph("Findings by Status", styles["VisualCaption"])
    )

    status_chart = build_status_chart_image(counts)

    story.append(
        Image(
            status_chart,
            width=6.5 * inch,
            height=6.5 * inch * (3 / 7.5)
        )
    )

    story.append(PageBreak())

    family_chart = build_family_chart_image(
        all_findings,
        assessment_level
    )

    if family_chart:

        story.append(
            Paragraph("Findings by Control Family", styles["VisualCaption"])
        )

        family_count = len(
            set(

                get_family_for_control(
                    assessment_level,
                    finding.get("control_id", "")
                )

                for finding in all_findings

            )

        )

        chart_height = (
            6.5 * inch
            * (max(2.5, 0.5 * family_count + 1) / 7.5)
        )

        story.append(
            Image(
                family_chart,
                width=6.5 * inch,
                height=chart_height
            )
        )

        story.append(PageBreak())

    risk_findings = compute_risk_findings(all_findings)

    if risk_findings:

        story.append(
            Paragraph("Risk Management Matrix", styles["VisualCaption"])
        )

        risk_chart = build_risk_matrix_chart_image(risk_findings)

        if risk_chart:

            story.append(
                Image(
                    risk_chart,
                    width=6.5 * inch,
                    height=6.5 * inch * (5 / 7.5)
                )
            )

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# EXPORT 4: METHODOLOGY OVERVIEW
# ============================================================
#
# Audience: anyone who wants to understand HOW the tool arrives
# at its findings — an assessor's QA reviewer, a client's IT
# team, an auditor. Describes the process conceptually. Does
# NOT include source code, prompts, or exact numeric internals.
#
# ============================================================

def build_methodology_pdf_report(
    assessment_level,
    framework_version,
    pdf_password=None
):

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        encrypt=build_pdf_encryption(pdf_password)
    )

    styles = build_pdf_styles()

    story = []

    build_pdf_title_block(
        story,
        styles,
        "GetRight CMMC Assessment",
        "Methodology Overview",
        assessment_level,
        framework_version
    )

    def add_section(heading, paragraphs=None, bullets=None):

        story.append(Paragraph(heading, styles["Heading2"]))

        if paragraphs:

            for paragraph_text in paragraphs:

                story.append(Paragraph(paragraph_text, styles["Body"]))

        if bullets:

            for bullet_text in bullets:

                story.append(
                    Paragraph(f"• {bullet_text}", styles["MethodBullet"])
                )

        story.append(Spacer(1, 10))

    add_section(
        "1. Purpose & Scope",
        paragraphs=[
            "GetRight performs an AI-assisted review of "
            "organizational cybersecurity evidence (logs and "
            "related records) against a defined set of CMMC "
            "requirements, to help an assessor identify likely "
            "compliance gaps before a formal assessment. It is a "
            "preparation and triage aid, not a certification tool "
            "— it does not issue or replace an official CMMC "
            "certification decision."
        ]
    )

    add_section(
        "2. Evidence Intake & Normalization",
        paragraphs=[
            "Uploaded evidence files (CSV, JSON, XML, or plain "
            "text logs) are parsed and, where structured, "
            "normalized into a consistent tabular format — column "
            "names are standardized and values are cleaned so that "
            "evidence from different systems can be compared "
            "against the same requirement on equal footing."
        ]
    )

    add_section(
        "3. Control Framework Basis",
        paragraphs=[
            "Each requirement reviewed is defined by a control ID, "
            "a control family, the requirement text itself, a set "
            "of assessment objectives, and the categories of "
            "evidence expected to demonstrate compliance. The "
            "control set used depends on the CMMC Level selected "
            "for the assessment."
        ]
    )

    add_section(
        "4. Evidence Segmentation (\"Batching\")",
        paragraphs=[
            "Large evidence files are split into smaller batches "
            "before analysis. This keeps each review within the "
            "context and rate limits of the underlying AI service, "
            "and ensures that large files are still reviewed in "
            "full rather than being sampled or truncated."
        ]
    )

    add_section(
        "5. AI-Assisted Evidence Review",
        paragraphs=[
            "For each requirement, the evidence batches relevant "
            "to that requirement are presented to an AI model "
            "alongside the requirement text, its assessment "
            "objectives, and the evidence types expected. The "
            "model is directed to compare the evidence against "
            "the requirement and produce a structured finding — "
            "it does not have access to, and does not consult, "
            "any information beyond what is provided in that "
            "review."
        ],
        bullets=[
            "Findings are limited to a fixed set of defined "
            "statuses (e.g. compliant, partially compliant, "
            "non-compliant, insufficient evidence) and a defined "
            "severity scale, so results are consistent and "
            "comparable across requirements.",
            "The model is instructed not to infer compliance "
            "simply from the absence of a problem in the "
            "evidence — absence of contrary evidence is not "
            "treated as proof of compliance.",
            "Requirements that typically depend on policy, "
            "procedure, interviews, or physical controls — not "
            "just logs — are flagged as such, since log evidence "
            "alone may be insufficient to fully assess them.",
            "The model does not make a final certification "
            "determination; its output is a draft finding for "
            "human assessor review."
        ]
    )

    add_section(
        "6. Combining Results Across Evidence Batches",
        paragraphs=[
            "When a requirement is reviewed across multiple "
            "evidence batches, the individual batch results are "
            "combined into a single finding per requirement. The "
            "combined finding takes the most severe status "
            "observed across all batches, merges the supporting "
            "and missing evidence identified in each batch, and "
            "averages the model's confidence across batches."
        ]
    )

    add_section(
        "7. Risk Prioritization",
        paragraphs=[
            "Open findings (anything short of fully compliant) "
            "are ranked to help focus remediation effort. Ranking "
            "combines two factors: how likely the finding is to "
            "represent a genuine, actionable gap (based on its "
            "compliance status) and how significant the "
            "consequence would be if left unaddressed (based on "
            "its assigned severity). The combined score sorts "
            "findings into priority tiers with suggested "
            "remediation timeframes. This is a triage heuristic "
            "intended to aid human judgment, not a certified "
            "risk-scoring methodology."
        ]
    )

    add_section(
        "8. Cost & Risk Exposure Estimates",
        paragraphs=[
            "Where shown, cost-savings and risk-exposure figures "
            "are calculated from assumptions the assessor enters "
            "directly — such as an assumed consultant rate, hours "
            "per requirement, and the value of contracts tied to "
            "compliance. The tool applies straightforward "
            "arithmetic to those inputs; it does not independently "
            "estimate market rates, legal exposure, or contract "
            "risk. These figures are only as accurate as the "
            "assumptions supplied and are clearly presented as "
            "estimates, not financial or legal determinations."
        ]
    )

    add_section(
        "9. Overall Compliance Rating & Projected Remediation Timeframe",
        paragraphs=[
            "Each CMMC Level carries a full control set in this tool "
            "(15 requirements for Level 1, 110 for Level 2, and 134 "
            "for Level 3, which includes the 110 Level 2 requirements "
            "plus 24 enhanced requirements). Once every control in the "
            "selected level has been reviewed, findings for the same "
            "control across multiple uploaded files are combined into "
            "a single result per control, using the same worst-status "
            "-wins logic used to combine evidence batches within one "
            "file.",

            "The Overall Compliance Rating is the count of controls "
            "found fully COMPLIANT divided by the total number of "
            "controls defined for that level. A level is rated "
            "\"Compliant\" only when 100% of its controls are "
            "compliant — for example, 15 of 15 Level 1 controls "
            "compliant is a 100% \"Compliant\" rating, while 14 of 15 "
            "is a 93% \"Not Compliant\" rating. Any status short of "
            "fully compliant on any control keeps the level at \"Not "
            "Compliant,\" regardless of how high the percentage is.",

            "The Projected Remediation Timeframe reflects the "
            "recommended timeframe (Immediate, 30 days, 90 days, or "
            "Monitor) associated with the single highest-priority open "
            "finding at that level, using the same likelihood-times-"
            "impact prioritization described above. This is an "
            "internal tool metric intended to help an organization "
            "gauge urgency and is distinct from the official DoD/SPRS "
            "scoring methodology used in a certified CMMC assessment, "
            "which applies weighted point values per requirement "
            "rather than a simple percentage."
        ]
    )

    add_section(
        "10. Human Oversight & Limitations",
        paragraphs=[
            "This tool is designed to assist, not replace, a "
            "qualified assessor. AI-generated findings can be "
            "incomplete or mistaken, particularly where evidence "
            "is ambiguous or where a requirement depends on "
            "information outside the uploaded logs. All findings, "
            "priorities, and estimates in this report should be "
            "reviewed by qualified personnel before being relied "
            "upon for compliance, contracting, or legal decisions."
        ]
    )

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# EXPORT ASSESSMENT (UI)
# ============================================================

if "assessment_results" in st.session_state:

    st.divider()

    st.subheader("Export Assessment")

    st.caption(
        "Choose the export that fits your audience. All exports "
        "reflect the same underlying findings."
    )

    assessment_level_value = st.session_state.get("assessment_level")

    framework_version_value = st.session_state.get("assessment_framework")

    all_results_value = st.session_state["assessment_results"]

    pdf_export_password = st.text_input(
        "🔒 Password-protect exported PDFs (optional)",
        type="password",
        key="pdf_export_password",
        help=(
            "If set, all four PDF exports below will require this "
            "password to open — useful since these reports can "
            "contain proprietary log evidence and company details. "
            "Share the password with the intended recipient through "
            "a separate channel than the PDF itself (not the same "
            "email)."
        )
    ) or None

    export_col1, export_col2 = st.columns(2)

    with export_col1:

        st.markdown("**🔧 Technical Findings Report**")

        st.caption(
            "Full technical detail for your cybersecurity team: "
            "requirements, assessment objectives, evidence "
            "reviewed, AI reasoning, and remediation guidance."
        )

        technical_pdf_buffer = build_technical_pdf_report(
            assessment_level=assessment_level_value,
            framework_version=framework_version_value,
            all_results=all_results_value,
            pdf_password=pdf_export_password
        )

        st.download_button(
            label="📥 Download Technical Report (PDF)",
            data=technical_pdf_buffer,
            file_name="GetRight_CMMC_Technical_Findings.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="download_technical_pdf"
        )

        st.markdown("")

        st.markdown("**🖼️ Visual Report**")

        st.caption(
            "Just the charts — findings by status, by control "
            "family, and the risk matrix. No text findings or "
            "dollar figures."
        )

        visuals_pdf_buffer = build_visuals_pdf_report(
            assessment_level=assessment_level_value,
            framework_version=framework_version_value,
            all_results=all_results_value,
            pdf_password=pdf_export_password
        )

        st.download_button(
            label="📥 Download Visual Report (PDF)",
            data=visuals_pdf_buffer,
            file_name="GetRight_CMMC_Visual_Report.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="download_visuals_pdf"
        )

    with export_col2:

        st.markdown("**📈 Executive Summary**")

        st.caption(
            "Plain-language summary for stakeholders: overall "
            "posture, top priorities, and the cost-savings / "
            "risk-exposure estimates. No raw log evidence or "
            "technical jargon."
        )

        executive_pdf_buffer = build_executive_pdf_report(
            assessment_level=assessment_level_value,
            framework_version=framework_version_value,
            all_results=all_results_value,
            consultant_hourly_rate=st.session_state.get(
                "consultant_hourly_rate", 250
            ),
            consultant_hours_per_control=st.session_state.get(
                "consultant_hours_per_control", 1.5
            ),
            tool_cost=st.session_state.get("tool_cost", 0.0),
            annual_contract_value=st.session_state.get(
                "annual_contract_value", 0
            ),
            pdf_password=pdf_export_password
        )

        st.download_button(
            label="📥 Download Executive Summary (PDF)",
            data=executive_pdf_buffer,
            file_name="GetRight_CMMC_Executive_Summary.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="download_executive_pdf"
        )

        st.markdown("")

        st.markdown("**📋 Methodology Overview**")

        st.caption(
            "Explains how the tool arrives at its findings — "
            "evidence handling, AI review process, prioritization, "
            "and cost-estimate logic — without exposing source "
            "code."
        )

        methodology_pdf_buffer = build_methodology_pdf_report(
            assessment_level=assessment_level_value,
            framework_version=framework_version_value,
            pdf_password=pdf_export_password
        )

        st.download_button(
            label="📥 Download Methodology Overview (PDF)",
            data=methodology_pdf_buffer,
            file_name="GetRight_CMMC_Methodology_Overview.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="download_methodology_pdf"
        )
      
