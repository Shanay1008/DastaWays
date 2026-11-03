from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import re

from app.config import PROJECT_ROOT, get_settings

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
EVIDENCE_COLLECTION = "applicant_evidence"


@lru_cache(maxsize=1)
def embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    settings = get_settings()
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=8)
def vector_store(collection_name: str):
    from langchain_chroma import Chroma

    settings = get_settings()
    chroma_path = Path(settings.chroma_path)
    if not chroma_path.is_absolute():
        chroma_path = PROJECT_ROOT / chroma_path
    chroma_path.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings(),
        persist_directory=str(chroma_path),
        collection_metadata={"hnsw:space": "cosine"},
    )


def policy_collection_name(scheme_id: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", scheme_id)[:40]
    return f"policy_{safe_id}"


def split_policy_file(path: Path):
    """Return LangChain Documents, preserving PDF page or Markdown section provenance."""
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if path.suffix.lower() == ".pdf":
        import fitz

        pdf = fitz.open(path)
        pages = [(page.number + 1, page.get_text().strip()) for page in pdf]
        pdf.close()
        if not any(text for _, text in pages):
            raise ValueError(f"No extractable text in {path.name}; scanned PDFs need OCR, which is not enabled.")
        source_sections = [(text, {"page": page, "section": ""}) for page, text in pages if text]
    elif path.suffix.lower() in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
        pieces = re.split(r"(?m)^<!--\s*PAGE\s+(\d+)\s*-->\s*$", text)
        source_sections = []
        if len(pieces) > 1:
            for index in range(1, len(pieces), 2):
                page = int(pieces[index])
                page_text = pieces[index + 1].strip()
                if page_text:
                    source_sections.append((page_text, {"page": page, "section": ""}))
        else:
            headings = list(re.finditer(r"(?m)^#{1,3}\s+(.+)$", text))
            for index, heading in enumerate(headings):
                end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
                section_text = text[heading.end():end].strip()
                if section_text:
                    source_sections.append((f"{heading.group(1)}\n{section_text}", {"page": None, "section": heading.group(1).strip()}))
            if not headings and text.strip():
                source_sections = [(text.strip(), {"page": None, "section": ""})]
    else:
        raise ValueError("Policy source must be a PDF, Markdown, or text file")

    splitter = RecursiveCharacterTextSplitter(chunk_size=750, chunk_overlap=120)
    documents = []
    source_hash = sha256(path.read_bytes()).hexdigest()
    for text, citation in source_sections:
        chunks = splitter.split_text(text)
        for chunk_index, chunk in enumerate(chunks):
            doc_id = sha256(f"{source_hash}:{citation}:{chunk_index}:{chunk}".encode()).hexdigest()
            documents.append(Document(page_content=chunk, metadata={
                "filename": path.name,
                "source_kind": "synthetic_policy",
                "scheme_id": "demo-scholarship",
                "source_hash": source_hash,
                "page": citation["page"] or 0,
                "section": citation["section"] or "",
                "chunk_id": doc_id,
            }))
    return documents


def index_policy_file(path: Path, scheme_id: str = "demo-scholarship") -> int:
    docs = split_policy_file(path)
    for document in docs:
        document.metadata["scheme_id"] = scheme_id
    store = vector_store(policy_collection_name(scheme_id))
    # Replacing a scheme's policy is explicit and prevents obsolete passages surviving re-ingestion.
    store.delete(where={"scheme_id": scheme_id})
    store.add_documents(docs, ids=[doc.metadata["chunk_id"] for doc in docs])
    return len(docs)


def search_policy(query: str, scheme_id: str, top_k: int | None = None) -> dict:
    if not query.strip():
        raise ValueError("Question cannot be empty")
    store = vector_store(policy_collection_name(scheme_id))
    settings = get_settings()
    hits = store.similarity_search_with_score(query, k=top_k or settings.rag_top_k,
                                              filter={"scheme_id": scheme_id})
    sources = []
    for document, distance in hits:
        if distance > settings.rag_distance_threshold:
            continue
        metadata = document.metadata
        sources.append({
            "document": metadata.get("filename", "Unknown source"),
            "page": metadata.get("page") or None,
            "section": metadata.get("section") or None,
            "excerpt": document.page_content,
            "distance": round(float(distance), 4),
        })
    if not sources:
        return {"query": query, "insufficient_evidence": True, "sources": [],
                "message": "The indexed policy did not provide sufficiently relevant evidence for this question."}
    return {"query": query, "insufficient_evidence": False, "sources": sources,
            "message": "Retrieved policy passages are shown below. No generated answer is provided in this module."}


def index_applicant_document(session_id: str, document_id: str, filename: str, extracted_text: str) -> int:
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    pages = re.split(r"(?m)^\[Page\s+(\d+)\]\s*", extracted_text)
    page_texts = []
    if len(pages) > 1:
        for index in range(1, len(pages), 2):
            page_texts.append((int(pages[index]), pages[index + 1].strip()))
    elif extracted_text.strip():
        page_texts = [(1, extracted_text.strip())]
    splitter = RecursiveCharacterTextSplitter(chunk_size=750, chunk_overlap=120)
    store = vector_store(EVIDENCE_COLLECTION)
    docs = []
    for page, text in page_texts:
        for chunk_number, chunk in enumerate(splitter.split_text(text)):
            chunk_id = sha256(f"{session_id}:{document_id}:{page}:{chunk_number}:{chunk}".encode()).hexdigest()
            docs.append(Document(page_content=chunk, metadata={
                "source_kind": "applicant_evidence", "session_id": session_id,
                "document_id": document_id, "filename": filename,
                "page": page, "chunk_id": chunk_id,
            }))
    if docs:
        store.add_documents(docs, ids=[doc.metadata["chunk_id"] for doc in docs])
    return len(docs)


def delete_applicant_document(session_id: str, document_id: str) -> None:
    vector_store(EVIDENCE_COLLECTION).delete(where={"session_id": session_id, "document_id": document_id})


def delete_session_evidence(session_id: str) -> None:
    vector_store(EVIDENCE_COLLECTION).delete(where={"session_id": session_id})


def search_applicant_evidence(query: str, session_id: str, top_k: int | None = None) -> dict:
    if not query.strip():
        raise ValueError("Question cannot be empty")
    store = vector_store(EVIDENCE_COLLECTION)
    settings = get_settings()
    hits = store.similarity_search_with_score(query, k=top_k or settings.rag_top_k,
                                              filter={"session_id": session_id})
    sources = []
    for document, distance in hits:
        if distance > settings.rag_distance_threshold:
            continue
        metadata = document.metadata
        sources.append({
            "document": metadata.get("filename", "Uploaded PDF"),
            "page": metadata.get("page") or None,
            "section": None,
            "excerpt": document.page_content,
            "distance": round(float(distance), 4),
        })
    return {"query": query, "insufficient_evidence": not sources, "sources": sources,
            "message": "Retrieved applicant PDF passages are shown below." if sources else
            "No sufficiently relevant passage was found in this workspace's uploaded PDFs."}
