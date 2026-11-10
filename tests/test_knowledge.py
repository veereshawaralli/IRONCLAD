from pathlib import Path

from ironclad.knowledge import bm25, retrieve
from ironclad.schema import Evidence


def test_bm25_relevant_first():
    docs = [
        Evidence(path="one.py", start_line=1, end_line=1, text="def billing(): pass"),
        Evidence(
            path="two.py",
            start_line=1,
            end_line=1,
            text="def average(values): return sum(values)",
        ),
    ]
    assert bm25("average values", docs)[0] == 1


def test_ast_bm25_retrieval():
    result = retrieve(Path("examples/broken_repo"), "average", 24000)
    assert result[0].path == "stats.py"
