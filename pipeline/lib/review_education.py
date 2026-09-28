"""Korean education-research review profile for the literacy pilot.

Sections: one-line summary, research question, participants, design,
effect size, limitations, parent implications (evidence-strength label,
no grade/admission guarantees), and evidence quotes.

Numbers that are not in the PDF must be written as "본문에서 확인되지 않음".
"""
from __future__ import annotations

import json
import os
import re

EDUCATION_SCHEMA_VERSION = "education-v1"

EDUCATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "essence": {
            "type": "string",
            "description": "한 줄 요약 1–2문장. PDF에 없는 수치는 쓰지 말 것.",
        },
        "motivation": {
            "type": "string",
            "description": "연구 질문과 배경. 본문에 없으면 본문에서 확인되지 않음.",
        },
        "participants": {
            "type": "string",
            "description": "국가/맥락(EFL·ESL·L1), 연령·학년, 표본 수, 숙달도. 메타분석이면 포함 연구 수·총 표본. 없으면 본문에서 확인되지 않음.",
        },
        "design": {
            "type": "string",
            "description": "RCT/준실험/상관/사례/메타분석/체계적 문헌고찰, 중재 내용·기간·빈도, 측정 도구.",
        },
        "findings": {
            "type": "string",
            "description": "효과크기(d, g, r)와 신뢰구간을 원문 수치 그대로. 추정 금지. 없으면 본문에서 확인되지 않음.",
        },
        "limitations": {
            "type": "string",
            "description": "저자가 밝힌 한계와 한국 EFL 아동에게의 일반화 한계.",
        },
        "parent_implications": {
            "type": "string",
            "description": "학부모 시사점 2–4개 불릿. 각 불릿 끝에 '근거 강도: 강' 또는 '중' 또는 '약'. 합격·입학·점수·등급 보장 금지.",
        },
        "evidence_quotes": {
            "type": "string",
            "description": "위 주장에 대응하는 원문 짧은 인용과 쪽 또는 섹션. 쪽을 모르면 쪽 미확인.",
        },
    },
    "required": [
        "essence", "motivation", "participants", "design", "findings",
        "limitations", "parent_implications", "evidence_quotes",
    ],
}

_GUARANTEE_RE = re.compile(
    r"(합격|입학|등급|점수|성적).{0,16}보장|보장.{0,16}(합격|입학|등급|점수|성적)"
)

EDUCATION_TEMPLATE = """# {title}

> **저자**: {authors} | **날짜**: {date} | {ref_label}: {ref_link}
> **리뷰 상태**: {status} | **라이선스**: {license} | **주제**: {subtopic}

---

## Essence

{essence}

## 연구 질문과 배경

{motivation}

## 참여자

{participants}

## 연구 설계

{design}

## 주요 결과와 효과크기

{findings}

## 한계

{limitations}

## 학부모 시사점

{parent_implications}

## 근거 인용

{evidence_quotes}
"""

NOT_IN_TEXT = "본문에서 확인되지 않음"


def scrub_guarantees(text: str) -> str:
    """Drop sentences that promise grades, admission, or scores."""
    if not text:
        return text
    kept = []
    for part in re.split(r"(?<=[.!?。])\s+|\n+", text):
        if _GUARANTEE_RE.search(part):
            continue
        kept.append(part)
    out = "\n".join(p for p in kept if p.strip()).strip()
    return out or "과장·보장 표현은 템플릿에서 제거했습니다. 근거 강도: 약"


def ensure_evidence_label(text: str) -> str:
    if "근거 강도" in (text or ""):
        return text
    base = (text or "").rstrip()
    return (base + "\n\n근거 강도: 약").strip()


def _yaml_quote(value) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def render_frontmatter(meta: dict, essence: str, status: str) -> str:
    authors = meta.get("authors") or []
    author_lines = "\n".join(f"  - {_yaml_quote(a)}" for a in authors) or "  []"
    if not authors:
        author_block = "authors: []"
    else:
        author_block = "authors:\n" + author_lines
    return (
        "---\n"
        "schema_version: v1\n"
        f"title: {_yaml_quote(meta.get('title') or '')}\n"
        f"{author_block}\n"
        f"date: {_yaml_quote(meta.get('year') or meta.get('date') or '')}\n"
        f"doi: {_yaml_quote(meta.get('doi') or '')}\n"
        f"license: {_yaml_quote(meta.get('license') or 'CC BY')}\n"
        f"journal: {_yaml_quote(meta.get('venue') or '')}\n"
        f"essence: {_yaml_quote((essence or '')[:500])}\n"
        f"review_status: {_yaml_quote(status)}\n"
        "scores:\n"
        "  overall: 0\n"
        "---\n\n"
    )


