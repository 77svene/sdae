"""
WarmMemory — semantic vector search via ChromaDB.
Fallback to in-memory list if ChromaDB not installed.
"""
from __future__ import annotations
from loguru import logger


class WarmMemory:
    def __init__(self):
        self._collection = None
        self._fallback: list[dict] = []
        self._init_chromadb()

    def _init_chromadb(self):
        try:
            import chromadb
            client = chromadb.Client()
            self._collection = client.get_or_create_collection("sdae_warm")
            logger.info("WarmMemory: ChromaDB initialized")
        except ImportError:
            logger.warning("ChromaDB not installed — using in-memory fallback")
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e} — using fallback")

    def store(self, key: str, text: str, metadata: dict | None = None):
        if self._collection:
            try:
                self._collection.upsert(
                    ids=[key],
                    documents=[text],
                    metadatas=[metadata or {}],
                )
                return
            except Exception as e:
                logger.warning(f"ChromaDB store failed: {e}")
        # Fallback
        self._fallback = [e for e in self._fallback if e["id"] != key]
        self._fallback.append({"id": key, "text": text, "meta": metadata or {}})

    def search(self, query: str, n: int = 5) -> list[dict]:
        if self._collection:
            try:
                results = self._collection.query(query_texts=[query], n_results=min(n, self._collection.count() or 1))
                docs = results.get("documents", [[]])[0]
                ids = results.get("ids", [[]])[0]
                return [{"id": i, "text": d} for i, d in zip(ids, docs)]
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}")

        # Fallback: naive keyword match
        q = query.lower()
        scored = [(e, sum(w in e["text"].lower() for w in q.split())) for e in self._fallback]
        scored.sort(key=lambda x: -x[1])
        return [e for e, _ in scored[:n]]

    def count(self) -> int:
        if self._collection:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._fallback)


WARM = WarmMemory()
