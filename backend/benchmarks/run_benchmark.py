"""PDF regression + benchmark harness.

Generates representative documents (text, academic, financial tables,
multi-column, scanned, mixed, vector charts, corrupt, encrypted) and measures
the ingestion pipeline:

* parse duration (preflight + partition)
* page-level citation correctness (chunk.page matches the source page)
* text/table recall (known content appears in extracted chunks)
* scan success rate (scanned docs route to hi_res and produce output)
* retrieval quality (fake deterministic embeddings: token-overlap ranking)

Run:  python -m benchmarks.run_benchmark
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz

from app.processing import preflight, structure


@dataclass
class DocCase:
    name: str
    build: Any  # callable(Path) -> Path
    queries: dict[str, int] = field(default_factory=dict)  # query -> expected page
    expected_route: str = "fast"
    expected_text: list[str] = field(default_factory=list)


def _blank_image(tmp: Path) -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 400), False)
    pix.clear_with(190)
    p = tmp / "scan.png"
    pix.save(p)
    return p


def build_text_report(tmp: Path) -> Path:
    path = tmp / "text_report.pdf"
    doc = fitz.open()
    topics = [
        "Revenue grew steadily across all regions.",
        "Inflation remained moderate this quarter.",
        "Employment and exports both improved.",
    ]
    for i, topic in enumerate(topics):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"Quarterly report page {i + 1}. {topic} " * 12,
            fontsize=10,
        )
    doc.save(path)
    doc.close()
    return path


def build_academic(tmp: Path) -> Path:
    path = tmp / "academic.pdf"
    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 72),
        "Abstract: This paper studies gradient descent convergence. "
        "Empirical results on MNIST. " * 8,
        fontsize=10,
    )
    page2 = doc.new_page()
    page2.insert_text(
        (72, 72),
        "Methods: We use a transformer with 12 layers and Adam optimizer. " * 10,
        fontsize=10,
    )
    doc.save(path)
    doc.close()
    return path


def build_financial_tables(tmp: Path) -> Path:
    path = tmp / "financial.pdf"
    doc = fitz.open()
    page = doc.new_page()
    rows = [
        "| Region | Revenue | Growth |",
        "|--------|---------|--------|",
        "| Africa | 100 | 12% |",
        "| Europe | 200 | 8% |",
        "| Asia | 300 | 15% |",
        "| Americas | 150 | 5% |",
    ]
    page.insert_text((72, 72), "\n".join(rows), fontsize=10)
    doc.save(path)
    doc.close()
    return path


def build_multicolumn(tmp: Path) -> Path:
    path = tmp / "multicolumn.pdf"
    doc = fitz.open()
    page = doc.new_page()
    left = "Left column headline. " * 15
    right = "Right column headline. " * 15
    page.insert_textbox(fitz.Rect(40, 60, 280, 700), left, fontsize=9)
    page.insert_textbox(fitz.Rect(320, 60, 560, 700), right, fontsize=9)
    doc.save(path)
    doc.close()
    return path


def build_scanned(tmp: Path) -> Path:
    path = tmp / "scanned.pdf"
    img = _blank_image(tmp)
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(fitz.Rect(30, 30, 560, 750), filename=str(img))
    doc.save(path)
    doc.close()
    return path


def build_mixed(tmp: Path) -> Path:
    path = tmp / "mixed.pdf"
    img = _blank_image(tmp)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Cover page with an embedded photo. " * 8, fontsize=10)
    page.insert_image(fitz.Rect(100, 200, 500, 500), filename=str(img))
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Body text continues. " * 20, fontsize=10)
    doc.save(path)
    doc.close()
    return path


def build_vector_chart(tmp: Path) -> Path:
    path = tmp / "vector_chart.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Quarterly sales by region", fontsize=10)
    page.insert_text((72, 520), "Sales increased every quarter. " * 6, fontsize=10)
    for x0, y0 in ((50, 120), (200, 120), (350, 120), (50, 320), (200, 320)):
        page.draw_rect(
            fitz.Rect(x0, y0, x0 + 130, y0 + 160), color=(0, 0, 1), fill=(0, 0, 1)
        )
    doc.save(path)
    doc.close()
    return path


def build_corrupt(tmp: Path) -> Path:
    path = tmp / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.4 this is not parseable garbage")
    return path


def build_encrypted(tmp: Path) -> Path:
    path = tmp / "encrypted.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Secret. " * 20, fontsize=10)
    doc.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    doc.close()
    return path


CASES: list[DocCase] = [
    DocCase(
        "text_report",
        build_text_report,
        queries={"inflation": 2, "revenue": 1},
        expected_route="fast",
        expected_text=["revenue", "inflation"],
    ),
    DocCase(
        "academic",
        build_academic,
        queries={"gradient descent": 1, "transformer layers": 2},
        expected_route="fast",
        expected_text=["gradient", "descent", "optimizer"],
    ),
    DocCase(
        "financial_tables",
        build_financial_tables,
        queries={"Africa revenue": 1, "Asia growth": 1},
        expected_route="fast",
        expected_text=["Revenue", "Growth", "Asia"],
    ),
    DocCase(
        "multicolumn",
        build_multicolumn,
        expected_route="fast",
        expected_text=["headline"],
    ),
    DocCase(
        "scanned",
        build_scanned,
        expected_route="hi_res",
        expected_text=[],
    ),
    DocCase(
        "mixed",
        build_mixed,
        expected_route="hi_res",
        expected_text=["cover"],
    ),
    DocCase(
        "vector_chart",
        build_vector_chart,
        expected_route="fast",
        expected_text=["sales"],
    ),
    DocCase("corrupt", build_corrupt, expected_route="invalid"),
    DocCase("encrypted", build_encrypted, expected_route="encrypted"),
]


def _fake_embed(text: str) -> list[float]:
    """Deterministic token-overlap embedding: one dim per token, scaled."""
    import re

    tokens = sorted(set(re.findall(r"[a-z0-9]+", text.lower())))
    vec = [0.0] * 256
    for tok in tokens:
        vec[hash(tok) % 256] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


def run_case(case: DocCase, tmp: Path) -> dict[str, Any]:
    pdf = case.build(tmp)
    report: dict[str, Any] = {
        "name": case.name,
        "route": "",
        "route_ok": False,
        "parse_seconds": 0.0,
        "chunks": 0,
        "text_recall": 0.0,
        "missing_text": [],
        "citation_accuracy": 0.0,
        "citation_misses": [],
        "retrieval_top1_correct": 0,
        "retrieval_queries": 0,
        "pages_with_output": 0,
        "total_pages": 0,
    }
    try:
        pf = preflight.classify_pdf(pdf)
    except preflight.PreflightError as exc:
        report["route"] = exc.status
        report["route_ok"] = exc.status == case.expected_route
        return report

    report["route"] = pf.route
    report["route_ok"] = pf.route == case.expected_route
    report["total_pages"] = pf.num_pages

    t0 = time.perf_counter()
    root, _elements, _num_pages, _warnings = structure.partition(pdf, preflight=pf)
    report["parse_seconds"] = round(time.perf_counter() - t0, 3)

    from app.processing import chunking

    chunks = chunking.build_chunks(root, f"bench-{case.name}")
    report["chunks"] = len(chunks)
    report["pages_with_output"] = len(
        {c.page for c in chunks if c.display_text and c.display_text.strip()}
    )

    blob = " ".join(c.display_text for c in chunks).lower()
    missing = [t for t in case.expected_text if t.lower() not in blob]
    report["missing_text"] = missing
    report["text_recall"] = round(
        (len(case.expected_text) - len(missing)) / max(1, len(case.expected_text)), 2
    )

    # Citation accuracy: each expected query maps to a source page; the chunk
    # containing the query's key terms must carry that page.
    citation_misses: list[str] = []
    cited = 0
    for query, expected_page in case.queries.items():
        key = query.split()[0].lower()
        hits = [c for c in chunks if key in (c.display_text or "").lower()]
        if hits and all(c.page == expected_page for c in hits):
            cited += 1
        else:
            citation_misses.append(f"{query}->p{expected_page}")
    report["citation_misses"] = citation_misses
    report["citation_accuracy"] = round(cited / max(1, len(case.queries)), 2)

    # Retrieval quality with deterministic fake embeddings.
    top1_ok = 0
    for query, expected_page in case.queries.items():
        qv = _fake_embed(query)
        ranked = sorted(
            ((_similarity(qv, _fake_embed(c.text_for_embedding)), c) for c in chunks),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if ranked and ranked[0][1].page == expected_page:
            top1_ok += 1
    report["retrieval_queries"] = len(case.queries)
    report["retrieval_top1_correct"] = top1_ok
    return report


def main() -> None:
    import tempfile

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="chatpdf-bench-") as tmp:
        root_tmp = Path(tmp)
        for case in CASES:
            try:
                results.append(run_case(case, root_tmp))
            except Exception as exc:  # pragma: no cover
                results.append(
                    {
                        "name": case.name,
                        "error": f"{type(exc).__name__}: {exc}",
                        "route_ok": False,
                    }
                )

    print(json.dumps(results, indent=2))

    routes_ok = sum(1 for r in results if r.get("route_ok"))
    parse_times = [r["parse_seconds"] for r in results if r.get("parse_seconds")]
    recall = [r["text_recall"] for r in results if "text_recall" in r]
    citations = [r["citation_accuracy"] for r in results if "citation_accuracy" in r]
    print(
        f"\nroute_ok: {routes_ok}/{len(results)}\n"
        f"median parse: {statistics.median(parse_times) if parse_times else 0:.3f}s\n"
        f"mean text_recall: {statistics.fmean(recall) if recall else 0:.2f}\n"
        f"mean citation_accuracy: {statistics.fmean(citations) if citations else 0:.2f}"
    )


if __name__ == "__main__":
    main()
