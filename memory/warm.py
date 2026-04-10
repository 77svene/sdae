"""
WarmMemory — semantic vector search via ChromaDB.
Uses PersistentClient so embeddings survive restarts.
Fallback to in-memory list if ChromaDB not installed.
Fixed: n_results=0 crash when collection is empty.
"""
from __future__ import annotations
from loguru import logger
from config import CFG


class WarmMemory:
    def __init__(self):
        self._collection = None
        self._fallback: list[dict] = []
        self._init_chromadb()

    def _init_chromadb(self):
        try:
            import chromadb
            chroma_path = str(CFG.data_dir / "chroma")
            # PersistentClient: survives restarts, embeddings on disk
            try:
                client = chromadb.PersistentClient(path=chroma_path)
            except AttributeError:
                # Older chromadb versions use Client(Settings(...))
                from chromadb.config import Settings
                client = chromadb.Client(Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=chroma_path,
                    anonymized_telemetry=False,
                ))
            self._collection = client.get_or_create_collection(
                "sdae_warm",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"WarmMemory: ChromaDB at {chroma_path} ({self._collection.count()} entries)")
        except ImportError:
            logger.warning("ChromaDB not installed — using in-memory fallback")
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e} — using fallback")

    def store(self, key: str, text: str, metadata: dict | None = None):
        if not text or not text.strip():
            return
        if self._collection is not None:
            try:
                self._collection.upsert(
                    ids=[key],
                    documents=[text[:2000]],  # ChromaDB has doc length limits
                    metadatas=[metadata or {}],
                )
                return
            except Exception as e:
                logger.warning(f"ChromaDB store failed: {e}")
        # Fallback
        self._fallback = [e for e in self._fallback if e["id"] != key]
        self._fallback.append({"id": key, "text": text, "meta": metadata or {}})

    def search(self, query: str, n: int = 5) -> list[dict]:
        if self._collection is not None:
            try:
                count = self._collection.count()
                if count == 0:
                    return []
                # n_results must be >= 1 and <= count
                safe_n = max(1, min(n, count))
                results = self._collection.query(query_texts=[query], n_results=safe_n)
                docs = results.get("documents", [[]])[0]
                ids = results.get("ids", [[]])[0]
                return [{"id": i, "text": d} for i, d in zip(ids, docs)]
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}")

        # Fallback: naive keyword match
        if not self._fallback:
            return []
        q = query.lower()
        scored = [(e, sum(w in e["text"].lower() for w in q.split())) for e in self._fallback]
        scored.sort(key=lambda x: -x[1])
        return [e for e, _ in scored[:n]]

    def count(self) -> int:
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._fallback)


WARM = WarmMemory()
