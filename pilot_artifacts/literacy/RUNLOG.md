# RUNLOG — literacy 내부 파일럿

## 기준

- 브랜치: `pilot/literacy`
- 베이스: 포크 `Reasonofmoon/paper-curation-revised` `master` `4536c043` (`fix: run real citedby deeper research`)
- 업스트림 스냅샷은 쓰지 않았다. 이 포크에 리뷰 작성(`run_update_force.write_review`), 검색 인덱스, 토픽 HTML이 이미 있어서 파이프라인을 돌릴 수 있었다.
- 업스트림 `jehyunlee/paper-curation`에는 push/PR/배포하지 않았다.
- `wrangler`, Cloudflare, GitHub Pages, 메일, Zotero API는 호출하지 않았다.
- LLM 호출 0회. `GOOGLE_API_KEY` 없음.

## 입력

- CSV 23행, PDF 22개 (CC BY). 업로드 zip.
- 빠진 1편: id 3, *Comparison of the Impact of Extensive and Intensive Reading…*, DOI `10.7575/aiac.ijalel.v.6n.3p.131`.
- DOI 랜딩을 한 번 열었다. 최종 URL `https://journals.aiac.org.au/index.php/IJALEL/article/view/3048` 에 PDF 링크가 없어 skip. 리뷰를 만들지 않았다.

## 실행한 명령 (종료 코드 0)

```bash
PYTHONUTF8=1 python3 pipeline/ingest_pdf_folder.py \
  --topic literacy \
  --csv /tmp/pilot-inputs/pilot-23-ccby.csv \
  --pdf-dir /tmp/pilot-inputs/pdfs

PYTHONUTF8=1 python3 pipeline/build_papers_index.py --topic literacy
PYTHONUTF8=1 python3 pipeline/classify_bib_subtopic.py --topic literacy
PYTHONUTF8=1 python3 pipeline/review_to_html.py --topic literacy --all
PYTHONUTF8=1 python3 pipeline/build_search_index.py \
  --topic literacy --bm25-only --include-text yes
SKIP_ZOTERO_KEYS=1 PYTHONUTF8=1 python3 pipeline/build_topic_index.py literacy

PYTHONUTF8=1 python3 pipeline/answer_deep_research.py --topic literacy \
  --retrieve-only --top-k 8 \
  --question "Does extensive reading improve English for Korean elementary students?" \
  --out pilot_artifacts/literacy/deep-research/q1-extensive-reading-korean-elementary.md

PYTHONUTF8=1 python3 pipeline/answer_deep_research.py --topic literacy \
  --retrieve-only --top-k 8 \
  --question "Should parents read English books with their kids at home?" \
  --out pilot_artifacts/literacy/deep-research/q2-parents-read-at-home.md

PYTHONUTF8=1 python3 -m unittest pipeline.tests.test_literacy_pilot
PYTHONUTF8=1 python3 pipeline/serve_local.py --port 8765 --topic literacy
```

ingest는 페이지 상한을 80으로 올린 뒤 한 번 더 돌려, 44쪽짜리 다독 메타분석 전문이 `text.md`에 들어가게 했다. 분류·HTML·BM25·토픽 페이지는 그 다음 다시 빌드했다.

## 결과

- 논문 디렉터리 22개. `text.md` + 교육 템플릿 placeholder `review.md` + `index.html`.
- placeholder는 효과크기를 쓰지 않는다. 학부모 시사점은 `근거 강도: 판정 불가`이고, 합격·점수 보장이 없다.
- 분류 6개: Extensive Reading, Vocabulary, Reading Comprehension, Phonics and Decoding, Reading Motivation, Home Literacy. primary는 CSV `subtopic`. TF-IDF 코사인이 배경보다 높을 때만 보조 범주 1개. HDBSCAN/SPECTER2/LLM 작명 아님.
- BM25 인덱스: 논문 22, 청크 187 (리뷰 88 + text.md 99). 임베딩 바이트는 0 벡터 placeholder. 모델 필드 `bm25-only`. API 호출 없음.
- 질문 1 상위 논문: 한국 초등 EFL 단순 독해 관점(011), 형태소(007), 듣고 읽기 메타분석(010), 가정 문해(018), 다독-어휘 메타분석(002).
- 질문 2 상위 논문: SPIRE 부모 참여(023), 다독 메타분석(001), 가정 문해(018) 등이 포함된다. BM25라 질문 어휘와 겹치는 다른 논문도 섞인다. 답변 문장은 생성하지 않았다.
- 로컬 페이지 `http://127.0.0.1:8765/literacy/` HTTP 200. 리뷰 페이지 HTTP 200.
- 스크린샷: 인덱스(범주 펼침), classic 검색 `extensive reading`, Deep Research 패널(질문만 입력, Enter 없음), 리뷰의 학부모 시사점, 모바일 인덱스.

## 막힌 것

`GOOGLE_API_KEY`가 없어 다음을 호출하지 않았다.

- `ingest_pdf_folder.py --write-reviews` (Gemini 리뷰)
- `build_category_summaries.py` (Gemini 요약. 지금은 서지 라벨 설명)
- `generate_timelines.py --narrative-only`
- `build_search_index.py`의 실제 `gemini-embedding-001` (`--bm25-only`를 뺌)
- `answer_deep_research.py`의 답변 단계 (`--retrieve-only`를 뺌)

