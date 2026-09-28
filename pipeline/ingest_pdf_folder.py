"""Ingest a folder of PDFs plus a bibliographic CSV. No Zotero.

Writes ``docs/papers/{slug}/text.md``, ``meta.json``, and — unless
``--write-reviews`` is set — an education-template placeholder review that
does not invent effect sizes.

``--write-reviews`` calls Gemini or Anthropic according to ``llm.provider``.
It exits before any request when the selected provider has no API key.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from config_loader import PAPERS_DIR, get_google_key, get_llm_settings, get_review_profile  # noqa: E402
from lib.review_education import write_placeholder_review  # noqa: E402


def slug_for(row: dict) -> str:
    """{NNN}_{Title} using the pilot PDF prefix (01 → 001)."""
    raw = (row.get("pdf_file") or row.get("pilot_id") or row.get("id") or "").strip()
    prefix = raw.split("_", 1)[0]
    if prefix.isdigit():
        num = int(prefix)
    else:
        num = int(row.get("id") or 0)
    title = row.get("title") or "Untitled"
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:60].strip()
    safe = re.sub(r"\s+", "_", safe)
    return f"{num:03d}_{safe}"


def _authors(cell: str) -> list[str]:
    return [a.strip() for a in (cell or "").replace(";", ",").split(",") if a.strip()]


def load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def extract_pdf_text(pdf_path: Path, title: str, max_pages: int = 80) -> tuple[str, int, bool]:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    parts = [f"# {title}\n"]
    truncated = doc.page_count > max_pages
    for index, page in enumerate(doc):
        if index >= max_pages:
            break
        parts.append(f"\n\n## Page {index + 1}\n\n")
        parts.append(page.get_text() or "")
    if truncated:
        parts.append(f"\n\n[truncated after {max_pages} pages of {doc.page_count}]\n")
    return "".join(parts), doc.page_count, truncated


def _ssl_context():
    ctx = ssl.create_default_context()
    return ctx


def try_download_pdf(doi: str, dest: Path, timeout: int = 20) -> str:
    """One DOI landing-page attempt. Returns a short status string. Never raises."""
    if not doi:
        return "no doi"
    url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "paper-curation-literacy-pilot/1.0",
        "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = resp.read(8_000_000)
            final = resp.geturl()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as exc:
        return f"fetch failed: {type(exc).__name__}: {exc}"[:300]
    if data[:5] == b"%PDF-" or "pdf" in ctype.lower():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return f"downloaded {final}"
    html = data.decode("utf-8", errors="ignore")
    match = re.search(r'href="([^"]+\.pdf[^"]*)"', html, re.I)
    if not match:
        return f"no pdf link at {final}"[:300]
    pdf_url = urllib.request.urljoin(final, match.group(1))
    try:
        req2 = urllib.request.Request(pdf_url, headers={
            "User-Agent": "paper-curation-literacy-pilot/1.0",
            "Accept": "application/pdf",
        })
        with urllib.request.urlopen(req2, timeout=timeout, context=_ssl_context()) as resp:
            data = resp.read(8_000_000)
    except Exception as exc:
        return f"pdf link failed: {type(exc).__name__}: {exc}"[:300]
    if data[:5] != b"%PDF-":
        return "linked file was not a PDF"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"downloaded {pdf_url}"


def _opening_excerpt(text: str) -> str:
    body = re.sub(r"^#.*\n", "", text, count=1)
    body = re.sub(r"## Page \d+\s*", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:500]


def _is_real_review(path: Path) -> bool:
    if not path.exists():
        return False
    head = path.read_text(encoding="utf-8")[:800]
    return "review_status:" in head and "placeholder" not in head


def ingest(csv_path: Path, pdf_dir: Path, *, topic: str, write_reviews: bool,
           force: bool) -> dict:
    os.environ["PAPER_CURATION_TOPIC"] = topic
    rows = load_rows(csv_path)
    papers_root = Path(PAPERS_DIR)
    papers_root.mkdir(parents=True, exist_ok=True)
    report = {"ingested": [], "skipped": [], "reviews": []}

    if write_reviews:
        settings = get_llm_settings()
        if settings["provider"] == "gemini" and not get_google_key():
            raise SystemExit(
                "BLOCKED: llm.provider=gemini but GOOGLE_API_KEY is missing. "
                "No review call was made. Re-run without --write-reviews "
                "for placeholders, or set the key and run again."
            )
        if settings["provider"] != "gemini" and not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "BLOCKED: llm.provider is not gemini and ANTHROPIC_API_KEY is missing. "
                "Set llm.provider to gemini. No review call was made."
            )

    for row in rows:
        slug = slug_for(row)
        pdf_name = (row.get("pdf_file") or "").strip()
        pdf_path = pdf_dir / pdf_name if pdf_name else None
        if pdf_path is None or not pdf_path.is_file():
            dest = papers_root / "_missing_pdfs" / f"{slug}.pdf"
            status = try_download_pdf((row.get("doi") or "").strip(), dest)
            if status.startswith("downloaded") and dest.is_file():
                pdf_path = dest
            else:
                report["skipped"].append({
                    "slug": slug,
                    "title": row.get("title") or "",
                    "doi": row.get("doi") or "",
                    "reason": status if pdf_name == "" else f"pdf missing ({pdf_name}); {status}",
                })
                print(f"SKIP {slug}: {report['skipped'][-1]['reason']}")
                continue

        slug_dir = papers_root / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        text, pages, truncated = extract_pdf_text(pdf_path, row.get("title") or slug)
        (slug_dir / "text.md").write_text(text, encoding="utf-8")
        meta = {
            "topic": topic,
            "slug": slug,
            "subtopic": (row.get("subtopic") or "").strip(),
            "title": (row.get("title") or "").strip(),
            "authors": _authors(row.get("authors") or ""),
            "year": (row.get("year") or "").strip(),
            "venue": (row.get("venue") or "").strip(),
            "doi": (row.get("doi") or "").strip(),
            "url": (row.get("url") or "").strip(),
            "license": (row.get("license") or "CC BY").strip(),
            "pdf_file": pdf_name or pdf_path.name,
            "pilot_id": (row.get("pilot_id") or "").strip(),
            "pages": pages,
            "text_truncated": truncated,
            "review_profile": get_review_profile(topic),
        }
        (slug_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        review_path = slug_dir / "review.md"
        if write_reviews and (force or not _is_real_review(review_path)):
            from lib.review_education import write_education_review
            item = {
                "title": meta["title"],
                "authors": meta["authors"],
                "date": meta["year"],
                "DOI": meta["doi"],
                "url": meta["url"],
                "venue": meta["venue"],
                "license": meta["license"],
                "_subtopic": meta["subtopic"],
                "_review_profile": "education",
            }
            ok = write_education_review(item, str(slug_dir), [])
            report["reviews"].append({"slug": slug, "ok": bool(ok)})
            print(f"REVIEW {slug}: {'ok' if ok else 'FAILED'}")
        elif not _is_real_review(review_path) or force:
            write_placeholder_review(str(slug_dir), meta, _opening_excerpt(text))
            print(f"PLACEHOLDER {slug}")
        else:
            print(f"KEEP REVIEW {slug}")
        report["ingested"].append({
            "slug": slug,
            "title": meta["title"],
            "doi": meta["doi"],
            "pages": pages,
            "chars": len(text),
            "subtopic": meta["subtopic"],
        })
        print(f"TEXT {slug}: {pages} pages, {len(text)} chars")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest PDFs from a folder without Zotero")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--write-reviews", action="store_true",
                        help="Call the configured LLM. Refuses if the key is missing.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing non-placeholder review.")
    args = parser.parse_args(argv)
    report = ingest(
        args.csv, args.pdf_dir, topic=args.topic,
        write_reviews=args.write_reviews, force=args.force,
    )
    print(json.dumps({
        "ingested": len(report["ingested"]),
        "skipped": len(report["skipped"]),
    }, ensure_ascii=False))
    skipped_path = Path(PAPERS_DIR).parent / args.topic / "_ingest_skipped.json"
    skipped_path.parent.mkdir(parents=True, exist_ok=True)
    skipped_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"report: {skipped_path}")
    return 0


if __name__ == "__main__":
    from _env_guard import force_py312
    force_py312()
    raise SystemExit(main())