def render_education_markdown(meta: dict, fields: dict, *, status: str) -> str:
    doi = (meta.get("doi") or "").strip()
    url = (meta.get("url") or "").strip()
    if doi:
        ref_label, ref_link = "**DOI**", f"[{doi}](https://doi.org/{doi})"
    elif url:
        ref_label, ref_link = "**URL**", f"[{url}]({url})"
    else:
        ref_label, ref_link = "**DOI**", "N/A"
    authors = ", ".join(a for a in (meta.get("authors") or []) if a) or "미상"
    body = EDUCATION_TEMPLATE.format(
        title=meta.get("title") or "Untitled",
        authors=authors,
        date=meta.get("year") or meta.get("date") or "",
        ref_label=ref_label,
        ref_link=ref_link,
        status=status,
        license=meta.get("license") or "CC BY",
        subtopic=meta.get("subtopic") or "",
        essence=fields.get("essence") or NOT_IN_TEXT,
        motivation=fields.get("motivation") or NOT_IN_TEXT,
        participants=fields.get("participants") or NOT_IN_TEXT,
        design=fields.get("design") or NOT_IN_TEXT,
        findings=fields.get("findings") or NOT_IN_TEXT,
        limitations=fields.get("limitations") or NOT_IN_TEXT,
        parent_implications=ensure_evidence_label(
            scrub_guarantees(fields.get("parent_implications") or "")
        ),
        evidence_quotes=fields.get("evidence_quotes") or NOT_IN_TEXT,
    )
    essence = fields.get("essence") or NOT_IN_TEXT
    return render_frontmatter(meta, essence, status) + body.strip() + "\n"


def placeholder_fields(meta: dict, opening_excerpt: str) -> dict:
    """Bibliographic placeholder. Does not interpret effect sizes."""
    excerpt = (opening_excerpt or "").strip()
    excerpt = re.sub(r"\s+", " ", excerpt)[:500]
    if excerpt:
        quote = (
            "아래는 PDF에서 그대로 잘라 낸 앞부분이다. 해석·효과크기 환산은 하지 않았다.\n\n"
            f"> {excerpt}"
        )
    else:
        quote = NOT_IN_TEXT
    return {
        "essence": (
            "[PLACEHOLDER] GOOGLE_API_KEY 가 없어 Gemini 리뷰를 생성하지 않았다. "
            "이 문장은 서지 정보만 담고, 연구의 효과를 요약하지 않는다."
        ),
        "motivation": NOT_IN_TEXT + " (리뷰 미생성).",
        "participants": NOT_IN_TEXT + " (리뷰 미생성).",
        "design": NOT_IN_TEXT + " (리뷰 미생성).",
        "findings": NOT_IN_TEXT + " 효과크기는 placeholder 리뷰에서 적지 않는다.",
        "limitations": NOT_IN_TEXT + " (리뷰 미생성).",
        "parent_implications": (
            "- 리뷰가 생성되기 전에는 가정에서의 실천을 권하지 않는다. "
            "합격·입학·점수·등급을 보장하지 않는다. 근거 강도: 판정 불가"
        ),
        "evidence_quotes": quote,
    }


_EFFECT_RE = re.compile(
    r"(?i)(cohen|hedges|effect size|\bd\s*=|\bg\s*=|95%\s*CI|confidence interval)"
)


def excerpt_for_review(text: str, head: int = 14000, window: int = 3500, extra: int = 3) -> str:
    """Opening pages plus a few later windows that mention effect sizes.

    A flat 12k-character cut drops the results of long meta-analyses. This
    stays inside one Gemini call and does not invent numbers.
    """
    body = text or ""
    head_text = body[:head]
    rest = body[head:]
    extras = []
    for match in _EFFECT_RE.finditer(rest):
        start = max(0, match.start() - 500)
        end = min(len(rest), match.end() + window)
        extras.append(rest[start:end])
        if len(extras) >= extra:
            break
    if not extras:
        return head_text
    return head_text + "\n\n---\n\n" + "\n\n---\n\n".join(extras)


def education_prompt(meta: dict, paper_text: str) -> str:
    authors = ", ".join(meta.get("authors") or [])
    excerpt = excerpt_for_review(paper_text)
    return (
        "당신은 L2/EFL 읽기 논문을 한국 영어리딩 학원 학부모를 위해 구조화하는 연구 보조자이다.\n"
        "아래 PDF 발췌만 근거로 JSON 필드를 채워라. 발췌에 없는 수치·표본·효과크기는 "
        "절대 추정하지 말고 그 항목에 '본문에서 확인되지 않음'이라고 써라.\n"
        "narrative 는 한국어. 기술 용어·효과크기 기호(d, g, r, CI)는 원문 그대로 둬라.\n"
        "학부모 시사점은 2–4개 불릿이고, 각 불릿은 '근거 강도: 강' 또는 '중' 또는 '약'으로 끝난다.\n"
        "합격, 입학, 점수, 등급, 성적을 보장하는 문장은 금지한다.\n"
        "한국 EFL 아동에게 일반화하기 어렵다면 한계에 그 점을 적어라.\n\n"
        f"제목: {meta.get('title') or ''}\n"
        f"저자: {authors}\n"
        f"연도: {meta.get('year') or ''}\n"
        f"학술지: {meta.get('venue') or ''}\n"
        f"DOI: {meta.get('doi') or ''}\n"
        f"파일럿 하위주제(서지 라벨, 결과로 단정하지 말 것): {meta.get('subtopic') or ''}\n\n"
        f"본문 발췌:\n{excerpt}\n"
    )


