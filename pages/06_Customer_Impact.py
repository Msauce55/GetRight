#Show charts that show the impact of the assessment on the customer, 
# specifically, money saved, issues resolves, and an area where customers can
# leave feedback for the dev team. This page should be accessible from the 
# landing page and should be a separate page in the app. I want this sections
# to pull data from the assessment and display it in a visually appealing way 
# that details the assistance

import streamlit as st
import pandas as pd
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from impact_utils import (
    load_impact_history,
    load_feedback,
    log_feedback,
    STATUS_KEYS
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Customer Impact Dashboard",
    page_icon="📈",
    layout="wide"
)


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


# ============================================================
# HEADER
# ============================================================

st.title(
    "📈 Customer Impact Dashboard"
)

st.caption(
    "Aggregate view of the value GetRight has delivered across every "
    "assessment run. This updates automatically each time an "
    "assessment is logged from the Assessment page."
)

header_col1, header_col2 = st.columns([5, 1])

with header_col2:

    if st.button("🔄 Refresh", use_container_width=True):

        st.rerun()


# ============================================================
# LOAD DATA (re-read from disk on every run, so this page
# always reflects the latest logged assessments/feedback)
# ============================================================

history_df = load_impact_history()

feedback_df = load_feedback()


# ============================================================
# IMPACT SECTION
# ============================================================

if history_df.empty:

    st.info(
        "No assessments have been logged yet. Run an assessment on "
        "the Assessment page, then use the \"Log This Assessment to "
        "Customer Impact Dashboard\" button to see it here."
    )

