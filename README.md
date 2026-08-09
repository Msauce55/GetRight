# GetRight
# 🛡️ GetRight CMMC Assessment

An AI-assisted Streamlit application that analyzes cybersecurity evidence logs against **CMMC (Cybersecurity Maturity Model Certification)** requirements and generates audit-ready reports.

## What It Does

GetRight helps organizations prepare for a CMMC assessment by automatically reviewing uploaded cybersecurity evidence (logs, configs, records) against the official control requirements for a selected CMMC level, then producing polished PDF reports summarizing the findings.

- **Full CMMC control coverage**
  - **Level 1** — 15 requirements (FAR 52.204-21)
  - **Level 2** — 110 requirements (NIST SP 800-171 Rev. 2, 14 control families)
  - **Level 3** — 134 requirements (the 110 Level 2 requirements plus 24 enhanced requirements from NIST SP 800-172)
- **AI-powered evidence analysis** — uploaded logs (CSV, XML, JSON, TXT) are analyzed against each control's assessment objectives using an LLM (via the Groq API), with large files automatically batched.
- **Findings & prioritization** — results are rated by compliance status and prioritized by likelihood × impact, with a recommended remediation timeframe for each open finding.
- **PDF report exports:**
  - 🔧 **Technical Findings Report** — full detail for a cybersecurity team (requirements, objectives, evidence reviewed, AI reasoning, remediation guidance)
  - 🖼️ **Visual Report** — charts only (findings by status, by control family, risk matrix)
  - 📈 **Executive Summary** — plain-language overview with cost-savings and risk-exposure estimates for stakeholders
  - 📋 **Methodology Overview** — explains how the tool evaluates evidence and arrives at findings, without exposing source code

## How It Works

1. Enter company information (name, representative, contact email).
2. Select a CMMC level and assessment framework version.
3. Upload cybersecurity evidence logs (Windows, Linux, macOS, firewall, SIEM, EDR, authentication logs, etc.).
4. The app analyzes each control against the uploaded evidence and produces a compliance status per requirement.
5. Review results and export the report format that fits your audience.

## Tech Stack

- [Streamlit](https://streamlit.io/) — web app framework
- [Groq API](https://groq.com/) (OpenAI-compatible client) — AI evidence analysis
- [ReportLab](https://www.reportlab.com/) — PDF report generation
- [Matplotlib](https://matplotlib.org/) — charts and visualizations
- [Pandas](https://pandas.pydata.org/) — data handling

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/getright.git
cd getright
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure your API key
Create a `.env` file in the project root:
```
GROQ_API_KEY=your_groq_api_key_here
```

Or, if deploying on **Streamlit Community Cloud**, add it under your app's **Settings → Secrets**:
```toml
GROQ_API_KEY = "your_groq_api_key_here"
```

### 4. Run the app
```bash
streamlit run streamlit_app.py
```

## Disclaimer

This tool is designed to **assist, not replace**, a qualified CMMC assessor. AI-generated findings can be incomplete or mistaken, particularly where evidence is ambiguous. All findings, priorities, and cost/risk estimates should be reviewed by qualified personnel before being relied upon for compliance, contracting, or legal decisions. This tool does not produce an official DoD/SPRS score.

