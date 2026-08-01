"""
Streamlit UI — ask natural-language questions against the RAG corpora.

Runs the retrieval pipeline in-process (no API server needed):
    corpus picker → question → retrieve → rerank → grounded answer + sources

Launch locally:
    pip install -r requirements-ui.txt
    streamlit run ui/streamlit_app.py

Reads the same env vars as the app (AZURE_SEARCH_ENDPOINT, AI_FOUNDRY_ENDPOINT, …).
With none set it falls back to local ChromaDB + an extractive (no-LLM) answer.
"""
import os
import sys

import streamlit as st

# Allow `streamlit run ui/streamlit_app.py` from the project root to import src.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import config  # noqa: E402
from src.pipeline import rag_query  # noqa: E402

st.set_page_config(page_title="KYC/AML — Ask the KB", page_icon="🔎", layout="wide")

st.title("🔎 Ask the Knowledge Base")
st.caption("Natural-language RAG over the regulatory KB and the OCR'd travel brochures.")

with st.sidebar:
    st.header("Corpus")
    corpora = rag_query.available_corpora()
    labels = {c["key"]: c["label"] for c in corpora}
    corpus_key = st.radio(
        "Search over", options=list(labels), format_func=lambda k: labels[k],
    )

    st.divider()
    st.header("Retrieval")
    top_k_retrieve = st.slider("Retrieve (k)", 1, 20, config.top_k_retrieve)
    top_k_rerank = st.slider("Rerank to", 1, 10, config.top_k_rerank)

    st.divider()
    st.caption(f"Vector backend: **{rag_query.get_corpus(corpus_key).store.backend}**")
    st.caption(f"LLM reasoning: **{'on' if config.use_foundry_agents else 'off (extractive)'}**")

    if corpus_key == "travel":
        if st.button("Index travel brochures"):
            with st.spinner("Ingesting OCR'd travel extractions…"):
                n = rag_query.ingest_travel_corpus()
            st.success(f"Travel corpus ready ({n} docs).") if n else st.warning(
                "No extractions found under data/extracted/."
            )

question = st.text_input(
    "Your question",
    placeholder={
        "regulatory": "e.g. What triggers enhanced due diligence for a PEP?",
        "travel": "e.g. Which hotels does Margie's Travel offer in Dubai?",
    }.get(corpus_key, "Ask a question…"),
)

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Retrieving and reasoning…"):
        result = rag_query.answer_query(
            question, corpus_key,
            top_k_retrieve=top_k_retrieve, top_k_rerank=top_k_rerank,
        )

    grounded = result["grounded"]
    src = result["assessment_source"]
    badge = "✅ grounded" if grounded else "⚠️ not grounded in sources"
    st.subheader("Answer")
    st.markdown(result["answer"] or "_(no answer)_")
    st.caption(f"{badge} · answer via **{src}** · cited sources: {result['citations'] or '—'}")

    st.subheader(f"Sources ({len(result['sources'])})")
    for s in result["sources"]:
        ref = f" — {s['reference']}" if s["reference"] else ""
        with st.expander(f"[{s['n']}] score {s['score']}{ref}"):
            if s["doc_type"]:
                st.caption(f"doc_type: {s['doc_type']}")
            st.write(s["text"])