else:

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    st.subheader("Filter")

    company_options = ["All Companies"] + sorted(
        history_df["company_name"].dropna().unique().tolist()
    )

    selected_company = st.selectbox(
        "Company",
        company_options
    )

    filtered_df = (
        history_df
        if selected_company == "All Companies"
        else history_df[history_df["company_name"] == selected_company]
    )

    st.divider()

    # --------------------------------------------------------
    # KPI ROW
    # --------------------------------------------------------

    total_saved = filtered_df["net_savings"].sum()

    total_exposure_avoided = filtered_df["exposure_avoided"].sum()

    total_assessments = len(filtered_df)

    total_companies = filtered_df["company_name"].nunique()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    kpi1.metric(
        "💰 Total Estimated Savings",
        f"${total_saved:,.0f}"
    )

    kpi2.metric(
        "🛡️ Risk Exposure Avoided",
        f"${total_exposure_avoided:,.0f}"
    )

    kpi3.metric(
        "📋 Assessments Run",
        total_assessments
    )

    kpi4.metric(
        "🏢 Companies Served",
        total_companies
    )

    st.caption(
        "Savings and exposure figures reflect the assumptions each "
        "assessor entered at the time of their assessment — see the "
        "Methodology Overview export on the Assessment page for how "
        "these are calculated. These are estimates, not guarantees."
    )

    st.divider()

    # --------------------------------------------------------
    # CUMULATIVE SAVINGS TREND
    # --------------------------------------------------------

    st.subheader(
        "💰 Estimated Value Delivered Over Time"
    )

    trend_df = filtered_df.copy()

    trend_df["cumulative_savings"] = trend_df["net_savings"].cumsum()

    trend_df["cumulative_exposure_avoided"] = (
        trend_df["exposure_avoided"].cumsum()
    )

    fig, ax = plt.subplots(figsize=(9, 3.5))

    ax.plot(
        trend_df["timestamp"],
        trend_df["cumulative_savings"],
        marker="o",
        markersize=4,
        color="#1a7f37",
        label="Cumulative Consultant Savings"
    )

    ax.plot(
        trend_df["timestamp"],
        trend_df["cumulative_exposure_avoided"],
        marker="o",
        markersize=4,
        color="#0969da",
        label="Cumulative Risk Exposure Avoided"
    )

    ax.set_ylabel("Estimated $ (cumulative)", fontsize=9)

    ax.legend(loc="upper left", fontsize=8)

    ax.grid(True, linestyle="--", alpha=0.3)

    fig.autofmt_xdate()

    fig.tight_layout()

    savings_buffer = io.BytesIO()

    fig.savefig(savings_buffer, format="png", dpi=150)

    plt.close(fig)

    savings_buffer.seek(0)

    st.image(savings_buffer, use_container_width=True)

    st.divider()

    # --------------------------------------------------------
    # COMPLIANCE FINDINGS TREND
    # --------------------------------------------------------

    st.subheader(
        "📊 Compliance Findings Trend"
    )

    st.caption(
        "Number of findings in each status, per logged assessment, "
        "over time."
    )

    fig2, ax2 = plt.subplots(figsize=(9, 3.5))

    bottoms = [0] * len(filtered_df)

    x_values = filtered_df["timestamp"]

    for status in STATUS_KEYS:

        values = filtered_df[status].tolist()

        ax2.bar(
            x_values,
            values,
            bottom=bottoms,
            color=STATUS_HEX[status],
            label=status.title(),
            width=2.0
        )

        bottoms = [
            bottom + value
            for bottom, value in zip(bottoms, values)
        ]

    ax2.set_ylabel("Findings", fontsize=9)

    ax2.legend(loc="upper left", fontsize=7, ncol=2)

    ax2.grid(True, linestyle="--", alpha=0.3, axis="y")

    fig2.autofmt_xdate()

    fig2.tight_layout()

    trend_buffer = io.BytesIO()

    fig2.savefig(trend_buffer, format="png", dpi=150)

    plt.close(fig2)

    trend_buffer.seek(0)

    st.image(trend_buffer, use_container_width=True)

    st.divider()

    # --------------------------------------------------------
    # AGGREGATE STATUS BREAKDOWN
    # --------------------------------------------------------

    st.subheader(
        "🥧 Findings by Status (All Time)"
    )

    total_counts = {

        status: int(filtered_df[status].sum())

        for status in STATUS_KEYS

    }

    pie_col, table_col = st.columns([1, 1])

    with pie_col:

        nonzero_labels = [
            status.title()
            for status in STATUS_KEYS
            if total_counts[status] > 0
        ]

        nonzero_values = [
            total_counts[status]
            for status in STATUS_KEYS
            if total_counts[status] > 0
        ]

        nonzero_colors = [
            STATUS_HEX[status]
            for status in STATUS_KEYS
            if total_counts[status] > 0
        ]

        if nonzero_values:

            fig3, ax3 = plt.subplots(figsize=(4, 4))

            ax3.pie(
                nonzero_values,
                labels=nonzero_labels,
                colors=nonzero_colors,
                autopct="%1.0f%%",
                textprops={"fontsize": 8}
            )

            fig3.tight_layout()

            pie_buffer = io.BytesIO()

            fig3.savefig(pie_buffer, format="png", dpi=150)

            plt.close(fig3)

            pie_buffer.seek(0)

            st.image(pie_buffer, use_container_width=True)

        else:

            st.info("No findings recorded yet.")

    with table_col:

        summary_table = pd.DataFrame({

            "Status": [
                status.title()
                for status in STATUS_KEYS
            ],

            "Total Findings": [
                total_counts[status]
                for status in STATUS_KEYS
            ]

        })

        st.dataframe(
            summary_table,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # --------------------------------------------------------
    # COMPANIES SERVED
    # --------------------------------------------------------

    st.subheader(
        "🏆 Companies Served"
    )

    company_summary = (

        filtered_df

        .groupby("company_name")

        .agg(

            assessments_run=("company_name", "count"),
            total_savings=("net_savings", "sum"),
            total_exposure_avoided=("exposure_avoided", "sum"),
            last_assessment=("timestamp", "max")

        )

        .reset_index()

        .sort_values("total_savings", ascending=False)

    )

    company_summary["total_savings"] = company_summary[
        "total_savings"
    ].map(lambda value: f"${value:,.0f}")

    company_summary["total_exposure_avoided"] = company_summary[
        "total_exposure_avoided"
    ].map(lambda value: f"${value:,.0f}")

    company_summary.columns = [
        "Company",
        "Assessments Run",
        "Total Savings",
        "Total Exposure Avoided",
        "Last Assessment"
    ]

    st.dataframe(
        company_summary,
        use_container_width=True,
        hide_index=True
    )

    with st.expander("📄 Full Assessment History"):

        history_display = filtered_df[[
            "timestamp",
            "company_name",
            "cmmc_level",
            "framework_version",
            "num_controls",
            "net_savings",
            "exposure_avoided"
        ]].copy()

        history_display.columns = [
            "Date",
            "Company",
            "CMMC Level",
            "Framework",
            "Controls Assessed",
            "Net Savings ($)",
            "Exposure Avoided ($)"
        ]

        st.dataframe(
            history_display.sort_values("Date", ascending=False),
            use_container_width=True,
            hide_index=True
        )


st.divider()


# ============================================================
# CUSTOMER FEEDBACK
# ============================================================

st.header(
    "💬 Customer Feedback"
)

feedback_form_col, feedback_display_col = st.columns([1, 1])

with feedback_form_col:

    st.subheader(
        "Share Your Feedback"
    )

    with st.form("customer_feedback_form", clear_on_submit=True):

        fb_company = st.text_input(
            "Company Name"
        )

        fb_representative = st.text_input(
            "Your Name"
        )

        fb_rating = st.slider(
            "How would you rate GetRight?",
            1, 5, 5
        )

        fb_comment = st.text_area(
            "What's working well? What could be better?"
        )

        fb_submitted = st.form_submit_button(
            "Submit Feedback"
        )

        if fb_submitted:

            if not fb_company or not fb_comment:

                st.error(
                    "Company name and comments are required."
                )

            else:

                log_feedback(
                    company_name=fb_company.strip(),
                    representative=fb_representative.strip(),
                    rating=fb_rating,
                    comment=fb_comment.strip()
                )

                st.success(
                    "Thank you for your feedback!"
                )

                st.rerun()

with feedback_display_col:

    st.subheader(
        "What Customers Are Saying"
    )

    if feedback_df.empty:

        st.info(
            "No feedback submitted yet."
        )

    else:

        avg_rating = feedback_df["rating"].mean()

        st.metric(
            "⭐ Average Rating",
            f"{avg_rating:.1f} / 5",
            help=f"Based on {len(feedback_df)} reviews"
        )

        for _, row in feedback_df.head(10).iterrows():

            stars = "⭐" * int(row["rating"])

            with st.container(border=True):

                st.markdown(
                    f"**{row['company_name']}** — {stars}"
                )

                if row.get("comment"):

                    st.write(row["comment"])

                if pd.notna(row["timestamp"]):

                    st.caption(
                        row["timestamp"].strftime("%B %d, %Y") 
                          )