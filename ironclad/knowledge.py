"""AST-aware BM25 + optional pgvector retrieval with reciprocal-rank fusion."""

import hashlib
import json
import math
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

from .repository import chunks
from .schema import Evidence
from .store import Store


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z_][a-z_0-9]*", text.lower())


def bm25(query: str, docs: list[Evidence]) -> list[int]:
    corpus = [tokens(d.path + " " + d.text) for d in docs]
    average = sum(map(len, corpus)) / max(len(corpus), 1)
    words = tokens(query)
    scores = []
    for index, document in enumerate(corpus):
        counts = Counter(document)
        score = 0.0
        for word in words:
            df = sum(word in other for other in corpus)
            idf = math.log(1 + (len(corpus) - df + 0.5) / (df + 0.5))
            tf = counts[word]
            score += (
                idf
                * tf
                * 2.5
                / (tf + 1.5 * (0.25 + 0.75 * len(document) / max(average, 1)))
            )
        names = set(
            re.findall(r"(?:def|class)\s+([a-z_][a-z_0-9]*)", docs[index].text.lower())
        )
        score += 3 * len(names.intersection(words))
        scores.append((score, index))
    return [i for _, i in sorted(scores, key=lambda pair: (-pair[0], pair[1]))]


def embed(text: str, store: Store, rid: str, budget: float, calls: int) -> list[float]:
    rate = float(os.environ["IRONCLAD_EMBEDDING_USD_PER_MILLION"])
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Embedding price must be positive")
    store.reserve(rid, (len(text.encode()) + 512) * rate / 1000000, budget, calls)
    request = urllib.request.Request(
        os.environ.get(
            "IRONCLAD_EMBEDDING_URL", "https://api.openai.com/v1/embeddings"
        ),
        data=json.dumps(
            {"model": os.environ["IRONCLAD_EMBEDDING_MODEL"], "input": text}
        ).encode(),
        headers={
            "Content-Type": "application/json",
        },
    )
    request.add_unredirected_header(
        "Authorization", "Bearer " + os.environ["IRONCLAD_EMBEDDING_KEY"]
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    vector = [float(n) for n in result["data"][0]["embedding"]]
    if not vector or not all(math.isfinite(n) for n in vector):
        raise ValueError("Invalid embedding")
    return vector


class VectorIndex:
    def __init__(self) -> None:
        import psycopg

        self.db = psycopg.connect(os.environ["IRONCLAD_DATABASE_URL"], autocommit=True)
        dims = int(os.environ.get("IRONCLAD_EMBEDDING_DIMENSIONS", "1536"))
        if not 1 <= dims <= 4096:
            raise ValueError("Invalid embedding dimensions")
        self.db.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.db.execute(
            f"CREATE TABLE IF NOT EXISTS documents(repo TEXT,path TEXT,start_line INTEGER,end_line INTEGER,chunk TEXT,digest TEXT,embedding vector({dims}),PRIMARY KEY(repo,path,start_line))"
        )

    def index(self, repo: Path, store: Store, budget: float = 1.0) -> int:
        docs = chunks(repo, 24000)
        rid = "index-" + __import__("uuid").uuid4().hex
        values = []
        for doc in docs:
            vector = embed(doc.text, store, rid, budget, 500)
            values.append(
                (
                    str(repo.resolve()),
                    doc.path,
                    doc.start_line,
                    doc.end_line,
                    doc.text,
                    hashlib.sha256(doc.text.encode()).hexdigest(),
                    json.dumps(vector),
                )
            )
        # Replace atomically; deleted source files disappear from retrieval.
        with self.db.transaction():
            self.db.execute(
                "DELETE FROM documents WHERE repo=%s", (str(repo.resolve()),)
            )
            for row in values:
                self.db.execute(
                    "INSERT INTO documents VALUES(%s,%s,%s,%s,%s,%s,%s::vector)", row
                )
        return len(values)

    def search(self, repo: Path, vector: list[float]) -> list[tuple[str, int, str]]:
        rows = self.db.execute(
            "SELECT path,start_line,digest FROM documents WHERE repo=%s ORDER BY embedding <=> %s::vector LIMIT 50",
            (str(repo.resolve()), json.dumps(vector)),
        ).fetchall()
        return [(str(p), int(line), str(digest)) for p, line, digest in rows]


def retrieve(
    repo: Path,
    query: str,
    limit: int,
    store: Store | None = None,
    rid: str = "knowledge",
    budget: float = 0.5,
    calls: int = 100,
) -> list[Evidence]:
    docs = chunks(repo, limit)
    if not docs:
        raise ValueError("No eligible Python function/class evidence")
    ranked = bm25(query, docs)
    scores = {index: 1 / (60 + rank) for rank, index in enumerate(ranked, 1)}
    if (
        os.environ.get("IRONCLAD_DATABASE_URL")
        and os.environ.get("IRONCLAD_EMBEDDING_KEY")
        and store
    ):
        vector = embed(query, store, rid, budget, calls)
        index = VectorIndex()
        try:
            semantic = index.search(repo, vector)
        finally:
            index.db.close()
        lookup = {
            (d.path, d.start_line, hashlib.sha256(d.text.encode()).hexdigest()): i
            for i, d in enumerate(docs)
        }
        for rank, key in enumerate(semantic, 1):
            if key in lookup:
                i = lookup[key]
                scores[i] = scores.get(i, 0) + 1 / (60 + rank)
    result = []
    used = 0
    for i in sorted(scores, key=lambda i: (-scores[i], i)):
        if used + len(docs[i].text) <= limit:
            result.append(docs[i])
            used += len(docs[i].text)
        if len(result) == 8:
            break
    return result
