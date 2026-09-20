"""
Streamlit Admin Management Dashboard
=====================================
A self-contained admin dashboard with:
  1. Login gate (default admin / admin1234)
  2. Application Health monitoring
  3. Login / user credential issuance
  4. Access control (roles & permissions)

Run with:
    pip install streamlit psutil
    streamlit run admin_dashboard.py

Data (users, roles, permissions) is persisted locally in a SQLite file
called `admin_dashboard.db` that is created automatically next to this
script on first run.
"""

import sqlite3
import hashlib
import secrets
import string
import time
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "admin_dashboard.db"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin1234"
MODULES = ["Dashboard", "User Management", "Access Control", "Reports", "System Settings"]
ROLES = ["admin", "manager", "viewer"]

st.set_page_config(page_title="Admin Console", page_icon="🛠️", layout="wide")

# --------------------------------------------------------------------------
# Password hashing helpers (salted SHA-256 — swap for bcrypt/argon2 in prod)
# --------------------------------------------------------------------------
def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def make_salt() -> str:
    return secrets.token_hex(16)


def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# --------------------------------------------------------------------------
# Database layer
# --------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            enabled INTEGER NOT NULL DEFAULT 1,
            must_reset INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            module TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(role, module)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL
        )
    """)
    conn.commit()

    # Seed default admin account if no users exist yet
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        salt = make_salt()
        pw_hash = hash_password(DEFAULT_ADMIN_PASSWORD, salt)
        cur.execute(
            "INSERT INTO users (username, salt, password_hash, role, enabled, must_reset, created_at) "
            "VALUES (?,?,?,?,1,0,?)",
            (DEFAULT_ADMIN_USERNAME, salt, pw_hash, "admin", datetime.utcnow().isoformat()),
        )
        conn.commit()

    # Seed default role/module permission matrix
    cur.execute("SELECT COUNT(*) AS c FROM permissions")
    if cur.fetchone()["c"] == 0:
        defaults = {
            "admin":   {m: 1 for m in MODULES},
            "manager": {m: (1 if m != "System Settings" else 0) for m in MODULES},
            "viewer":  {m: (1 if m == "Dashboard" else 0) for m in MODULES},
        }
        for role, mods in defaults.items():
            for module, allowed in mods.items():
                cur.execute(
                    "INSERT OR IGNORE INTO permissions (role, module, allowed) VALUES (?,?,?)",
                    (role, module, allowed),
                )
        conn.commit()
    conn.close()


def log_action(actor: str, action: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (timestamp, actor, action) VALUES (?,?,?)",
        (datetime.utcnow().isoformat(), actor, action),
    )
    conn.commit()
    conn.close()


def get_user(username: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row


def verify_login(username: str, password: str):
    user = get_user(username)
    if not user:
        return None
    if not user["enabled"]:
        return "disabled"
    if hash_password(password, user["salt"]) == user["password_hash"]:
        conn = get_conn()
        conn.execute(
            "UPDATE users SET last_login = ? WHERE username = ?",
            (datetime.utcnow().isoformat(), username),
        )
        conn.commit()
        conn.close()
        return user
    return None


def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def create_user(username: str, password: str, role: str):
    conn = get_conn()
    salt = make_salt()
    pw_hash = hash_password(password, salt)
    conn.execute(
        "INSERT INTO users (username, salt, password_hash, role, enabled, must_reset, created_at) "
        "VALUES (?,?,?,?,1,1,?)",
        (username, salt, pw_hash, role, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def set_user_enabled(username: str, enabled: bool):
    conn = get_conn()
    conn.execute("UPDATE users SET enabled = ? WHERE username = ?", (int(enabled), username))
    conn.commit()
    conn.close()


def set_user_role(username: str, role: str):
    conn = get_conn()
    conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
    conn.commit()
    conn.close()


def reset_password(username: str, new_password: str):
    conn = get_conn()
    salt = make_salt()
    pw_hash = hash_password(new_password, salt)
    conn.execute(
        "UPDATE users SET salt = ?, password_hash = ?, must_reset = 1 WHERE username = ?",
        (salt, pw_hash, username),
    )
    conn.commit()
    conn.close()


def delete_user(username: str):
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def get_permissions_matrix():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM permissions").fetchall()
    conn.close()
    matrix = {role: {} for role in ROLES}
    for r in rows:
        matrix.setdefault(r["role"], {})[r["module"]] = bool(r["allowed"])
    return matrix


def set_permission(role: str, module: str, allowed: bool):
    conn = get_conn()
    conn.execute(
        "INSERT INTO permissions (role, module, allowed) VALUES (?,?,?) "
        "ON CONFLICT(role, module) DO UPDATE SET allowed = excluded.allowed",
        (role, module, int(allowed)),
    )
    conn.commit()
    conn.close()


def get_audit_log(limit: int = 25):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


init_db()

# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "role" not in st.session_state:
    st.session_state.role = None
if "app_start_time" not in st.session_state:
    st.session_state.app_start_time = time.time()


def do_logout():
    log_action(st.session_state.username, "Logged out")
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None


# --------------------------------------------------------------------------
# Login screen
# --------------------------------------------------------------------------
def render_login():
    st.markdown(
        "<h1 style='text-align:center;'>🛠️ Admin Console</h1>",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Sign in")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)

        if submitted:
            result = verify_login(username, password)
            if result is None:
                st.error("Invalid username or password.")
                log_action(username or "unknown", "Failed login attempt")
            elif result == "disabled":
                st.error("This account has been disabled. Contact an administrator.")
                log_action(username, "Login blocked (account disabled)")
            else:
                st.session_state.logged_in = True
                st.session_state.username = result["username"]
                st.session_state.role = result["role"]
                log_action(username, "Logged in")
                if result["must_reset"]:
                    st.session_state.must_reset = True
                st.rerun()

        st.caption("Default admin login: **admin** / **admin1234** — change this password after first login.")


# --------------------------------------------------------------------------
# Dashboard: Application Health
# --------------------------------------------------------------------------
def render_health():
    st.subheader("Application Health")

    uptime = timedelta(seconds=int(time.time() - st.session_state.app_start_time))
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    active_users = conn.execute("SELECT COUNT(*) c FROM users WHERE enabled=1").fetchone()["c"]
    conn.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Session Uptime", str(uptime))
    c2.metric("Total Accounts", total_users)
    c3.metric("Active Accounts", active_users)
    c4.metric("Disabled Accounts", total_users - active_users)

    st.divider()

    if HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("CPU Usage", f"{cpu:.1f}%")
            st.progress(min(int(cpu), 100) / 100)
        with c2:
            st.metric("Memory Usage", f"{mem.percent:.1f}%")
            st.progress(min(int(mem.percent), 100) / 100)
        with c3:
            st.metric("Disk Usage", f"{disk.percent:.1f}%")
            st.progress(min(int(disk.percent), 100) / 100)

        status = "🟢 Healthy" if cpu < 85 and mem.percent < 90 else "🟠 Under Load"
        st.info(f"Overall status: **{status}**")
    else:
        st.warning(
            "`psutil` isn't installed, so live CPU/memory/disk metrics aren't available. "
            "Run `pip install psutil` to enable them."
        )

    st.divider()
    st.markdown("**Recent Activity**")
    logs = get_audit_log(15)
    if logs:
        st.dataframe(
            [{"Time (UTC)": l["timestamp"], "User": l["actor"], "Action": l["action"]} for l in logs],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No activity recorded yet.")


# --------------------------------------------------------------------------
# Dashboard: Issue Login Information
# --------------------------------------------------------------------------
def render_user_management():
    st.subheader("Issue Login Information")

    with st.expander("➕ Create a new account", expanded=False):
        with st.form("create_user_form", clear_on_submit=True):
            new_username = st.text_input("New username")
            colA, colB = st.columns(2)
            with colA:
                new_role = st.selectbox("Role", ROLES)
            with colB:
                auto_pw = st.checkbox("Auto-generate temporary password", value=True)
            manual_pw = st.text_input("Password (if not auto-generated)", type="password")
            create_submitted = st.form_submit_button("Issue login")

        if create_submitted:
            if not new_username.strip():
                st.error("Username is required.")
            elif get_user(new_username.strip()):
                st.error("That username already exists.")
            else:
                pw = generate_temp_password() if auto_pw else manual_pw
                if not pw:
                    st.error("Provide a password or enable auto-generation.")
                else:
                    create_user(new_username.strip(), pw, new_role)
                    log_action(st.session_state.username, f"Created account '{new_username}' (role={new_role})")
                    st.success(f"Account created for **{new_username}**.")
                    if auto_pw:
                        st.info(f"Temporary password: `{pw}`  \nUser will be required to reset it after first login.")

    st.divider()
    st.markdown("**Existing accounts**")

    users = list_users()
    if not users:
        st.caption("No accounts yet.")
        return

    for u in users:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 1.3, 1.2, 1.2, 1.8])
            c1.markdown(f"**{u['username']}**")
            c1.caption(f"Created {u['created_at'][:10]} · Last login: {u['last_login'][:16] if u['last_login'] else 'never'}")

            new_role = c2.selectbox(
                "Role", ROLES, index=ROLES.index(u["role"]) if u["role"] in ROLES else 0,
                key=f"role_{u['id']}", label_visibility="collapsed",
            )
            if new_role != u["role"]:
                set_user_role(u["username"], new_role)
                log_action(st.session_state.username, f"Changed role of '{u['username']}' to {new_role}")
                st.rerun()

            enabled = c3.toggle("Enabled", value=bool(u["enabled"]), key=f"enabled_{u['id']}")
            if enabled != bool(u["enabled"]):
                set_user_enabled(u["username"], enabled)
                log_action(st.session_state.username, f"{'Enabled' if enabled else 'Disabled'} account '{u['username']}'")
                st.rerun()

            if c4.button("Reset password", key=f"reset_{u['id']}"):
                temp_pw = generate_temp_password()
                reset_password(u["username"], temp_pw)
                log_action(st.session_state.username, f"Reset password for '{u['username']}'")
                st.success(f"New temporary password for {u['username']}: `{temp_pw}`")

            if u["username"] != st.session_state.username:
                if c5.button("Delete account", key=f"del_{u['id']}", type="secondary"):
                    delete_user(u["username"])
                    log_action(st.session_state.username, f"Deleted account '{u['username']}'")
                    st.rerun()
            else:
                c5.caption("Current session")


# --------------------------------------------------------------------------
# Dashboard: Access Control
# --------------------------------------------------------------------------
def render_access_control():
    st.subheader("Access Control")
    st.caption("Define which modules each role is allowed to access.")

    matrix = get_permissions_matrix()

    header_cols = st.columns([1.5] + [1] * len(MODULES))
    header_cols[0].markdown("**Role**")
    for i, module in enumerate(MODULES):
        header_cols[i + 1].markdown(f"**{module}**")

    for role in ROLES:
        row_cols = st.columns([1.5] + [1] * len(MODULES))
        row_cols[0].markdown(f"`{role}`")
        for i, module in enumerate(MODULES):
            current = matrix.get(role, {}).get(module, False)
            checked = row_cols[i + 1].checkbox(
                "", value=current, key=f"perm_{role}_{module}", label_visibility="collapsed"
            )
            if checked != current:
                set_permission(role, module, checked)
                log_action(
                    st.session_state.username,
                    f"Set permission '{module}' for role '{role}' to {checked}",
                )
                st.rerun()

    st.divider()
    st.markdown("**Notes**")
    st.caption(
        "- The `admin` role should generally retain full access.\n"
        "- Changes apply immediately to any user holding that role.\n"
        "- This matrix currently controls visibility within this console only; "
        "wire it into your application's own authorization checks for enforcement elsewhere."
    )


# --------------------------------------------------------------------------
# Main dashboard shell
# --------------------------------------------------------------------------
def render_dashboard():
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.username}")
        st.caption(f"Role: `{st.session_state.role}`")
        st.divider()
        page = st.radio(
            "Navigate",
            ["Application Health", "Issue Login Information", "Access Control"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Log out", use_container_width=True):
            do_logout()
            st.rerun()

    st.title("Admin Dashboard")

    if st.session_state.get("must_reset"):
        st.warning("You're using a temporary password. Consider issuing yourself a new one from Issue Login Information.")

    if page == "Application Health":
        render_health()
    elif page == "Issue Login Information":
        render_user_management()
    elif page == "Access Control":
        render_access_control()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if st.session_state.logged_in:
    render_dashboard()
else:
    render_login()
    