import os
import sys
import json
import asyncio
import streamlit as st
import pandas as pd
from datetime import datetime

# Set page configuration
st.set_page_config(
    page_title="RAG Evaluation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom CSS for premium styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .metric-card {
        background-color: #1E293B;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #334155;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    .metric-title {
        color: #94A3B8;
        font-size: 14px;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 8px;
    }
    
    .metric-value {
        color: #F8FAFC;
        font-size: 28px;
        font-weight: 700;
    }
    
    .metric-status-pass {
        color: #10B981;
        font-weight: 600;
        font-size: 14px;
        margin-top: 4px;
    }
    
    .metric-status-fail {
        color: #EF4444;
        font-weight: 600;
        font-size: 14px;
        margin-top: 4px;
    }
    
    .status-badge-passed {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10B981;
        padding: 6px 12px;
        border-radius: 20px;
        border: 1px solid rgba(16, 185, 129, 0.3);
        font-weight: bold;
        display: inline-block;
    }
    
    .status-badge-failed {
        background-color: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        padding: 6px 12px;
        border-radius: 20px;
        border: 1px solid rgba(239, 68, 68, 0.3);
        font-weight: bold;
        display: inline-block;
    }
    
    .section-title {
        color: #38BDF8;
        border-bottom: 2px solid #334155;
        padding-bottom: 8px;
        margin-top: 25px;
        margin-bottom: 15px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Add root folder to path so imports work correctly
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

RESULTS_FILE = os.path.join(ROOT_DIR, "results", "evaluation_results.json")

# Define threshold boundaries (Phase 13 success criteria)
THRESHOLDS = {
    "bleu1": 0.40,
    "bleu4": 0.20,
    "rougeL_f1": 0.45,
    "faithfulness": 0.95,
    "context_precision": 0.90,
    "context_recall": 0.85,
    "coverage_score": 90.0,
    "hallucination_score": 0.05
}

METRIC_LABELS = {
    "bleu1": "BLEU-1 (N-gram 1)",
    "bleu2": "BLEU-2 (N-gram 2)",
    "bleu3": "BLEU-3 (N-gram 3)",
    "bleu4": "BLEU-4 (N-gram 4)",
    "rouge1_f1": "ROUGE-1 F1",
    "rouge2_f1": "ROUGE-2 F1",
    "rougeL_f1": "ROUGE-L F1",
    "bert_precision": "BERT Precision",
    "bert_recall": "BERT Recall",
    "bert_f1": "BERT F1",
    "faithfulness": "Faithfulness (RAGAs)",
    "answer_relevancy": "Answer Relevancy (RAGAs)",
    "context_precision": "Context Precision (RAGAs)",
    "context_recall": "Context Recall (RAGAs)",
    "coverage_score": "Section Coverage Score",
    "hallucination_score": "Hallucination Score"
}

def load_results():
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return sorted(data, key=lambda x: x.get("created_at", ""), reverse=True)
            return []
    except Exception as e:
        st.error(f"Error reading evaluation results: {e}")
        return []

async def trigger_benchmark_run():
    from benchmark_runner import run_benchmark
    await run_benchmark()

# --- Sidebar ---
st.sidebar.title("🛠️ Evaluation Control")
st.sidebar.markdown("Use this panel to trigger a new production-grade automated RAG evaluation run over the uploaded documents.")

if st.sidebar.button("⚡ Run Evaluation Benchmark", use_container_width=True):
    with st.spinner("Executing RAG Evaluation Benchmark... This compiles BLEU, ROUGE, BERTScore, RAGAs, Section Coverage, and Hallucination metrics. Please wait."):
        try:
            asyncio.run(trigger_benchmark_run())
            st.sidebar.success("🎉 Benchmark run completed successfully!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ Error during benchmark: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Metric Threshold Targets")
for metric, val in THRESHOLDS.items():
    if metric == "hallucination_score":
        st.sidebar.markdown(f"**{METRIC_LABELS.get(metric, metric)}**: `< {val:.2f}`")
    else:
        st.sidebar.markdown(f"**{METRIC_LABELS.get(metric, metric)}**: `> {val:.2f}`")

# --- Load Data ---
results = load_results()

# --- Main Dashboard Header ---
st.title("📊 Production-Grade RAG Evaluation Dashboard")
st.markdown("Automated evaluation suite verifying LLM-generated summaries against gold reference answers across 13 key metrics.")

if not results:
    st.info("ℹ️ No evaluation runs found. Click the button in the sidebar to run your first benchmark evaluation.")
    st.stop()

# --- Overview Metrics Row ---
total_runs = len(results)
passed_runs = sum(1 for r in results if r.get("status") == "PASSED")
pass_rate = (passed_runs / total_runs) * 100 if total_runs > 0 else 0

col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
with col_stat1:
    st.metric(label="Total Evaluation Runs", value=total_runs)
with col_stat2:
    st.metric(label="Passed Runs", value=passed_runs)
with col_stat3:
    st.metric(label="Overall Pass Rate", value=f"{pass_rate:.1f}%")
with col_stat4:
    latest_status = results[0].get("status", "N/A")
    if latest_status == "PASSED":
        st.markdown(f"**Latest Run Status**<br><span class='status-badge-passed'>PASSED</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"**Latest Run Status**<br><span class='status-badge-failed'>FAILED</span>", unsafe_allow_html=True)

# --- Select Run ---
st.markdown("<h2 class='section-title'>🔍 Inspection of Evaluation Runs</h2>", unsafe_allow_html=True)

run_options = []
for idx, r in enumerate(results):
    dt_str = r.get("created_at", "")
    try:
        dt = datetime.fromisoformat(dt_str)
        dt_display = dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        dt_display = dt_str
    
    doc_name = r.get("document_name", "Unknown Document")
    status = r.get("status", "UNKNOWN")
    run_options.append(f"{idx + 1}. {dt_display} | Doc: {doc_name} | [{status}]")

selected_option = st.selectbox(
    "Select an evaluation run to inspect details:",
    options=run_options,
    index=0
)

# Extract selected run index
selected_idx = run_options.index(selected_option)
selected_run = results[selected_idx]

# --- Display Selected Run Details ---
st.markdown("### Run Summary")
col_run1, col_run2, col_run3 = st.columns(3)
with col_run1:
    st.write(f"**Evaluation ID:** `{selected_run.get('id')}`")
    st.write(f"**Document Name:** `{selected_run.get('document_name')}`")
with col_run2:
    st.write(f"**Document ID:** `{selected_run.get('document_id')}`")
    st.write(f"**Timestamp:** `{selected_run.get('created_at')}`")
with col_run3:
    status = selected_run.get("status", "UNKNOWN")
    if status == "PASSED":
        st.markdown(f"**Status:** <span class='status-badge-passed'>PASSED</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"**Status:** <span class='status-badge-failed'>FAILED</span>", unsafe_allow_html=True)

if status == "FAILED":
    st.error(f"⚠️ **Diagnostics:** {selected_run.get('diagnostics')}")
    # Read missing sections if available
    results_dir = os.path.join(ROOT_DIR, "results")
    missing_path = os.path.join(results_dir, "missing_sections.json")
    if os.path.exists(missing_path):
        try:
            with open(missing_path, "r", encoding="utf-8") as f:
                missing_sections = json.load(f)
                if missing_sections:
                    st.warning(f"❌ **Missing Sections Detected:** {', '.join(missing_sections)}")
        except Exception as e:
            pass
else:
    st.success("🎉 This run met or exceeded all configured success criteria thresholds.")

# --- Selected Run Metrics Grid ---
st.markdown("### Detailed Scores & Threshold Checks")
scores = selected_run.get("scores", {})

# 4 columns for metrics grid
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
metrics_keys = list(METRIC_LABELS.keys())

for idx, metric in enumerate(metrics_keys):
    val = scores.get(metric)
    
    if val is not None:
        if metric in ["coverage_score"]:
            val_str = f"{val:.1f}%"
        else:
            val_str = f"{val:.4f}"
    else:
        val_str = "N/A"
    
    # Check threshold status
    threshold = THRESHOLDS.get(metric)
    if threshold is not None and val is not None:
        if metric == "hallucination_score":
            if val <= threshold:
                status_text = f"✅ Pass (≤ {threshold:.2f})"
                status_class = "metric-status-pass"
            else:
                status_text = f"❌ Fail (> {threshold:.2f})"
                status_class = "metric-status-fail"
        elif metric == "coverage_score":
            if val >= threshold:
                status_text = f"✅ Pass (≥ {threshold:.0f}%)"
                status_class = "metric-status-pass"
            else:
                status_text = f"❌ Fail (< {threshold:.0f}%)"
                status_class = "metric-status-fail"
        else:
            if val >= threshold:
                status_text = f"✅ Pass (≥ {threshold:.2f})"
                status_class = "metric-status-pass"
            else:
                status_text = f"❌ Fail (< {threshold:.2f})"
                status_class = "metric-status-fail"
    else:
        status_text = "Target: N/A"
        status_class = "metric-status-pass"
        
    metric_card_html = f"""
    <div class="metric-card">
        <div class="metric-title">{METRIC_LABELS.get(metric, metric)}</div>
        <div class="metric-value">{val_str}</div>
        <div class="{status_class}">{status_text}</div>
    </div>
    """
    
    col_idx = idx % 4
    if col_idx == 0:
        with col_m1:
            st.markdown(metric_card_html, unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    elif col_idx == 1:
        with col_m2:
            st.markdown(metric_card_html, unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    elif col_idx == 2:
        with col_m3:
            st.markdown(metric_card_html, unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    elif col_idx == 3:
        with col_m4:
            st.markdown(metric_card_html, unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

# --- Texts Side-by-Side Comparison ---
st.markdown("<h2 class='section-title'>📝 Text Generation & Ground Truth</h2>", unsafe_allow_html=True)

col_txt1, col_txt2 = st.columns(2)
with col_txt1:
    st.markdown("### 🎯 Reference Gold Answer (Ground Truth)")
    st.markdown(f"<div style='background-color: #0F172A; padding: 15px; border-radius: 8px; border: 1px solid #1E293B; height: 400px; overflow-y: scroll;'>{selected_run.get('reference_text')}</div>", unsafe_allow_html=True)

with col_txt2:
    st.markdown("### 🤖 Chatbot Generated Response")
    st.markdown(f"<div style='background-color: #0F172A; padding: 15px; border-radius: 8px; border: 1px solid #1E293B; height: 400px; overflow-y: scroll;'>{selected_run.get('response_text')}</div>", unsafe_allow_html=True)

st.markdown("### 🔍 User Query")
st.code(selected_run.get("query_text"))

# --- Historical Performance Chart ---
st.markdown("<h2 class='section-title'>📈 Historical Performance & Metrics Trend</h2>", unsafe_allow_html=True)

# Prepare DataFrame for chart
chart_data = []
for r in reversed(results):
    dt_str = r.get("created_at", "")
    try:
        dt = datetime.fromisoformat(dt_str)
        date_label = dt.strftime("%m-%d %H:%M")
    except:
        date_label = dt_str
        
    row = {"Run Time": date_label}
    for m in THRESHOLDS.keys():
        row[METRIC_LABELS.get(m, m)] = r.get("scores", {}).get(m, 0.0)
    chart_data.append(row)

df_chart = pd.DataFrame(chart_data)

st.markdown("This line chart visualizes how evaluation scores progress across evaluation runs. You can toggle metrics using the selector below.")
available_metrics = [METRIC_LABELS.get(m) for m in THRESHOLDS.keys()]
selected_chart_metrics = st.multiselect(
    "Select metrics to visualize:",
    options=available_metrics,
    default=[METRIC_LABELS.get("bleu4"), METRIC_LABELS.get("rougeL_f1"), METRIC_LABELS.get("coverage_score"), METRIC_LABELS.get("hallucination_score")]
)

if selected_chart_metrics:
    chart_df_filtered = df_chart[["Run Time"] + selected_chart_metrics].set_index("Run Time")
    st.line_chart(chart_df_filtered)
else:
    st.warning("Please select at least one metric to render the trend chart.")

# --- Raw Results Table ---
st.markdown("<h2 class='section-title'>📋 Raw Evaluation Log</h2>", unsafe_allow_html=True)
flat_results = []
for idx, r in enumerate(results):
    flat_results.append({
        "Index": idx + 1,
        "Timestamp": r.get("created_at"),
        "Document": r.get("document_name"),
        "Status": r.get("status"),
        "BLEU-4": r.get("scores", {}).get("bleu4"),
        "ROUGE-L F1": r.get("scores", {}).get("rougeL_f1"),
        "Coverage %": r.get("scores", {}).get("coverage_score"),
        "Hallucination": r.get("scores", {}).get("hallucination_score"),
        "Faithfulness": r.get("scores", {}).get("faithfulness"),
        "Ctx Precision": r.get("scores", {}).get("context_precision"),
        "Ctx Recall": r.get("scores", {}).get("context_recall"),
    })
df_flat = pd.DataFrame(flat_results)
st.dataframe(df_flat.set_index("Index"), use_container_width=True)
