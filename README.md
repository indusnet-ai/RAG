# 🚀 Production RAG Chatbot (FastAPI + React)

A production-grade Retrieval-Augmented Generation (RAG) system with multi-format document ingestion, hybrid search (BM25 + vector), BGE cross-encoder reranking, JWT authentication, multi-tenant isolation, and LangSmith observability.

---

## 🌟 Key Features

- **Multi-Format Ingestion**: PDF, DOCX, TXT, and Audio file support with OCR.
- **Hybrid Search**: Reciprocal Rank Fusion combining BM25 keyword matching (40%) and dense vector search (60%).
- **Cross-Encoder Reranking**: Re-orders retrieved chunks using `BGE-Reranker-v2-m3` for precision.
- **Observability**: End-to-end LLM call tracing via **LangSmith**.
- **Multi-Tenant JWT Auth**: Strict user-level and collection-level data isolation.
- **Dynamic Summarization**: Generic document-agnostic Map-Reduce summarization.
- **Citations & Sources**: Direct page-level and file-level citations.

---

## 🏗️ Architecture

```
User → React Frontend (localhost:5173)
         ↓ HTTP REST API / Streaming
       FastAPI Backend (localhost:8000)
         ↓
 ┌─────────────────┬──────────────────┬─────────────────┐
 │ Hybrid Search   │ Cross-Reranker   │ LangSmith Trace │
 │ BM25 + Vector   │ BGE-v2-m3        │ LLM Analytics   │
 └─────────────────┴──────────────────┴─────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Backend Setup

```bash
# Clone the repository
git clone https://github.com/indusnet-ai/RAG.git
cd RAG

# Create & activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `.env` and fill in your keys:
```env
OPENAI_API_KEY=sk-proj-...
DATABASE_URL=sqlite:///./rag_local.db
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=RAG-Chatbot
```

Start the FastAPI server:
```bash
python -m uvicorn main:app --port 8000 --reload
```

---

### 2. Frontend Setup

```bash
cd RAG-chatbot-frontend-main
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🔐 Credentials for Testing

- **Email**: `rag@gmail.com`
- **Password**: `Rag@54321`

---

## 📄 API Documentation

FastAPI Interactive Swagger Docs:
👉 `http://127.0.0.1:8000/docs`

Prometheus Metrics Endpoint:
👉 `http://127.0.0.1:8000/metrics`
