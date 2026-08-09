import streamlit as st

st.set_page_config(
    page_title="GetRight Management Portal",
    page_icon="🔒",
    layout="wide",
)
if not st.session_state.get("logged_in_user"):
    st.title("Access Denied")
    st.error("You must be signed in to access the management portal.")
    st.stop()
if not st.session_state.get("management_access", False):
    st.title("Access Denied")
    st.error(
        "This page is only available to GetRight management."
    )
    st.stop()

st.title("🔒 Management Portal")

company_info = st.session_state.get("company_info", {})

st.subheader("Company Information Submitted")
st.write("The following details were submitted by the client:")

st.markdown(
    f"- **Company Name:** {company_info.get('company_name', 'N/A')}\n"
    f"- **Representative:** {company_info.get('representative', 'N/A')}\n"
    f"- **Representative's Email:** {company_info.get('representative_email', 'N/A')}"
)

st.divider()

st.info(
    "This page is restricted to management only. Use the information above to review the client and schedule the CMMC compliance assessment."
)

if st.button("Return to Home", use_container_width=True):
    st.session_state.management_access = False
    st.experimental_rerun()
