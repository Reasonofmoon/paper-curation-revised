"""Answer a Deep Research question from the local search index.

Default retrieval is BM25 and does not call an embedding API. The answer
step uses Gemini only when ``GOOGLE_API_KEY`` is set and ``--retrieve-only``
is absent. With no key this script writes the retrieved passages and exits
2, unless ``--retrieve-only`` is set (exit 0, no answer invented).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from config_loader import get_google_key, get_llm_settings  # noqa: E402
from query_search_index import query_search_index  # noqa: E402


def number_papers(result: dict) -> list[dict]:
    """One citation number per corpus paper, in retrieval rank order."""
    papers = []
    seen = set()
    for hit in result.get("results") or []:
        slug = hit.get("slug") or ""
        if not slug or slug in seen:
            continue
        seen.add(slug)
        papers.append({
            "n": len(papers) + 1,
            "slug": slug,
            "title": hit.get("title") or slug,
            "year": hit.get("year") or "",
            "url": hit.get("url") or "",
            "section": hit.get("section") or "",
            "text": hit.get("text") or "",
            "bm25_score": hit.get("bm25_score"),
        })
    # Attach the best passage already stored; also keep extra passages in chunks.
    chunks_by_slug = {}
    for hit in result.get("results") or []:
        chunks_by_slug.setdefault(hit.get("slug"), []).append(hit)
    for paper in papers:
        paper["passages"] = chunks_by_slug.get(paper["slug"], [])
    return papers


def format_retrieval_markdown(question: str, result: dict, papers: list[dict],
                              answer: str | None, blocked: str | None) -> str:
    lines = [
        f"# {question}",
        "",
        f"- topic: `{result.get('topic')}`",
        f"- mode: `{result.get('mode')}`",
        f"- index model: `{result.get('model')}`",
        "",
        "## Retrieved passages",
        "",
    ]
    if not papers:
        lines.append("검색 결과가 없습니다.")
    for paper in papers:
        lines.append(f"### [{paper['n']}] {paper['title']}")
        lines.append("")
        lines.append(f"- slug: `{paper['slug']}`")
        if paper.get("year"):
            lines.append(f"- year: {paper['year']}")
        if paper.get("url"):
            lines.append(f"- url: {paper['url']}")
        lines.append("")
        for passage in paper.get("passages") or []:
            section = passage.get("section") or ""
            text = (passage.get("text") or "").strip()
            lines.append(f"**{section}**")
            lines.append("")
            lines.append(text)
            lines.append("")
    lines.append("## Answer")
    lines.append("")
    if answer:
        lines.append(answer.strip())
        lines.append("")
        lines.append("## Citation list")
        lines.append("")
        for paper in papers:
            lines.append(f"- [{paper['n']}] {paper['title']} (`{paper['slug']}`)")
    else:
        lines.append(blocked or "답변을 생성하지 않았다.")
        lines.append("")
        lines.append("인용 번호는 위 Retrieved passages의 논문 번호와 같다. 답변 문장은 쓰지 않았다.")
    lines.append("")
    return "\n".join(lines)


def _answer_prompt(question: str, papers: list[dict]) -> str:
    blocks = []
    for paper in papers:
        excerpt = (paper.get("text") or "")[:1200]
        blocks.append(f"[{paper['n']}] {paper['title']} ({paper.get('year') or '?'})\n{excerpt}")
    context = "\n\n".join(blocks)
    return (
        "너는 영어리딩 학원 학부모를 위한 연구 보조자다. 아래 검색 발췌만 근거로 한국어로 답하라.\n"
        "주장마다 발췌 번호 [N]을 붙여라. 목록에 없는 논문 번호는 쓰지 마라.\n"
        "발췌에 없는 효과크기나 표본 수는 추정하지 말고 '발췌에서 확인되지 않음'이라고 써라.\n"
        "합격, 입학, 점수, 등급을 보장하지 마라. 근거가 약하면 그렇게 말해라.\n\n"
        f"질문: {question}\n\n"
        f"발췌:\n{context}\n"
    )


def answer_with_gemini(question: str, papers: list[dict], model: str) -> str:
    from lib.gemini_llm import gemini_generate_text
    return gemini_generate_text(
        _answer_prompt(question, papers), model=model, max_output_tokens=1800, temperature=0.2,
    )


def run(topic: str, question: str, *, top_k: int, out: Path | None,
        retrieve_only: bool) -> int:
    result = query_search_index(topic, question, top_k=top_k, mode="bm25")
    papers = number_papers(result)
    answer = None
    blocked = None
    code = 0
    if retrieve_only:
        blocked = (
            "RETRIEVE-ONLY. Gemini 답변을 호출하지 않았다. "
            "GOOGLE_API_KEY를 설정한 뒤 `--retrieve-only` 없이 같은 명령을 실행하면 "
            "위 [N] 논문만 인용하는 답변이 생성된다."
        )
    elif not get_google_key():
        blocked = (
            "BLOCKED: GOOGLE_API_KEY가 없어 Gemini 답변을 호출하지 않았다. "
            "검색 구절만 저장했다."
        )
        code = 2
    else:
        settings = get_llm_settings()
        if settings["provider"] != "gemini":
            blocked = (
                "BLOCKED: llm.provider가 gemini가 아니다. Anthropic 답변은 호출하지 않았다."
            )
            code = 2
        else:
            answer = answer_with_gemini(question, papers, settings["review_model"])
    text = format_retrieval_markdown(question, result, papers, answer, blocked)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BM25 retrieval plus optional Gemini answer")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--retrieve-only", action="store_true",
                        help="Write passages and skip the answer call (exit 0).")
    args = parser.parse_args(argv)
    return run(
        args.topic, args.question, top_k=args.top_k, out=args.out,
        retrieve_only=args.retrieve_only,
    )


if __name__ == "__main__":
    from _env_guard import force_py312
    force_py312()
    raise SystemExit(main())
