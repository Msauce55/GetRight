import hashlib
import json
from pathlib import Path

import streamlit as st

# -----------------------------
# Page Configuration
# -----------------------------
st.set_page_config(
    page_title="GetRight: CMMC Compliance Auditor",
    page_icon="🛡️",
    layout="wide"
)

AUTH_FILE = Path(__file__).resolve().parent / "users.json"


def hash_password(email: str, password: str) -> str:
    value = f"{email.lower().strip()}:{password}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_users() -> dict:
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_users(users: dict) -> None:
    AUTH_FILE.write_text(json.dumps(users, indent=2))


# -----------------------------
# Initialize Session State
# -----------------------------
if "assessment_started" not in st.session_state:
    st.session_state.assessment_started = False

if "company_info" not in st.session_state:
    st.session_state.company_info = {
        "company_name": "",
        "representative": "",
        "representative_email": "",
    }
    st.session_state.management_access = False
    st.session_state.company_info_submitted = False

if "users" not in st.session_state:
    st.session_state.users = load_users()

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

if "auth_message" not in st.session_state:
    st.session_state.auth_message = ""


# -----------------------------
# Custom Styling
# -----------------------------
st.markdown(
    """
    <style>
    
    div.stButton > button {
        background-color: #28a745;
        color: white;
        font-size: 18px;
        font-weight: bold;
        border-radius: 10px;
        padding: 10px 25px;
    }

    div.stButton > button:hover {
        background-color: #218838;
        color: white;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# -----------------------------
# Landing Page
# -----------------------------
st.title("GetRight: :green[CMMC Compliance Auditor]")


st.divider()


st.markdown(
"""
## Who We Are

A group of college students assisting **Ada Analytics** in developing a 
CMMC compliance auditing platform.

Our mission is to help organizations assess their cybersecurity maturity,
identify compliance gaps, and generate actionable recommendations aligned
with:

- **CMMC 2.0**
- **NIST SP 800-171 Rev. 3**
- **DoW Assessment Methodology**

The GetRight platform transforms compliance requirements into an organized,
repeatable assessment workflow.
"""
)

st.divider()
# -----------------------------
# Resources Button
# -----------------------------
if st.button("📚 Resources", use_container_width=True):
    st.switch_page("pages/05_Resources.py")
# -----------------------------
# Get Compliant Button
# -----------------------------
if st.button(
    "🟢 Get Compliant",
    use_container_width=True
):

    st.session_state.assessment_started = True
# -----------------------------
# Get Compliant Button
# -----------------------------
if st.button("🤝 Customer Impact", use_container_width=True):
    st.switch_page("pages/06_Customer_Impact.py")
# -----------------------------
# Assessment Overview
# -----------------------------
if st.session_state.assessment_started:

    st.success(
        "Welcome to the GetRight CMMC Compliance Auditor!"
    )


    st.header(
        "Your Compliance Journey Starts Here"
    )


    st.write(
"""
The AI-assisted assessment process will guide your organization through:

### Phase 1: Assessment
✔ Identify organization information  
✔ Determine CMMC target level  
✔ Review security requirements  


### Phase 2: Evidence Collection
✔ Upload policies and artifacts  
✔ Validate documentation  
✔ Organize compliance evidence  


### Phase 3: Compliance Analysis
✔ Map evidence to controls  
✔ Identify security gaps  
✔ Generate remediation guidance  


### Phase 4: Reporting
✔ Create executive summaries  
✔ Produce compliance readiness reports  
"""
    )


    st.info(
        "Estimated completion time: 30–60 minutes depending on organizational readiness."
    )


    st.divider()


    if st.button(
        "🚀 Start Assessment",
        type="primary",
        use_container_width=True
    ):

        st.switch_page(
            "pages/02_Assessment.py"
        )
st.divider()

if not st.session_state.logged_in_user:
    st.header("Account Access")
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login = st.form_submit_button("Sign In")

            if login:
                email = email.strip().lower()
                if not email or not password:
                    st.error("Enter both email and password to sign in.")
                elif email not in st.session_state.users:
                    st.error("No account found for that email.")
                else:
                    hashed = hash_password(email, password)
                    if st.session_state.users[email]["password"] != hashed:
                        st.error("Incorrect password.")
                    else:
                        st.session_state.logged_in_user = email
                        st.success(f"Signed in as {email}.")
                        st.experimental_rerun()

    with tab_register:
        with st.form("register_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            register = st.form_submit_button("Create Account")

            if register:
                email = email.strip().lower()
                if not email or not password or not confirm_password:
                    st.error("Enter email and matching passwords to create an account.")
                elif password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(password) < 8:
                    st.error("Password must be at least 8 characters long.")
                elif email in st.session_state.users:
                    st.error("An account already exists for that email.")
                else:
                    st.session_state.users[email] = {
                        "password": hash_password(email, password)
                    }
                    save_users(st.session_state.users)
                    st.session_state.logged_in_user = email
                    st.success(f"Account created and signed in as {email}.")
                    st.experimental_rerun()

    st.info("Account Access is for Management Only.")

st.success(f"Signed in as {st.session_state.logged_in_user}.")
if st.button("Log out"):
    st.session_state.logged_in_user = None
    st.experimental_rerun()

with st.expander("Account details"):
    st.write(f"**Email:** {st.session_state.logged_in_user}")


st.markdown(
    """
    <div style="
        background-color: #d4edda;
        border: 1px solid #28a745;
        border-radius: 8px;
        padding: 15px;
        color: #155724;
        margin-bottom: 10px;
    ">
        <strong>Sole Developer/Technical Lead:</strong> Mikayla Saucedo<br><br>
        <strong>Project Team/Contributors:</strong> Brianna Lopez &amp; Victor Espinoza<br><br>
        <strong>Project Advisor:</strong> Dr. Ray Hsu
    </div>
    """,
    unsafe_allow_html=True
)

