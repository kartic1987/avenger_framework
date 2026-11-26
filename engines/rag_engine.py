import json, re
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from core.config import KNOWLEDGE_DIR
from core.document_loader import extract_text, SUPPORTED
from core.llm import LLMClient
from core.guardrails import validate_input

def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    words = text.split()
    if not words: return []
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start:start+size]))
        start += max(1, size-overlap)
    return chunks

class RAGEngine:
    def __init__(self, directory: Path = KNOWLEDGE_DIR, llm=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.llm = llm or LLMClient()

    def ingest(self, filename: str, data: bytes, progress_callback=None, page_range=None) -> int:
        text = extract_text(data, filename, progress_callback=progress_callback, page_range=page_range)
        if not text.strip():
            raise ValueError("No text could be extracted from the document.")
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(filename).name)
        (self.directory / safe_name).write_bytes(data)
        chunks = chunk_text(text)
        self._save_index_entry(safe_name, chunks)
        return len(chunks)

    def _index_path(self):
        return self.directory / "index.json"

    def _save_index_entry(self, name, chunks):
        path = self._index_path()
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        entries = [e for e in entries if e["source"] != name]
        entries.extend({"source": name, "chunk": c} for c in chunks)
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def retrieve(self, question: str, top_k: int = 4) -> list[dict]:
        ok, error = validate_input(question, 4000)
        if not ok: raise ValueError(error)
        path = self._index_path()
        if not path.exists(): return []
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not entries: return []
        corpus = [e["chunk"] for e in entries]
        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(corpus + [question])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = scores.argsort()[::-1][:top_k]
        return [{"source": entries[i]["source"], "text": entries[i]["chunk"],
                 "score": float(scores[i])} for i in ranked if scores[i] > 0]

    def ask(self, question: str, top_k: int = 4) -> dict:
        hits = self.retrieve(question, top_k)
        if not hits:
            return {"answer": "I could not find relevant information in the indexed knowledge sources.",
                    "sources": []}
        context = "\n\n".join(f"[Source: {h['source']}]\n{h['text']}" for h in hits)
        answer = self.llm.generate(
            f"Answer only using the context below. If the answer is not present, say so. "
            f"Cite source filenames in the answer.\n\nCONTEXT:\n{context}\n\nQUESTION:\n{question}",
            "You are a grounded knowledge assistant. Do not use outside knowledge."
        )
        return {"answer": answer, "sources": hits}
