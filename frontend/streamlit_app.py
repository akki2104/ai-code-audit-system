"""Streamlit UI for AI Code Audit System."""

import json
import time
import requests
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AI Code Audit System",
    page_icon="🛡️",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stApp { max-width: 1200px; margin: 0 auto; }
    .severity-critical { color: #ff4444; font-weight: bold; }
    .severity-high { color: #ff8800; font-weight: bold; }
    .severity-medium { color: #ffbb33; font-weight: bold; }
    .severity-low { color: #00C851; font-weight: bold; }
    .health-score-container {
        text-align: center;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .finding-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


def severity_color(severity: str) -> str:
    colors = {
        "Critical": "#ff4444",
        "High": "#ff8800",
        "Medium": "#ffbb33",
        "Low": "#00C851",
    }
    return colors.get(severity, "#888")


def health_score_color(score: int) -> str:
    if score >= 80:
        return "#00C851"
    elif score >= 50:
        return "#ffbb33"
    return "#ff4444"


def render_health_gauge(score: int):
    """Render a health score gauge chart."""
    color = health_score_color(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Code Health Score", "font": {"size": 24}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 50], "color": "#ffebee"},
                {"range": [50, 80], "color": "#fff8e1"},
                {"range": [80, 100], "color": "#e8f5e9"},
            ],
            "threshold": {
                "line": {"color": "black", "width": 4},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig.update_layout(height=300, margin=dict(t=80, b=20, l=40, r=40))
    st.plotly_chart(fig, width="stretch")


def render_severity_pie(report: dict):
    """Render severity distribution pie chart."""
    labels = ["Critical", "High", "Medium", "Low"]
    values = [
        report.get("total_critical", 0),
        report.get("total_high", 0),
        report.get("total_medium", 0),
        report.get("total_low", 0),
    ]
    colors = ["#ff4444", "#ff8800", "#ffbb33", "#00C851"]

    if sum(values) == 0:
        st.info("No security findings to display.")
        return

    fig = px.pie(
        names=labels,
        values=values,
        color=labels,
        color_discrete_map=dict(zip(labels, colors)),
        title="Security Findings by Severity",
    )
    fig.update_traces(textposition="inside", textinfo="value+label")
    fig.update_layout(height=350, margin=dict(t=60, b=20))
    st.plotly_chart(fig, width="stretch")


def render_file_heatmap(findings: list):
    """Render file-level finding count heatmap."""
    file_counts = {}
    for f in findings:
        fp = f.get("file_path", "unknown")
        file_counts[fp] = file_counts.get(fp, 0) + 1

    if not file_counts:
        return

    files = list(file_counts.keys())
    counts = list(file_counts.values())

    fig = px.bar(
        x=counts, y=files, orientation="h",
        title="Findings by File",
        labels={"x": "Number of Findings", "y": "File"},
        color=counts,
        color_continuous_scale="RdYlGn_r",
    )
    fig.update_layout(height=max(250, len(files) * 40), margin=dict(t=60, b=20))
    st.plotly_chart(fig, width="stretch")


def render_security_finding(finding: dict, idx: int):
    """Render a single security finding card."""
    severity = finding.get("severity", "Low")
    color = severity_color(severity)

    with st.expander(
        f"{'🔴' if severity == 'Critical' else '🟠' if severity == 'High' else '🟡' if severity == 'Medium' else '🟢'} "
        f"[{severity}] {finding.get('category', 'Unknown')} — {finding.get('file_path', '')}",
        expanded=(severity == "Critical"),
    ):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Description:** {finding.get('description', '')}")
            if finding.get("line_number"):
                st.markdown(f"**Line:** {finding['line_number']}")
        with col2:
            st.markdown(f"**Confidence:** {finding.get('confidence', 0):.0%}")
            st.markdown(f"**ID:** `{finding.get('id', '')}`")

        if finding.get("code_snippet"):
            st.code(finding["code_snippet"], language="python")

        st.markdown(f"**💡 Fix Suggestion:** {finding.get('fix_suggestion', '')}")


def render_quality_finding(finding: dict, idx: int):
    """Render a single quality finding card."""
    with st.expander(
        f"🔧 [{finding.get('category', 'Unknown')}] {finding.get('file_path', '')} — {finding.get('description', '')[:80]}",
    ):
        st.markdown(f"**Description:** {finding.get('description', '')}")
        st.markdown(f"**File:** `{finding.get('file_path', '')}`")
        st.markdown(f"**💡 Suggestion:** {finding.get('suggestion', '')}")


def poll_status(audit_id: str) -> dict:
    """Poll the audit status endpoint."""
    try:
        resp = requests.get(f"{API_BASE}/api/audit/{audit_id}/status", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return {"status": "error", "error": "Failed to connect to backend"}


def get_report(audit_id: str) -> dict | None:
    """Fetch the final audit report."""
    try:
        resp = requests.get(f"{API_BASE}/api/audit/{audit_id}/report", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return None


# ─── SIDEBAR ───
with st.sidebar:
    st.title("🛡️ AI Code Audit")
    st.markdown("---")

    input_method = st.radio("Choose input method:", ["Upload ZIP", "GitHub URL"])

    audit_id = None

    if input_method == "Upload ZIP":
        uploaded_file = st.file_uploader("Upload a ZIP file", type=["zip"])
        if st.button("🚀 Start Audit", disabled=not uploaded_file, width="stretch"):
            if uploaded_file:
                with st.spinner("Uploading..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/zip")}
                    try:
                        resp = requests.post(f"{API_BASE}/api/audit/upload", files=files, timeout=30)
                        if resp.status_code == 200:
                            result = resp.json()
                            st.session_state["audit_id"] = result["audit_id"]
                            st.session_state["audit_status"] = "queued"
                            st.session_state.pop("report", None)
                            st.rerun()
                        else:
                            st.error(f"Upload failed: {resp.text}")
                    except requests.RequestException as e:
                        st.error(f"Connection error: {e}")

    else:
        repo_url = st.text_input("GitHub Repository URL",
                                  placeholder="https://github.com/user/repo")
        if st.button("🚀 Start Audit", disabled=not repo_url, width="stretch"):
            if repo_url:
                with st.spinner("Cloning repository..."):
                    try:
                        resp = requests.post(
                            f"{API_BASE}/api/audit/github",
                            json={"repo_url": repo_url},
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            result = resp.json()
                            st.session_state["audit_id"] = result["audit_id"]
                            st.session_state["audit_status"] = "queued"
                            st.session_state.pop("report", None)
                            st.rerun()
                        else:
                            st.error(f"Clone failed: {resp.text}")
                    except requests.RequestException as e:
                        st.error(f"Connection error: {e}")

    st.markdown("---")
    st.markdown("### How It Works")
    st.markdown("""
    1. **Scanner Agent** — Parses your codebase
    2. **Security Auditor** — Finds OWASP Top 10 vulnerabilities
    3. **Code Reviewer** — Identifies quality issues
    4. **Report Generator** — Compiles the final report
    """)

# ─── MAIN AREA ───
st.title("🛡️ AI Code Review & Security Audit")

# Check for active audit
if "audit_id" in st.session_state:
    audit_id = st.session_state["audit_id"]
    current_status = st.session_state.get("audit_status", "queued")

    if current_status != "complete" and current_status != "error":
        # Show progress
        st.markdown("### 🔄 Audit In Progress")
        st.markdown(f"**Audit ID:** `{audit_id}`")

        status_steps = {
            "queued": 0,
            "scanning": 1,
            "auditing": 2,
            "reviewing": 3,
            "generating": 4,
            "complete": 5,
        }

        step_names = ["Queued", "📂 Scanning Files", "🔒 Security Audit", "🔍 Code Review", "📊 Generating Report", "✅ Complete"]

        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        # Poll loop
        max_polls = 300  # 10 minutes max
        for _ in range(max_polls):
            status_data = poll_status(audit_id)
            current_status = status_data.get("status", "queued")
            st.session_state["audit_status"] = current_status

            step_idx = status_steps.get(current_status, 0)
            progress_val = min(step_idx / 5, 1.0)

            with progress_placeholder.container():
                st.progress(progress_val)
                cols = st.columns(5)
                for i, name in enumerate(step_names[1:]):
                    with cols[i]:
                        if i < step_idx:
                            st.markdown(f"✅ {name}")
                        elif i == step_idx:
                            st.markdown(f"⏳ {name}")
                        else:
                            st.markdown(f"⬜ {name}")

            if current_status == "complete":
                st.session_state["audit_status"] = "complete"
                time.sleep(0.5)
                st.rerun()
                break
            elif current_status == "error":
                st.error(f"Audit failed: {status_data.get('error', 'Unknown error')}")
                break

            time.sleep(2)

    elif current_status == "complete":
        # Fetch and display report
        if "report" not in st.session_state or st.session_state["report"] is None:
            report = get_report(audit_id)
            if report:
                st.session_state["report"] = report
            else:
                st.error("Failed to fetch report.")
                st.stop()

        report = st.session_state["report"]

        # Header metrics
        st.markdown("### 📊 Audit Results")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Files Analyzed", report.get("files_analyzed", 0))
        with col2:
            st.metric("🔴 Critical", report.get("total_critical", 0))
        with col3:
            st.metric("🟠 High", report.get("total_high", 0))
        with col4:
            st.metric("🟡 Medium", report.get("total_medium", 0))
        with col5:
            st.metric("🟢 Low", report.get("total_low", 0))

        st.markdown("---")

        # Health Score and Severity Pie
        col_left, col_right = st.columns(2)
        with col_left:
            render_health_gauge(report.get("health_score", 0))
        with col_right:
            render_severity_pie(report)

        st.markdown("---")

        # Executive Summary
        st.markdown("### 📋 Executive Summary")
        st.info(report.get("summary", "No summary available."))

        st.markdown("---")

        # File heatmap
        all_findings = report.get("security_findings", []) + report.get("quality_findings", [])
        render_file_heatmap(all_findings)

        st.markdown("---")

        # Security Findings
        security_findings = report.get("security_findings", [])
        st.markdown(f"### 🔒 Security Findings ({len(security_findings)})")
        if security_findings:
            # Sort by severity
            severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            security_findings.sort(key=lambda x: severity_order.get(x.get("severity", "Low"), 4))
            for i, finding in enumerate(security_findings):
                render_security_finding(finding, i)
        else:
            st.success("No security vulnerabilities found! ✨")

        st.markdown("---")

        # Quality Findings
        quality_findings = report.get("quality_findings", [])
        st.markdown(f"### 🔧 Code Quality Findings ({len(quality_findings)})")
        if quality_findings:
            for i, finding in enumerate(quality_findings):
                render_quality_finding(finding, i)
        else:
            st.success("No code quality issues found! ✨")

        st.markdown("---")

        # Export
        col_export1, col_export2 = st.columns(2)
        with col_export1:
            st.download_button(
                "📥 Export Report (JSON)",
                data=json.dumps(report, indent=2),
                file_name=f"audit_report_{audit_id[:8]}.json",
                mime="application/json",
                width="stretch",
            )
        with col_export2:
            if st.button("🔄 New Audit", width="stretch"):
                for key in ["audit_id", "audit_status", "report"]:
                    st.session_state.pop(key, None)
                st.rerun()

else:
    # Welcome screen
    st.markdown("""
    ### Welcome! 👋

    Upload a codebase (ZIP file) or paste a GitHub repository URL to start an AI-powered code audit.

    **What this system checks:**
    - 🔒 **Security Vulnerabilities** — SQL Injection, XSS, Hardcoded Secrets, Broken Auth, and more (OWASP Top 10)
    - 🔧 **Code Quality** — Anti-patterns, missing error handling, performance issues, dead code
    - 📊 **Health Score** — Overall code health rating from 0-100

    **How it works:**
    Four AI agents analyze your code in sequence using a LangGraph state machine:

    ```
    Scanner → Security Auditor → Code Reviewer → Report Generator
    ```

    Use the sidebar to get started! ➡️
    """)
