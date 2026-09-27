"""Classify a PDF-folder topic without a paid LLM and without SPECTER2.

Primary category comes from each paper's ``meta.json`` ``subtopic`` (the
pilot bibliography). A second category is added only when TF-IDF cosine to
another subtopic is clearly higher than the background. This is not HDBSCAN;
``classify_papers.py`` still needs a topic-model bundle built with SPECTER2.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from config_loader import PAPERS_DIR, get_papers_index_path, get_topic_dir  # noqa: E402

# Stable display order for the literacy academy corpus.
SUBTOPIC_LABELS = {
    "extensive-reading": "Extensive Reading",
    "vocabulary": "Vocabulary",
    "reading-comprehension": "Reading Comprehension",
    "phonics-decoding": "Phonics and Decoding",
    "reading-motivation": "Reading Motivation",
    "parent-home-literacy": "Home Literacy",
}

SUBTOPIC_BLURBS = {
    "Extensive Reading": (
        "이 묶음은 파일럿 서지표의 extensive reading 라벨이다. "
        "다독이 제2언어 학습에 미치는 영향을 다룬 논문이 여기로 배정된다. "
        "효과의 크기나 한국 초등학생에게의 적용은 개별 리뷰가 끝나기 전에는 단정하지 않는다. "
        "분류 자체는 모델 호출 없이 서지 라벨을 따른 것이다."
    ),
    "Vocabulary": (
        "이 묶음은 읽기 중의 어휘 학습, 주석, 형태소 인식을 다루는 서지 라벨이다. "
        "우연적 어휘 습득과 반복 읽기가 같은 칸에 모인다. "
        "특정 학습 방법의 우열은 이 설명에서 주장하지 않는다. "
        "Gemini 카테고리 요약 전이며, 학부모 상담 문장으로 쓰지 않는다. "
        "효과크기는 각 논문의 본문을 확인한 뒤에만 적는다."
    ),
    "Reading Comprehension": (
        "이 묶음은 독해 예측 요인, 듣고 읽기, 종이 대 화면 읽기처럼 이해 자체를 다룬다. "
        "단순 독해 관점과 한국 EFL 학습자 연구가 포함될 수 있다. "
        "어떤 읽기 방식이 더 낫다는 결론은 개별 논문의 효과크기를 확인한 뒤에만 말한다. "
        "지금은 파일럿 코퍼스를 나누기 위한 라벨이다."
    ),
    "Phonics and Decoding": (
        "이 묶음은 음운 인식, 파닉스, 읽기 부진 중재처럼 해독 지도를 다룬다. "
        "초등 단계의 소리-글자 대응과 치료 연구를 한 칸에 둔다. "
        "모든 아동에게 같은 중재가 필요하다는 뜻은 아니다. "
        "근거 강도와 대상 연령은 각 논문 리뷰에서 따로 확인한다. "
        "이 문단은 치료 효과를 보장하지 않는다."
    ),
    "Reading Motivation": (
        "이 묶음은 읽기 동기, 교사 지원, 흥미와 선택권을 다룬 서지 라벨이다. "
        "동기가 읽기 행동과 어떻게 연결되는지를 묻되, 동기 프로그램의 만능 효과를 말하지 않는다. "
        "한국 교실과 다른 나라 교실의 차이는 논문마다 다르다. "
        "이 문단은 클러스터 작명이 아니라 파일럿 라벨 설명이다."
    ),
    "Home Literacy": (
        "이 묶음은 가정 문해 환경, 함께 책 읽기, 부모 참여 프로그램을 다룬다. "
        "가정 환경은 상관일 수도 있고 프로그램 효과일 수도 있어 논문마다 설계가 다르다. "
        "집에서 영어책을 읽으면 성적이 오른다는 보장으로 읽으면 안 된다. "
        "학부모 시사점은 개별 리뷰의 근거 강도 라벨을 따른다."
    ),
}

_TOKEN_RE = re.compile(r"[a-z]{3,}")
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "its", "their", "they", "them", "than",
    "then", "into", "also", "can", "may", "our", "out", "over", "under", "between",
    "which", "what", "when", "where", "who", "how", "all", "any", "each", "more",
    "most", "such", "only", "other", "these", "those", "been", "being", "using",
    "used", "use", "study", "studies", "paper", "results", "result",
}


def label_for(subtopic: str) -> str:
    key = (subtopic or "").strip()
    if key in SUBTOPIC_LABELS:
        return SUBTOPIC_LABELS[key]
    if not key:
        return "Other"
    return key.replace("-", " ").title()


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP]


def tfidf_vectors(docs: list[str]) -> list[dict[str, float]]:
    tfs = [Counter(tokens(doc)) for doc in docs]
    df = Counter()
    for tf in tfs:
        df.update(tf.keys())
    n = max(len(docs), 1)
    vecs = []
    for tf in tfs:
        total = sum(tf.values()) or 1
        vec = {}
        for term, count in tf.items():
            idf = math.log((n + 1) / (df[term] + 1)) + 1.0
            vec[term] = (count / total) * idf
        vecs.append(vec)
    return vecs


def cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def assign_categories(records: list[dict], *, min_cosine: float = 0.18,
                      margin: float = 0.04) -> list[dict]:
    """records: {slug, subtopic, text}. Primary is the bibliography label."""
    vecs = tfidf_vectors([r.get("text") or "" for r in records])
    primaries = [label_for(r.get("subtopic") or "") for r in records]
    assignments = []
    for i, record in enumerate(records):
        by_cat = defaultdict(list)
        for j, other in enumerate(primaries):
            if i == j or other == primaries[i]:
                continue
            by_cat[other].append(cosine(vecs[i], vecs[j]))
        means = {cat: sum(vals) / len(vals) for cat, vals in by_cat.items() if vals}
        secondary = ""
        if means:
            best = max(means, key=means.get)
            background = sum(means.values()) / len(means)
            if means[best] >= min_cosine and means[best] >= background + margin:
                secondary = best
        all_cats = [primaries[i]]
        if secondary and secondary not in all_cats:
            all_cats.append(secondary)
        assignments.append({
            "slug": record["slug"],
            "primary_category": primaries[i],
            "all_categories": all_cats,
            "sub_category": primaries[i],
            "subtopic": record.get("subtopic") or "",
        })
    return assignments


def _load_records(topic: str) -> list[dict]:
    records = []
    root = Path(PAPERS_DIR)
    if not root.exists():
        return records
    for slug_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name[:1].isdigit()):
        meta_path = slug_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("topic") not in (None, "", topic):
            continue
        text = ""
        text_path = slug_dir / "text.md"
        if text_path.exists():
            text = text_path.read_text(encoding="utf-8", errors="ignore")[:12000]
        records.append({
            "slug": slug_dir.name,
            "subtopic": meta.get("subtopic") or "",
            "text": text,
            "title": meta.get("title") or "",
        })
    return records


def _summary_entry(name: str, slugs: list[str]) -> dict:
    return {
        "category": name,
        "description": "",
        "description_ko": SUBTOPIC_BLURBS.get(
            name,
            "이 묶음은 파일럿 서지 라벨이다. 효과나 정책을 이 문단에서 단정하지 않는다. "
            "Gemini 요약 전이며, 개별 논문의 설계와 한계를 리뷰에서 확인한다. "
            "합격이나 점수를 보장하는 표현은 쓰지 않는다.",
        ),
        "sub_themes": [],
        "sub_themes_ko": [],
        "papers": slugs,
    }


def apply_classification(topic: str) -> dict:
    records = _load_records(topic)
    if not records:
        raise SystemExit(f"no meta.json papers for topic {topic}")
    assignments = assign_categories(records)
    topic_dir = Path(get_topic_dir(topic))
    topic_dir.mkdir(parents=True, exist_ok=True)

    order = list(dict.fromkeys(
        list(SUBTOPIC_LABELS.values())
        + [a["primary_category"] for a in assignments]
    ))
    present = [name for name in order if any(a["primary_category"] == name for a in assignments)]
    cls = {
        "method": "bibliography-subtopic+tfidf-secondary",
        "llm": False,
        "categories": [{"name": name} for name in present],
        "assignments": [
            {k: a[k] for k in ("slug", "primary_category", "all_categories", "sub_category")}
            for a in assignments
        ],
    }
    (topic_dir / "_new_classification.json").write_text(
        json.dumps(cls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    by_cat = defaultdict(list)
    for a in assignments:
        by_cat[a["primary_category"]].append(a["slug"])
    summaries = [_summary_entry(name, by_cat[name]) for name in present]
    (topic_dir / "_category_summaries.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    narrative = {
        "executive_summary_ko": (
            "이 색인은 한국 영어리딩 학원 학부모를 위한 L2/EFL 읽기 연구 파일럿의 정적 초안이다. "
            "카드의 한 줄 요약은 Gemini 리뷰 이전 placeholder이며, 효과크기나 가정 실천 지침으로 읽으면 안 된다. "
            "분류는 서지표 subtopic이 일차이고, 본문 TF-IDF가 비슷할 때만 보조 범주를 하나 더한다. "
            "타임라인 서술과 임베딩 검색은 GOOGLE_API_KEY가 생긴 뒤에 생성한다. "
            "어떤 문장도 합격, 입학, 점수, 등급을 보장하지 않는다."
        ),
        "category_analyses": {
            name: {"description_ko": _summary_entry(name, by_cat[name])["description_ko"]}
            for name in present
        },
        "status": "placeholder-no-llm",
    }
    (topic_dir / "_timeline_narrative.json").write_text(
        json.dumps(narrative, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    index_path = Path(get_papers_index_path())
    papers = []
    if index_path.exists():
        papers = json.loads(index_path.read_text(encoding="utf-8"))
    by_slug = {a["slug"]: a for a in assignments}
    seen = set()
    for paper in papers:
        seen.add(paper.get("slug"))
        assignment = by_slug.get(paper.get("slug"))
        if not assignment:
            continue
        topics = list(paper.get("topics") or [])
        if topic not in topics:
            topics.append(topic)
        paper["topics"] = topics
        paper["primary_topic"] = paper.get("primary_topic") or topic
        classifications = paper.get("classifications") or {}
        classifications[topic] = {
            "primary_category": assignment["primary_category"],
            "all_categories": assignment["all_categories"],
            "sub_category": assignment["sub_category"],
        }
        paper["classifications"] = classifications
    if papers:
        index_path.write_text(
            json.dumps(papers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    print(f"classified {len(assignments)} papers into {len(present)} categories")
    for a in assignments:
        extra = ",".join(a["all_categories"][1:])
        print(f"  {a['slug']}: {a['primary_category']}" + (f" + {extra}" if extra else ""))
    return {"assignments": assignments, "categories": present, "index_slugs": len(seen)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bibliography subtopic classification (no LLM)")
    parser.add_argument("--topic", required=True)
    args = parser.parse_args(argv)
    apply_classification(args.topic)
    return 0


if __name__ == "__main__":
    from _env_guard import force_py312
    force_py312()
    raise SystemExit(main())