정확한 명령은 `NEXT-STEPS.md`.

## 코드에서 바꾼 점

- `llm.provider=gemini`일 때만 리뷰·타임라인 서술·카테고리 요약이 Gemini다. 기본값은 그대로 Anthropic.
- `review_profiles.literacy=education` (코드 기본값도 literacy는 education).
- Zotero 없이 CSV+PDF 폴더 ingest.
- 교육 리뷰 템플릿과 보장 표현 제거.
- `--bm25-only`는 임베딩 API를 호출하지 않는다.
- `literacy/`를 `docs/.assetsignore`에 넣어 로컬 전용으로 둔다.

## Anthropic 실행 (2026-09-28) — 호출 전 견적

이번 실행은 Gemini가 아니라 파이프라인 기본 Anthropic provider다. `config.json`의 `llm.provider=anthropic` (로컬, gitignore, 키 없음).

### 키 게이트

- `ANTHROPIC_API_KEY`: 있음. `claude-sonnet-5`, `max_tokens=16` Messages 호출 HTTP 200. input 16, output 4.
- 요약 모델 확인: `claude-haiku-4-5-20251001`, `max_tokens=16` HTTP 200. input 14, output 4.
- `GEMINI_API_KEY`: 없음. `GOOGLE_API_KEY`: 없음. Gemini 호출은 하지 않았다. 검색 인덱스는 `--bm25-only`.

### 모델

- 리뷰: `claude-sonnet-5` (기본값. Opus 아님)
- 타임라인: 코드 기본은 `claude-opus-5`. Opus-class라 `claude-sonnet-5`로 바꿨다. `TIMELINE_MAX_OUTPUT_TOKENS=4000`
- 카테고리 요약: `claude-haiku-4-5-20251001`
- 단가 (README, 2026-09-01 이후): Sonnet $3 / $15 per 1M, Haiku $1 / $5 per 1M

### 예상 비용 (step 1 이전)

| 단계 | 입력 | 출력(예상) | 예상 USD | 상한 USD |
|------|------|------------|----------|----------|
| 키 게이트 | 30 | 8 | 0.0001 | 0.0001 |
| 리뷰 22편 | 214,869 (count_tokens 실측) | 2,000×22 | 1.30 | 1.97 (max_tokens 4000) |
| 카테고리 요약 | ~6천 | ~5천 | 0.05 | 0.15 |
| 타임라인 8회 (상한 4000) | ~2만 | ~1.6만 예상 / 3.2만 상한 | 0.30 | 0.54 |
| Deep Research 2문항 | ~6천 | ~2천 | 0.05 | 0.08 |
| 검색 임베딩 | — | — | 0 (BM25) | 0 |

예상 합계 약 **$1.75**. 상한 약 **$2.74**. $3 미만이라 진행한다. 각 호출 직전 `usage_log.abort_if_over`가 누적+해당 호출 상한이 $3을 넘으면 그 호출을 하지 않는다.

## Anthropic 실행 결과

PDF 22편은 git에 없으므로 `/tmp/pilot-inputs/pdfs`에 풀고, 유료 호출 전에 `ingest_pdf_folder.py`로 `text.md`만 다시 만들었다. 논문 03(IJALEL)은 DOI 랜딩에 PDF가 없어 다시 skip.

| 단계 | 상태 |
|------|------|
| 리뷰 22편 `claude-sonnet-5` | 완료. 22/22 `review_status: anthropic:claude-sonnet-5` |
| 008 XML이 essence 한 칸에 들어옴 | 캐시를 다시 읽어 필드를 나누어 재작성. 추가 호출 없음 |
| `build_papers_index.py` | 22편, essence 22 |
| `classify_bib_subtopic.py` | 6범주, LLM 없음. 이 단계가 요약·타임라인 JSON을 덮어씀 |
| `build_category_summaries.py` | Haiku 6호출, 품질 검사 통과 |
| `generate_timelines.py --narrative-only` | Sonnet. `TIMELINE_MAX_OUTPUT_TOKENS=4000`. 이미지 없음. 일부 카테고리 JSON이 출력 한도에서 잘려, 한글 카테고리 요약으로 executive summary만 한 번 더 생성 |
| 검색 | `GEMINI_API_KEY` 없음. `--bm25-only`. 청크 275 |
| Deep Research 2문항 | Sonnet. 첫 답은 1600토큰에서 문장이 잘려 2200으로 재생성. 질문 2가 SPIRE를 싱가포르로 잘못 적어, 본문(말레이시아 멜라카)에 맞게 그 한 구절만 고침 |
| 정적 사이트 | `review_to_html` 22, `build_topic_index`. 키 환경변수를 빼고 빌드. HTML에 API 키 값은 없다. literacy 리뷰의 뒤로가기는 `../../literacy/index.html` |
| 로컬 서버 | `serve_local.py --port 8765` HTTP 200 |

실측 합계는 `usage.md`: 입력 250,987 + 출력 95,598 토큰, **$2.16**. $3 상한 안에서 끝났다.

배포, wrangler, Cloudflare, GitHub Pages, 메일, Zotero API, 업스트림 `jehyunlee/paper-curation` push/PR은 하지 않았다.