_PARAM_RE = re.compile(
    r'<parameter name="([a-z_]+)">(.*?)</(?:parameter|\1)>',
    re.S,
)


def _unwrap_embedded_parameters(data: dict) -> dict:
    """Some tool calls dump every field into ``essence`` as XML. Split them back."""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    essence = out.get("essence") if isinstance(out.get("essence"), str) else ""
    if "<parameter" not in essence and "</essence>" not in essence:
        return out
    head, sep, _rest = essence.partition("</essence>")
    if sep:
        out["essence"] = head.strip()
    for name, value in _PARAM_RE.findall(essence):
        if name not in EDUCATION_JSON_SCHEMA["required"] or name == "essence":
            continue
        current = out.get(name)
        if not isinstance(current, str) or not current.strip() or current.strip() == NOT_IN_TEXT:
            out[name] = value.strip()
    return out


def normalize_education_fields(data: dict) -> dict:
    data = _unwrap_embedded_parameters(data)
    out = {}
    for key in EDUCATION_JSON_SCHEMA["required"]:
        value = data.get(key) if isinstance(data, dict) else None
        if not isinstance(value, str) or not value.strip():
            value = NOT_IN_TEXT
        value = value.replace("</invoke>", "").strip()
        out[key] = value.strip()
    out["parent_implications"] = ensure_evidence_label(
        scrub_guarantees(out["parent_implications"])
    )
    return out


def write_education_review(item: dict, slug_dir: str, figures=None) -> bool:
    """Call the configured provider and write review.md. No call if the key is missing."""
    del figures  # education template does not embed figures in v1
    text_path = os.path.join(slug_dir, "text.md")
    if not os.path.exists(text_path):
        return False
    with open(text_path, "r", encoding="utf-8") as handle:
        paper_text = handle.read()

    meta = meta_from_item(item)
    from config_loader import get_llm_settings
    settings = get_llm_settings()
    prompt = education_prompt(meta, paper_text)
    if settings["provider"] == "gemini":
        model = settings["review_model"]

        def _make_call():
            from lib.gemini_llm import gemini_generate_json
            return gemini_generate_json(
                prompt, EDUCATION_JSON_SCHEMA, model=model, max_output_tokens=4000,
            )
    else:
        model = os.environ.get("WRITE_REVIEW_MODEL") or settings["review_model"] or "claude-sonnet-5"
        if "opus" in model.lower():
            model = "claude-sonnet-5"

        def _make_call():
            from anthropic import Anthropic
            from lib.usage_log import abort_if_over, projected_usd, record
            client = Anthropic(timeout=180.0, max_retries=4)
            tool = {
                "name": "emit_review",
                "description": "Emit the education-research review fields.",
                "input_schema": EDUCATION_JSON_SCHEMA,
            }
            max_tokens = 4000
            est_in = max(1, len(prompt) // 2)
            abort_if_over(
                3.0, projected_usd(model, est_in, max_tokens), step="review",
            )
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=[tool],
                tool_choice={"type": "tool", "name": "emit_review"},
                messages=[{"role": "user", "content": prompt}],
            )
            record(
                "review", model, getattr(response, "usage", None),
                note=os.path.basename(slug_dir.rstrip("/\\")),
            )
            for block in response.content:
                if getattr(block, "type", None) == "tool_use" \
                        and getattr(block, "name", None) == "emit_review":
                    return dict(block.input)
            raise RuntimeError("emit_review tool was not invoked")

    from api._llm import cached_call, paper_cache_dir
    slug = os.path.basename(slug_dir.rstrip("/\\"))
    data = cached_call(
        paper_cache_dir(slug), prompt, model, _make_call,
        schema_version=EDUCATION_SCHEMA_VERSION,
    )
    fields = normalize_education_fields(data)
    status = f"gemini:{model}" if settings["provider"] == "gemini" else f"anthropic:{model}"
    review = render_education_markdown(meta, fields, status=status)
    with open(os.path.join(slug_dir, "review.md"), "w", encoding="utf-8") as handle:
        handle.write(review)
    return True


def meta_from_item(item: dict) -> dict:
    creators = item.get("creators") or []
    if creators and isinstance(creators[0], dict):
        authors = [
            f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
            for c in creators
        ]
        authors = [a for a in authors if a]
    else:
        authors = list(item.get("authors") or [])
    return {
        "title": item.get("title") or "",
        "authors": authors,
        "year": item.get("date") or item.get("year") or "",
        "doi": item.get("DOI") or item.get("doi") or "",
        "url": item.get("url") or "",
        "venue": item.get("venue") or item.get("publicationTitle") or "",
        "license": item.get("license") or "CC BY",
        "subtopic": item.get("subtopic") or item.get("_subtopic") or "",
    }


def write_placeholder_review(slug_dir: str, meta: dict, opening_excerpt: str) -> str:
    fields = placeholder_fields(meta, opening_excerpt)
    text = render_education_markdown(meta, fields, status="placeholder")
    path = os.path.join(slug_dir, "review.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
