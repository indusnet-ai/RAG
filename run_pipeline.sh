#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# Phase 9 pipeline automation
# ------------------------------------------------------------
# 1️⃣ Apply any pending text changes (if required)
#    Placeholder – you can add custom commands here.
#
# 2️⃣ Run the Map‑Reduce RAG pipeline for a test query (example).
#    Adjust the Python snippet to suit your actual entry point.
#
python - <<PY
import os, sys
# Ensure project root is in PYTHONPATH
ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.append(ROOT)

# Import the RAG generator and its dependencies
from services.rag_generation import RAGGenerator
from services.embedding_generator import EmbeddingGenerator
# NOTE: Adjust the DB connection & config as needed for your environment.
# Here we just instantiate a minimal generator for demonstration.

eg = EmbeddingGenerator()
# Assuming a SQLAlchemy engine `db` is available from a helper module
from services.db import get_db
db = get_db()
rag = RAGGenerator(embedding_generator=eg, db=db)

# Example query – replace with a real one if desired
query = "Summarize the main architectural patterns in the RAG documentation."
result = rag.generate_response(query=query)
print("RAG response generated.\n", result.response)
PY

# 3️⃣ Execute the benchmark runner (produces evaluation_results.json)
python benchmark_runner.py

# 4️⃣ Append the current metrics to a CSV history file for trend visualisation
python - <<PY
import json, csv, datetime, pathlib
base = pathlib.Path('evaluation_results.json')
if not base.is_file():
    raise FileNotFoundError('evaluation_results.json not found')
out = json.loads(base.read_text())
row = {
    'timestamp': datetime.datetime.utcnow().isoformat(),
    **{k: v for k, v in out.items() if isinstance(v, (int, float))}
}
csv_path = pathlib.Path('metrics_history.csv')
write_header = not csv_path.exists()
with csv_path.open('a', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=row.keys())
    if write_header:
        writer.writeheader()
    writer.writerow(row)
PY

# 5️⃣ Launch the Streamlit dashboard (runs until you stop it)
streamlit run dashboard.py
