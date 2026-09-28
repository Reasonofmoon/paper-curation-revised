# literacy 파일럿 — 다음 단계

2026-09-28 Anthropic 실행은 끝났다. 리뷰·카테고리 요약·타임라인 서술·Deep Research 답변은 `claude-sonnet-5`(요약만 Haiku)다. `GEMINI_API_KEY`가 없어 검색은 BM25다. 비용은 `usage.md` ($2.16). 아래 Gemini 절차는 임베딩을 붙일 때만 쓴다.

# literacy 파일럿 — GOOGLE_API_KEY 이후 실행 순서 (보류)

이번 브랜치(`pilot/literacy`)는 포크 `Reasonofmoon/paper-curation-revised`의 `master` `4536c043`에서 시작했다. 업스트림 `jehyunlee/paper-curation`은 fetch/merge/push/PR 하지 않았다. 배포, GitHub Pages, wrangler, Cloudflare, 메일은 사용하지 않는다.

`GOOGLE_API_KEY`가 없다. 아래 명령은 **아직 실행하지 않았다.** 키를 환경변수로만 넣고, `config.json`에는 적지 않는다. `config.json`은 gitignore 대상이다.

모델은 비용 대비 지시 이행이 되는 `gemini-2.5-flash` 하나다. 리뷰·타임라인 서술·카테고리 요약·Deep Research 답변이 이 모델을 쓴다. 임베딩만 `gemini-embedding-001` (768차원)이다. 이미지 타임라인(PaperBanana)은 돌리지 않는다.

## 0. 키와 provider

저장소 루트에서:

```bash
export GOOGLE_API_KEY="붙여넣기"
# 키를 파일에 쓰지 말 것. provider만 gemini로 맞춘다.
PYTHONUTF8=1 python3 - << 'PY'
import json
from pathlib import Path
p = Path("config.json")
cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
cfg.setdefault("zotero", {}).setdefault("collections", {})["literacy"] = "ReadMaster Literacy Pilot (CC BY)"
cfg.setdefault("llm", {})
cfg["llm"]["provider"] = "gemini"
cfg["llm"]["review_model"] = "gemini-2.5-flash"
cfg["llm"]["timeline_model"] = "gemini-2.5-flash"
cfg["llm"]["summary_model"] = "gemini-2.5-flash"
cfg.setdefault("review_profiles", {})["literacy"] = "education"
for secret in ("google_api_key", "gemini_api_key", "anthropic_api_key", "openai_api_key"):
    cfg.pop(secret, None)
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("config.json llm.provider=gemini (no API key stored)")
PY
```

PDF 22개는 git에 없다. 업로드 zip의 `pdfs/`를 예를 들어 `pilot_inputs/pdfs/`에 둔다. 논문 03(IJALEL, DOI `10.7575/aiac.ijalel.v.6n.3p.131`)은 랜딩 페이지에 PDF 링크가 없어 빠져 있다. PDF를 구하면 같은 폴더에 `03_....pdf`로 넣고 CSV `pdf_file`을 채운 뒤 1번을 다시 실행한다.

## 1. 리뷰 (Gemini, 교육 템플릿)

placeholder를 덮어쓴다. 키가 없으면 호출 전에 종료한다.

```bash
PYTHONUTF8=1 python3 pipeline/ingest_pdf_folder.py \
  --topic literacy \
  --csv pilot_artifacts/literacy/pilot-23-ccby.csv \
  --pdf-dir pilot_inputs/pdfs \
  --write-reviews
```

긴 메타분석은 앞부분과, 그 뒤에 나오는 효과크기 주변 창을 발췌한다. 발췌에 없는 수치는 `본문에서 확인되지 않음`이어야 한다.

## 2. 인덱스·분류 유지, 한글 카테고리 요약 (Gemini)

```bash
PYTHONUTF8=1 python3 pipeline/build_papers_index.py --topic literacy
PYTHONUTF8=1 python3 pipeline/classify_bib_subtopic.py --topic literacy
PYTHONUTF8=1 python3 pipeline/build_category_summaries.py --topic literacy
```

`classify_bib_subtopic.py`는 유료 호출이 아니다. 서지 subtopic이 primary다. 그 다음에 카테고리 요약을 Gemini로 다시 쓴다.

## 3. 타임라인 서술만 (Gemini, 이미지 생략)

```bash
PYTHONUTF8=1 python3 pipeline/generate_timelines.py --topic literacy --narrative-only
```

`--images-only`와 PaperBanana는 실행하지 않는다. `llm.provider=gemini`이면 서술 판정용 Anthropic vision 호출도 건너뛴다.

## 4. 리뷰 HTML, 밀집 검색 인덱스, 토픽 페이지

```bash
PYTHONUTF8=1 python3 pipeline/review_to_html.py --topic literacy --all
PYTHONUTF8=1 python3 pipeline/build_search_index.py --topic literacy --include-text yes
PYTHONUTF8=1 SKIP_ZOTERO_KEYS=1 python3 pipeline/build_topic_index.py literacy
```

`build_search_index.py`의 `--bm25-only`를 **빼야** `gemini-embedding-001`을 호출한다. `literacy/`는 `docs/.assetsignore`에 있어 로컬 전용이고, text.md 청크를 인덱스에 넣는다.

## 5. Deep Research 두 질문 (BM25 검색 + Gemini 답변)

`--retrieve-only`를 빼면 답변을 호출한다. 인용은 검색된 코퍼스 논문의 `[N]`만 허용한다.

```bash
PYTHONUTF8=1 python3 pipeline/answer_deep_research.py \
  --topic literacy --top-k 8 \
  --question "Does extensive reading improve English for Korean elementary students?" \
  --out pilot_artifacts/literacy/deep-research/q1-answer.md

PYTHONUTF8=1 python3 pipeline/answer_deep_research.py \
  --topic literacy --top-k 8 \
  --question "Should parents read English books with their kids at home?" \
  --out pilot_artifacts/literacy/deep-research/q2-answer.md
```

로컬에서 페이지를 보려면:

```bash
PYTHONUTF8=1 python3 pipeline/serve_local.py --port 8765 --topic literacy
```

`http://127.0.0.1:8765/literacy/`

## 하지 말 것

- `prepare_deploy.py`, `wrangler`, Cloudflare, `gh-pages`
- Anthropic 또는 OpenAI 키로 리뷰/타임라인/요약을 돌리는 것 (`llm.provider`를 `anthropic`으로 두지 말 것)
- 업스트림 `jehyunlee/paper-curation`으로 push 또는 PR
