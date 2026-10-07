# Live Studio 리뷰 (2026-10-08)

- 대상: 브랜치 `multi_agent_test`, 커밋 `6e99227` (D-326)
- 배포본: Cloud Run `live-studio-us`, 리비전 `00004-czk`
- 작성 기준 시각: 2026-10-08 12:42 KST
- 검토 방법: 코드 정독, 로컬 모의 모드 실행, 배포본 Cloud Logging 분석

근거 표시
- **[확인]** 실행하거나 로그에서 직접 확인함
- **[코드]** 코드로만 확인함
- **[추정]** 확정하지 못함

우선순위: P1 심사위원이나 사용자가 바로 부딪히는 것, P2 품질과 유지보수, P3 정리.
`CLAUDE.md` 범위 규칙상 댓글 처리와 온보딩은 다른 담당 영역입니다. 해당 항목에는 "(타 담당)"을 붙였습니다.

---

## 0. 요약

1. **뼈대는 의도대로 구현돼 있습니다.** 방송 전 문서 읽기와 용어집, 프롬프터 포인트 생성, 방송 중 병렬 판정, 방송 후 요약이 모두 동작합니다.
2. **규정 경고가 가장 느립니다.** 병렬 판정은 1~1.7초에 끝나는데, 그 뒤에 직렬로 붙은 검증자가 2~4초를 더합니다. 실측으로 경고 8건 중 4건이 통과선 5초를 넘었습니다.
3. **즉시 표시 경로는 영어 키워드 목록에만 걸립니다.** 브랜드 규칙, 문서에서 만든 법규, 한국어 발화는 전부 느린 경로를 탑니다.
4. **사실 확인이 금지 문구를 "정답"으로 안내했습니다.** 승인 안 된 문구 목록을 사실 출처로 읽은 것입니다.
5. **용어집은 STT 힌트로만 쓰이고 판정 에이전트에는 전달되지 않습니다.** STT가 "panthenol"을 "fentanyl"로 받아 적었고 사실 확인이 그대로 통과시켰습니다.
6. **댓글이 안 뜨는 것은 데모 피드가 꺼져 있어서입니다.** 장치와 데이터는 있습니다.
7. **허브의 버튼 두 개가 고장입니다.** "New demo session"은 404, 세션을 바꾸면 진행자 화면이 빕니다.
8. **테스트가 실제 구성을 검증하지 못합니다.** E2E 스펙 2개는 통과 불가 상태이고, 단위 테스트는 옛 설정으로 고정돼 있습니다.

---

## 1. 검토 범위와 방법

| 한 일 | 내용 |
|---|---|
| 코드 구조 분석 | 백엔드, 프론트엔드, 테스트, 스크립트, 데이터, 문서 전체 |
| 로컬 실행 | 모의 모드(실제 모델 호출 없음)로 서버를 띄워 테스트와 브라우저 E2E 실행 |
| 배포본 로그 분석 | 최근 36시간 Cloud Logging. 세션 `ses_…JTFP` (한국 시간 10/8 00:15~00:20) 중심 |
| 화면 문구 검토 | 한국어 번역 파일 2개, 영어 원문, 시청자 공지 템플릿 |

하지 못한 것
- 배포본 화면을 직접 조작하는 테스트. 배포본은 로그로만 확인했습니다.
- 실제 모델을 쓰는 로컬 실행. 로컬은 모의 모드로만 돌렸습니다.
- 봉인 평가 세트 실행. 레포 밖에 있습니다.

---

## 2. 의도 대비 구현 상태

### 2.1 방송 전

의도: 상품 문서를 올리면 전처리해서 용어집(STT 보완용)과 프롬프터 핵심 문장을 만든다.

| 의도 | 상태 | 비고 |
|---|---|---|
| 상품 문서 업로드와 전처리 | 됨 | PDF, 이미지, 워드, 엑셀, CSV, HTML. Gemini 3.8 Flash가 문서를 통째로 읽습니다. 읽기에 4~6분 걸린 기록이 있습니다(중앙값 254초, 최대 398초, 3건) |
| 근거 추적 | 됨 | 모든 값에 원문 인용이 붙고, 숫자가 인용에 없으면 코드가 버립니다 |
| 사람 확인 목록 | 됨 | 기본 설정에서 최대 10건 |
| 용어집 생성 | 됨 | 상품당 21~25개. 용어, 종류, 발음 형태, 출처 구획 |
| 용어집으로 STT 보완 | **반쯤 됨** | STT 힌트로 85개가 전달되지만 가중치가 없습니다. 용어집에 있는 "Panthenol"이 "fentanyl"로 들어왔습니다 |
| 용어집으로 LLM의 도메인 이해 보조 | **안 됨** | 판정 에이전트(규정, 맥락, 사실, 검증자)와 댓글 분류 어디에도 용어집이 입력되지 않습니다 |
| 프롬프터 핵심 문장 추출 | 됨 | 상품당 10~12개. 승인 후 백그라운드로 15~40초 |
| Vertex AI Search 활용 | **안 됨** | 설정(`RETRIEVER=vertex_search`)을 켜면 `NotImplementedError`가 납니다. 실제 검색은 로컬 BM25입니다 |
| 법규와 브랜드 가이드 등록 | 됨 | 문서를 읽어 규칙 팩으로 만듭니다 |
| 작업 보존 | 반쯤 됨 | 승인된 릴리스는 버킷에 남지만, 승인 전 작업은 서버 재시작 시 승인할 수 없습니다 |

Vertex AI Search에 대한 판단: 지금 문서 크기에서는 필요하지 않습니다. 상품 문서 전체가 약 15,000~20,000토큰이라 통째로 컨텍스트 캐시에 넣는 편이 빠릅니다. `docs/PLANNING.md`에는 질의당 약 2.1초, 158건 중 66건이 빈 결과였다는 측정이 있습니다. 쓴다면 문서가 많은 방송 전 단계에만 맞고, 라이브 경로에는 넣으면 안 됩니다.

### 2.2 방송 중

의도: 진행자 발화가 들어오면 상품 정보 오류, 규정 위반, 프롬프터 전환 여부를 병렬로 전부 판정하고 해당하는 결과만 띄운다. 규정 위반이 가장 엄격하고 빨라야 한다.

| 의도 | 상태 | 비고 |
|---|---|---|
| 발화마다 병렬로 전부 판정 | 됨 | 규정, 맥락, 사실 세 에이전트를 동시에 호출 |
| 해당하는 결과만 표시 | 됨 | 위반이 없으면 아무것도 뜨지 않습니다 |
| 상품 정보 오류 확인 | 됨, 품질 문제 | 금지 문구 목록을 사실 출처로 읽는 오류, 오인식 성분 통과 |
| 규정 위반 확인 | 됨, **느림** | 검증자 직렬 단계 때문에 4~6초 |
| 프롬프터 자동 전환 | 됨, 불안정 | 지난 세션에서 첫 시도가 먹히지 않았습니다 |
| 프롬프터 포인트 소화 표시 | 됨 | 맥락 판정이 처리 |
| 시험 결과 문구 단서 요구 | 됨, UX 문제 | "in our in-house test"를 10초 넘겨 말하면 인정되지 않습니다 |
| 댓글 분류, 답변, 게시 | 파이프라인은 됨 | 데모에서 댓글을 쏘는 장치가 꺼져 있습니다 |
| AI PD 카드 | 됨 | 질문이 없으면 보여줄 것이 없습니다 |

### 2.3 방송 후

| 의도 | 상태 | 비고 |
|---|---|---|
| 통계와 AI 요약 | 됨 | 요약 작성에 11~14초 |
| PDF와 JSON 내보내기 | 됨 | |
| 방송 기록 보존 | **안 됨** | 메모리에만 있어 서버가 내려가면 사라집니다. Firestore 저장소는 빈 껍데기 |

---

## 3. 방송 중 구조 평가

### 3.1 실제 흐름

```
의도:  문장 → [규정 | 맥락 | 사실] 동시 → 결과 표시
실제:  문장 → (끊긴 문장 병합·대기) → 키워드 스캔 → [규정 | 맥락 | 사실] 동시
            → 검증자(더 큰 모델) → 결과 표시
```

1. 브라우저가 16 kHz 음성을 100 ms 단위로 WebSocket에 보냅니다.
2. Google STT(`chirp_3`, 리전 `us`)가 문장을 확정합니다. 스트림은 180초마다 예비 스트림으로 교체합니다.
3. 3.5초 안에 들어온 끊긴 문장은 최대 3개까지 이어 붙입니다.
4. 정규식 키워드 스캔에 걸리면 임시 경고를 즉시 만듭니다.
5. 규정 판정, 맥락 판정, 사실 확인을 동시에 호출합니다(모두 `gemini-3.5-flash-lite`).
6. 후보 경고가 있으면 검증자(`gemini-3.8-flash`)가 후보마다 유지할지 버릴지 판단합니다.
7. 먼저 끝난 것부터 적용합니다. 규정과 사실은 즉시, 맥락과 답변 게시는 문장 순서대로.
8. 이벤트 스트림으로 화면에 전달합니다.

### 3.2 설계상 제한 시간

| 단계 | 제한 | 재시도 | 지연 시 재요청 |
|---|---|---|---|
| 규정 판정 | 2.5초 | 실패 시 1회 | 1.5초 뒤 |
| 맥락 판정 | 2.5초 | 없음 | 2초 뒤 |
| 사실 확인 | 5초 | 숫자가 있는 문장만 1회 | 3초 뒤 |
| 검증자 | 5초 | 없음 | **대상 아님** |

최악의 경우: 규정 경고 2.5 + 2.5 + 5 = 10초, 사실 정정 5 + 5 + 5 = 15초. STT 시간은 별도입니다.

### 3.3 병목과 구조 문제

| # | 문제 | 위치 | 영향 |
|---|---|---|---|
| L1 | **검증자가 직렬로 붙어 있습니다.** 병렬 판정이 끝난 뒤에야 시작합니다. | `utterances.py:547-558, 603-610` | 경고마다 2~4초 추가 |
| L2 | **검증이 끝날 때까지 경고 내용을 숨깁니다.** "확인 중" 칩만 뜹니다. | `utterances.py:507-520` | 가장 급한 규정 경고가 가장 늦음 |
| L3 | **검증자가 지연 시 재요청 대상이 아닙니다.** 지연값(2초)은 설정돼 있는데 대상 목록(`HEDGED_AGENTS`)에 없습니다. | `config.py:137-142`, `llm.py:505-507` | 검증자 꼬리 지연. 이전 리비전 포함 20건 중 5건 타임아웃 |
| L4 | **즉시 표시 경로가 영어 키워드에만 걸립니다.** 브랜드 규칙 9개와 문서에서 만든 법규는 키워드가 0개, 한국어는 목록 자체가 없습니다. | `data/lang/en.json`, `onboarding/lawpack.py:195` | 새 상품, 새 시장일수록 전부 느린 경로 |
| L5 | **끊긴 문장을 최대 3.5초 기다립니다.** "so", "and"로 끝난 조각은 다음 문장과 합치려고 판정을 미룹니다. | `utterances.py:277-284` | 해당 문장 최대 +3.5초 |
| L6 | **의미 없는 조각에도 세 번씩 호출합니다.** 지난 세션 문장 40개 중 10개가 "Um.", "Yep.", "Hello." 등이었습니다. | `utterances.py:294-327` | 비용, 공용 용량 초과(429) 위험 |
| L7 | **다음 상품의 캐시를 미리 만들지 않습니다.** 첫 상품만 방송 시작 때 만듭니다. | `utterances.py:569-579`, `runtime.py:278` | 전환 직후 사실 확인 2.5초 |
| L8 | **맥락 판정이 캐시를 못 탑니다.** 입력 평균 3,989토큰, 캐시 기준 4,096토큰. 40번 모두 캐시 없이 실행. | `llm.py:292-299` | 비용과 약간의 지연 |
| L9 | **캐시 생성 중에는 최대 1초 기다렸다가 캐시 없이 호출합니다.** | `llm.py:341` | 방송 시작과 전환 직후 첫 호출 지연 |
| L10 | **STT 멈춤을 감지하지 못합니다.** 음성은 들어가는데 결과가 오지 않는 상황을 감시하는 코드가 없습니다. | `providers/stt.py:132-192` | 지난 세션에서 36초 공백 |
| L11 | **방송 종료 후에도 마이크가 계속 돕니다.** 종료 시 음성 연결을 끊지 않습니다. | `api/audio_ws.py`, `runtime.py:289` | STT 비용, 종료 후 2분 넘게 문장 유입 |
| L12 | **429 대응이 없습니다.** 재시도나 대기 없이 실패로 끝납니다. | `llm.py:372-373` | 공용 용량 혼잡 시 경고 누락 |
| L13 | **맥락 결과와 답변 게시는 문장 순서대로 적용합니다.** 앞 문장의 판정이 늦으면 뒤 문장의 전환 신호와 게시가 밀립니다. | `utterances.py:329-352` | 전환 지연, 말로 한 답변 게시 지연 |
| L14 | **서버가 0대로 줄어듭니다.** 다시 뜰 때 강한 모델 예열이 실패한 기록이 있습니다(504 2회, 499 1회). | `deploy/cloudrun.sh`, `llm.py:639` | 첫 검증 호출 지연, 세션 소실 |
| L15 | **온보딩의 동기 파일 입출력이 라이브 판정과 같은 이벤트 루프를 씁니다.** (타 담당) | `onboarding/storage.py:86` | 방송 중 누가 상품을 등록하면 지연 |
| L16 | **검증자 호출 후에 출처 검사를 합니다.** 코드가 버릴 주장에도 호출이 먼저 나갑니다. | `agents/verifier.py:158-163` | 불필요한 호출과 "확인 중" 표시 |
| L17 | **판정 내용과 전환 신호가 로그에 남지 않습니다.** 맥락 판정 출력, 전환 계수, 병합 대기가 INFO 로그에 없습니다. | `utterances.py`, `logic/segments.py` | 전환 실패 같은 문제를 사후에 진단 불가 |

### 3.4 규정 경고를 가장 빠르게 하는 구조 (제안)

규정 판정 자체는 중앙값 1.0초에 끝납니다. STT 0.7초, 화면 표시 0.3초를 더하면 2초 안에 띄울 수 있습니다.

```
문장 → 규정 판정 (1.0초) → 임시 경고 즉시 표시 → 검증자 → 확정 또는 취소
```

- **판정이 후보를 내면 바로 임시 경고를 띄웁니다.** 문제 구절과 대체 문구까지 보여 줍니다. 검증자는 뒤에서 확정하거나 취소만 합니다.
- **새로 만들 것이 거의 없습니다.** 임시 경고 상태(`provisional`)와 확정, 취소 처리는 키워드 경로용으로 이미 있습니다(`logic/alerts.py`). 키워드가 하던 역할을 판정 결과로 넓히는 변경입니다.
- **대가는 화면 깜빡임입니다.** 검증자가 취소하면 떴던 경고가 사라집니다. 지난 세션에서는 규정 검증 5건 중 1건이 취소였습니다. 임시는 노란색, 확정은 빨간색으로 구분하면 받아들일 만합니다.
- **검증자를 지연 시 재요청 대상에 넣습니다.** 설정 한 줄입니다.
- **기대 효과:** 규정 경고 첫 표시 2초대, 확정은 지금과 같은 4~5초.

검증자를 넣은 이유도 기록해 둡니다. 빠른 모델 단독으로는 오경고 10~20%, 잘못된 HIGH 4~13건이 나왔습니다(`CLAUDE.md` 10/6 측정). 그래서 검증자를 없애는 것이 아니라 표시 시점을 앞당기는 것을 제안합니다.

---

## 4. 지연 시간 실측

출처: 배포본 Cloud Logging, 리비전 `00004-czk`. 경고 8건, 문장 약 40건. 경향을 보는 수준의 표본입니다.

### 4.1 말이 끝난 뒤 경고가 화면에 뜨기까지

| 대사 | 경고 | 첫 표시 | 확정 | 화면 표시 확인 |
|---|---|---|---|---|
| "This cream helps your wrinkle gone forever." | 사실 정정 메모 | 3.9초 | 3.9초 | 4.3초 |
| 같은 문장 | 규정 HIGH (브랜드 규칙) | 5.5초 | 5.5초 | 5.8초 |
| 같은 문장 | 규정 MEDIUM (브랜드 규칙) | 5.5초 | 5.5초 | 5.8초 |
| "So the Hydra Barrier Cream removes wrinkles or reverses skin aging." | 규정 HIGH (키워드 적중) | **0.7초** | 4.0초 | 4.3초 |
| 같은 문장 | 사실 정정 메모 | 5.8초 | 5.8초 | 6.0초 |
| "It helps keep skin hydrated for up to 24 hours." | 시험 문구 배너 | 3.6초 | 3.6초 | 3.9초 |
| "Honestly, this serum erases wrinkles completely…" (텍스트 주입) | 사실 정정 메모 | 3.2초 | 3.2초 | 3.4초 |
| 같은 문장 | 규정 HIGH | 5.4초 | 5.4초 | 5.7초 |

- 화면 표시 기준 중앙값 5.0초, 최대 6.0초. 8건 중 4건이 5초 초과.
- 마지막 문장은 STT를 거치지 않았는데도 5.7초입니다.
- 이전 리비전의 한국어 문장 "밤 사이에 주름이 사라집니다."는 규정 HIGH 6.6초, 사실 메모 6.8초였습니다.

### 4.2 구간별 소요 시간

| 구간 | 모델 | 건수 | 중앙값 | 상위 5% | 최대 |
|---|---|---|---|---|---|
| STT: 말 끝 → 문장 확정 | chirp_3 | 42 | 0.69초 | 8.5초 | 27.5초 |
| 규정 판정 | 3.5 Flash-Lite | 41 | 0.99초 | 1.36초 | 1.43초 |
| 맥락 판정 | 3.5 Flash-Lite | 40 | 1.21초 | 1.42초 | 1.53초 |
| 사실 확인 | 3.5 Flash-Lite | 40 | 1.26초 | 1.74초 | 2.49초 |
| 검증자 | 3.8 Flash | 11 | 2.15초 | 3.92초 | 4.07초 |
| 검증자가 더한 시간 (규정) | | 5 | 2.19초 | 3.97초 | 4.07초 |
| 검증자가 더한 시간 (사실) | | 4 | 1.97초 | 3.52초 | 3.77초 |
| 서버 → 화면 표시 확인 | | 8 | 약 0.3초 | | 0.39초 |
| 댓글 분류 | 3.5 Flash-Lite | 5 | 1.21초 | 1.25초 | 1.26초 |
| 답변 작성 | 3.8 Flash | 2 | 3.14초 | | 3.74초 |
| 답변 검증 | 3.5 Flash-Lite | 2 | 0.83초 | | 0.86초 |
| 방송 요약 | 3.8 Flash | 2 | 11.6초 | | 13.5초 |

"wrinkle gone forever"의 규정 HIGH 5.5초 분해: STT 0.60 + 규정 판정 1.36 + 검증자 3.56. 검증자가 전체의 약 3분의 2입니다.

호출 실패: 규정 판정 1건 오류(41건 중). 이전 리비전 포함 시 검증자 20건 중 5건이 5초 타임아웃.

### 4.3 STT 멈춤

한국 시간 00:16:09부터 약 36초 동안 문장이 들어오지 않다가 네 문장이 1.4초 사이에 한꺼번에 도착했습니다.

| 도착 시각 | 말 끝난 뒤 | 문장 |
|---|---|---|
| 00:16:44.99 | 27.5초 | "So it absorbs really quickly. Inside you've got 1% ceramide NP, 5% fentanyl and 3% squalane." |
| 00:16:45.45 | 25.2초 | "Oh, Raj is asking if" |
| 00:16:45.95 | 8.5초 | "Actually, this cream really helps your wrinkles." |
| 00:16:46.32 | 7.1초 | "coin" |

이 구간을 빼면 STT는 0.5~1.1초로 안정적입니다. 스트림 교체 시점(186초)과는 무관한 구간입니다. 원인은 로그만으로는 알 수 없습니다. Google 쪽 지연인지 음성 전송 끊김인지 구분되지 않습니다.

### 4.4 측정의 한계

- 서버 시각 기준입니다. 브라우저에서 음성이 서버에 닿기까지의 시간(보통 0.1~0.3초)은 빠져 있습니다.
- STT 지연에는 말이 끝났다고 판단하기까지의 침묵 대기가 포함됩니다.
- 경고 8건으로는 상위 5% 값을 신뢰하기 어렵습니다. 통과선 판정에는 수십 건이 필요합니다.
- 배포 스크립트는 최근 `STT_ENDPOINTING=STANDARD`로 바뀌었습니다. 이 리비전에 반영됐는지는 확인하지 못했습니다.

---

## 5. 라이브 세션 로그 분석

세션 `ses_…JTFP`, 한국 시간 10/8 00:15:36 시작, 00:20:29 종료. 상품은 Hydra Barrier Cream과 Deep Hydration Ampoule.

### 5.1 판정이 틀린 것

| # | 발화(STT 결과) | 일어난 일 | 문제 |
|---|---|---|---|
| J1 | "…1% ceramide NP, 5% fentanyl and 3% squalane." | 사실 확인이 "5% fentanyl"을 `supported`로 판정 | 원래 말은 "panthenol". 문서에 없는 성분을 통과시켰습니다. 소리가 비슷한 값을 불확실로 처리하는 프롬프트 v2 이상이 기본값이 아닙니다(기본 v1) |
| J2 | "This cream helps your wrinkle gone forever." | 사실 정정 메모 생성. 정답 칸이 "Removes wrinkles or reverses skin ageing." | "승인 안 된 문구" 목록을 사실 출처로 읽었습니다. 진행자에게 금지 문구를 말하라고 안내하는 셈입니다 |
| J3 | "So the Hydra Barrier Cream removes wrinkles or reverses skin aging." | 사실 정정 메모. 정답 칸이 "Removes wrinkles or reverses skin ageing is not approved" | J2와 같은 원인. 두 메모 모두 정정되지 않은 채 45초 뒤 숨겨졌습니다 |
| J4 | "Actually, this cream really helps your wrinkles." | 규정 판정은 브랜드 규칙 위반으로 잡았으나 검증자가 "주름 제거를 암시하지 않는다"며 기각 | 다음 문장 "wrinkle gone forever"는 통과. 같은 유형인데 결과가 갈렸고, 앞 문장은 놓친 것으로 볼 여지가 있습니다 |
| J5 | 같은 문장 | 사실 확인도 같은 문장에 금지 문구 기반 후보를 냈고 검증자가 기각 | J2와 달리 여기서는 검증자가 걸렀습니다. 검증자 판단이 일관되지 않습니다 |

J2, J3의 원인: 기본 경로에서는 "승인 문구 구획을 출처로 쓴 주장은 버린다"는 코드 가드가 건너뛰어집니다(`fact_checker.py`의 `hard_validate`, 검증 모드에서는 `:823`의 `continue`로 생략). 검증자가 대신 걸러야 하는데 일관되게 거르지 못했습니다.

### 5.2 의도대로 움직이지 않은 것

| # | 상황 | 일어난 일 | 원인 |
|---|---|---|---|
| U1 | "up to 24 hours" 배너가 뜬 뒤 28초 후 "It is our in-house test."라고 말함 | `no_correcting_content`로 거절. 배너 유지 | 덧붙이기는 10초 안에만 인정됩니다(`LATE_QUALIFIER_MS`). 그 뒤에는 결과 문장까지 다시 말해야 합니다. 배너 문구는 그렇게 안내하지 않습니다 |
| U2 | 같은 배너 중 시험 상세를 읽음("…32 participants aged 20 to 49…corneometer") | 역시 거절 | 같은 원인 |
| U3 | "Okay, now let me show you our Deep Hydration Ampoule. It has 4% niacinamide." 이후 "It's a watery gel." / "Just two or three drops." / "after toner" | 상품 전환이 일어나지 않음 | 전환은 "다음 상품 이름을 말한 전환 문장" 뒤 30초 안에 "다음 상품의 프롬프터 포인트를 말한 문장"이 와야 확정됩니다. 대본의 한 문장을 STT가 세 조각으로 끊었습니다. **[추정]** 맥락 판정 출력이 로그에 없어 확정 불가 |
| U4 | "Let us skip to the next product, which is Deep Hydration Ampoule." 다음 "So, it is 4% niacinamide." | 전환됨(00:20:12경) | 두 번째 시도에서 조건 충족. 5초 카운트다운 포함 |
| U5 | "where are the questions?" | 질문이 하나도 없음 | 6절 참고 |
| U6 | "Oh, Raj is asking if" + "Actually, this cream really helps your wrinkles." | 두 문장이 하나로 병합됨 | 앞 문장이 끝맺음 부호 없이 끝나 병합 조건을 만족. 서로 무관한 문장입니다 |
| U7 | 한 문장에 경고 3개 | "wrinkle gone forever"에 사실 메모, 규정 HIGH, 규정 MEDIUM이 동시에 뜸 | 같은 구절에 대한 중복 안내 |

### 5.3 시스템 문제

| # | 일어난 일 | 근거 |
|---|---|---|
| S1 | "New demo session" 클릭 3회 모두 404 | 00:15:02, 00:15:18, 00:15:34에 `POST /api/sessions` 404 |
| S2 | 방송 종료 후에도 마이크 스트림 유지 | 00:20:29 종료, STT 문장이 00:22:39까지 도착. 종료 후 스트림 교체까지 수행 |
| S3 | 서버가 0대로 줄었다가 재시작 | 23:53:01, 00:14:27에 새 인스턴스 시작 |
| S4 | 강한 모델 예열 실패 | `warm-up of gemini-3.8-flash failed` 504 2회, 499 1회 |
| S5 | STT 36초 멈춤 | 4.3절 |
| S6 | STT 오인식 | "DAON LAB" → "down lab", "Hydra Barrier Cream" → "Hydra version", "panthenol" → "fentanyl". 힌트 85개가 걸려 있었음 |
| S7 | 의미 없는 조각마다 3회 호출 | "coin", "Yep.", "Hello." 2회, "come", "Switch.", "Um.", "Yeah. Um, yeah." 등 |
| S8 | 캐시 없이 실행된 호출 | "context cache … still being created; this call runs uncached" 3회(방송 시작, 전환 직후) |

### 5.4 정상 동작한 것

- 규정 HIGH 경고 생성, 5초 뒤 격상, 정정 문장("It helps support the skin's moisture barrier.")으로 약 1초 만에 정정 처리. 2회 모두 정상.
- 키워드 적중 문장의 임시 경고 0.7초 표시.
- 시험 문구 배너("up to 24 hours") 생성.
- 성분, 제형, 사용법 발화의 사실 확인(`supported`) 정상: "lightweight gel-cream", "1% ceramide NP", "3% squalane", "4% niacinamide", "watery gel", "two to three drops", "after toner".
- 다른 상품을 언급했을 때 사실 확인이 해당 상품 문서를 기준으로 판정.
- 방송 요약 생성(13.5초).

---

## 6. 댓글이 안 뜨는 이유

쏘는 장치와 데이터는 있고, 꺼져 있습니다.

- **장치는 서버 안의 타이머입니다.** 별도 클라우드 작업(Cloud Run Job, Scheduler)은 레포에 없습니다. `FeedEngine`이 2.5~6초 간격으로 배경 댓글을 흘리고, 데모 콘솔 버튼으로 질문 묶음을 쏩니다(`backend/app/pipelines/feed.py`).
- **데이터도 준비돼 있습니다.** `data/demo/comment_pool.json`에 배경 댓글 49개, `data/demo/comment_script.json`에 묶음 5개가 있습니다. 상품 ID가 지금 데모 릴리스와 일치합니다.

| 묶음 | 내용 | 댓글 수 |
|---|---|---|
| B1 | 반응과 가격 질문 | 9 |
| B2 | 지성 피부, 메이크업 | 13 |
| B3 | 민감 질문(임신 등), 스팸 | 8 |
| B4 | 타임 세일 | 4 |
| B5 | 상품 전환 직후 | 7 |

- **릴리스 방송에서는 무조건 꺼집니다.** `backend/app/pipelines/runtime.py:101`이 릴리스로 만든 방송이면 피드를 끕니다. 지금은 데모 자체가 릴리스 방송이라 항상 꺼집니다.
- **꺼진 상태에서 버튼을 누르면 오류가 납니다.** 묶음 버튼은 404 `unknown_burst`, 배경 댓글 시작은 500(`KeyError: 'min_gap_ms'`)입니다. [확인]
- **시청자 직접 입력도 꺼져 있습니다.** `VIEWER_INPUT_ENABLED` 기본값이 false이고 배포 스크립트가 켜지 않습니다.
- **지금 댓글이 뜨는 경로는 둘뿐입니다.** 시승 화면의 고정 댓글 5개, 그리고 스크립트용 `POST /api/sessions/{sid}/demo/comments`.

고치는 방법: 방송의 릴리스가 데모 릴리스(`data/demo_release/show.json`)와 같으면 피드를 켭니다. 조건 한 줄과 빈 풀 방어 코드입니다. 실행으로 검증하지는 않았습니다. [코드] (타 담당)

댓글 처리 자체의 속도는 문제없습니다. 새 질문 하나에 분류 1.2초, 답변 작성 3.1초, 검증 0.8초로 약 5초이고, 같은 질문은 캐시로 즉시 답합니다.

---

## 7. 로컬 테스트 결과

모의 모드. 실제 Gemini와 STT는 호출하지 않았습니다.

| 항목 | 결과 |
|---|---|
| 백엔드 pytest | 1,296개 통과. `GCP_PROJECT`가 없으면 10개 파일이 수집 단계에서 실패 |
| 프론트엔드 vitest | 192개 통과 |
| 프론트엔드 빌드 | 성공. Node 22 필요, 20.8에서는 실패 |
| Playwright E2E 2개 | 둘 다 실패 |
| 데모 대본 직접 진행 | 규정 경고, 정정, 부정문 무경고, 방송 시작과 종료, 요약은 정상 |

모의 모드에서 확인하지 못한 것: 사실 정정(녹화 응답이 옛 형식이라 `invalid`), 상품 전환, 댓글 응답, 프로모.

최신 커밋에서 이미 고쳐진 것: 프론트엔드가 이벤트 5종(`verify.started`, `verify.done`, `verify.health`, `line.check`, `feed.updated`)을 구독하지 않던 문제. D-320에서 수정됐습니다.

---

## 8. 개선점 전체 목록

A~G는 코드와 문구 검토에서, H는 라이브 세션과 구조 평가에서 나온 항목입니다.

### 8.A. 기능 결함 (P1)

| # | 문제 | 위치 | 고치는 방법 |
|---|---|---|---|
| A1 | **[확인]** 세션이 바뀌면 진행자 화면이 "No product on air"로 빕니다. 스튜디오에서 "Reset demo"를 누르거나 `/host`를 `?session=` 없이 열 때 생깁니다. 새로고침하면 돌아옵니다. | `frontend/src/app/store.ts:218-233` | `cachedResource`가 돌려주는 훅의 `useEffect` 의존성이 `[]`라, 세션 ID가 바뀌어 다른 리소스로 교체돼도 불러오지 않습니다. 리소스를 키로 받는 훅 하나로 바꾸고 의존성에 키를 넣습니다. |
| A2 | **[확인, 배포본 로그에서도 3회 확인]** "New demo session" 버튼이 동작하지 않습니다. 허브의 초록색 주 버튼과 데모 콘솔 버튼 모두 404 `unknown_runsheet`를 받습니다. | `frontend/src/screens/Hub.tsx:231`, `DemoConsole.tsx:178`, `frontend/src/app/api.ts:92` | 빈 본문으로 `POST /api/sessions`를 부르는데 기본 진행표가 더는 없습니다. 이미 있는 `POST /api/demo/sessions`를 부르도록 바꿉니다. 실패 시 오류 문구도 화면에 보여야 합니다. |
| A3 | **[확인]** 데모 콘솔의 "Start background chatter"가 릴리스 방송에서 500을 냅니다. | `backend/app/pipelines/feed.py:95` (`KeyError: 'min_gap_ms'`) | 릴리스 방송에서는 피드가 꺼져 있어야 하므로 `start_pool`에서 `demo=False`면 조용히 반환하고, 콘솔에서는 버튼과 B1~B4 버스트 버튼을 숨깁니다. 지금은 버튼이 보이고 누르면 404나 500이 납니다. |
| A4 | **[코드]** 허브의 "Before the show → Setup" 카드가 구형 `/setup`으로 갑니다. 깨끗한 기본 데이터에서는 문서 목록이 비어 있고, 실제 등록 흐름은 `/onboarding`입니다. | `frontend/src/screens/Hub.tsx:24-27` | 카드를 `/onboarding`으로 바꾸고 구형 설정 화면은 숨기거나 삭제합니다(B4 참고). |
| A5 | **[코드]** 승인 전 온보딩 작업은 서버가 재시작하면 승인할 수 없습니다. 결과 파일은 버킷에 있는데 작업 목록이 메모리에만 있습니다. Cloud Run은 유휴 시 0으로 줄어듭니다. (타 담당) | `backend/app/api/onboarding.py:27, 110` | 작업 조회 시 메모리에 없으면 `<job_id>/result.json`에서 복원합니다. |
| A6 | **[코드]** 운영자 헤더의 "Risky lines alerted 0/6"이 HIGH 경고가 떠 있는 동안에도 0으로 보였습니다. **[추정]** 집계 기준이 화면 설명과 다릅니다. | `frontend/src/screens/operator/Header.tsx:54-65` | 분자와 분모가 무엇인지 확인하고, 기준이 맞다면 라벨을 바꿉니다. |

---

### 8.B. 구조 (P2)

**B1. `utterances.py`를 나눕니다.** 1,511줄 한 파일에 발화 파이프라인과, 그와 무관한 운영자 조작 약 300줄(`:1204-1511`, 경고 해제, 큐, 전환 되돌리기, 공지)이 함께 있습니다. 운영자 조작을 `pipelines/host_actions.py`로 옮기면 가장 자주 바뀌는 파일(61회 수정)의 충돌이 줄어듭니다.

**B2. 판정 검증 코드를 기본 경로와 실험 경로로 분리합니다.** `fact_checker.py`(977줄)의 `_post_validate` 약 160줄과 어휘 가드 20여 개는 기본 설정에서 실행되지 않습니다. `utterance_judge.py`의 `validate_compliance` 약 155줄도 대부분 건너뜁니다. 기본 경로(`hard_validate`, 출처 확인)만 남기고 나머지를 `agents/legacy_guards.py`로 옮기면 "지금 실제로 도는 코드"가 한눈에 보입니다.

**B3. 실험 스위치를 정리합니다.** 설정이 약 30개 스위치를 갖고 있고, 그중 결론이 난 것이 많습니다.
- 삭제 후보: 설계안 E, F1, F2 전용 모듈(`rule_search.py`, `docstore.py`, `file_tools.py`), `JUDGE_MODE=split`, `COMPLIANCE_DOCS`(세 번 측정해 모두 악화), `STT_AWARE`, `NUMBER_CHECK`.
- 효과 없는 설정: `FACT_SEARCH_TIMEOUT_MS`, `GCS_BUCKET`.
- 기본값 불일치: 코드 곳곳의 `getattr(settings, "X", 기본값)`이 `config.py`와 다른 값을 씁니다(`FACT_MODE` "sheet" 대 "docs", `JUDGE_ARM` "guards" 대 "verify"). 설정은 항상 존재하므로 `getattr`를 없앱니다.
- `FACT_PROMPT` 기본값은 아직 v1인데 최근 측정은 v2~v4로 했습니다. 채택한 버전을 기본값으로 올려야 배포본이 측정한 구성과 같아집니다.

**B4. 상품 등록 경로를 하나로 합칩니다.** 구형 `/api/setup` + `pipelines/setup.py`(702줄) + `SetupView`와 신형 `/api/onboarding`이 공존합니다. 용어집 생성기도 둘입니다(`audio_ws.default_glossary`, `setup.default_terms`). 구형을 제거하면 약 1,500줄이 줄어듭니다. (타 담당)

**B5. 전역 설정 직접 참조를 없앱니다.** `validate_compliance`와 `fixes_of()`가 주입받은 설정 대신 `get_settings()`를 읽습니다(`utterance_judge.py:268-270`, `fact_checker.py:523-526`). 그래서 테스트가 환경변수로 설정을 고정해야 하고, D2의 문제가 생깁니다.

**B6. 순환 의존과 비공개 함수 공유를 풉니다.**
- `runtime` ↔ `utterances`, `comments`, `pd`, `feed`가 함수 안 import로 서로를 부릅니다.
- `verifier.py`, `vote.py`, `ai_pd.py`가 다른 모듈의 밑줄 함수(`_drop`, `_numbers`, `_cdrop` 등)를 가져옵니다. 공용 함수는 밑줄을 떼고 `agents/validation.py` 같은 곳으로 옮깁니다.
- 판정 메타데이터가 pydantic 비공개 속성(`_unverified`, `_votes`)으로 전달되고 `getattr`로 읽힙니다. 정식 필드로 만듭니다.

**B7. 범용 플랫폼 목표와 어긋나는 영어 전용 코드.** `fact_checker.py:190-270`, `utterance_judge.py:115-206`, `utterances.py:72-77`의 정규식(`_AFFIRM`, `_REJECT`, `_HEDGE`, `DANGLING`)은 영어에서만 동작합니다. 통화 단위 표도 SGD와 MYR뿐입니다. 언어팩(`data/lang/en.json`)으로 옮기거나, B2에서 실험 경로로 격리합니다.

**B8. 프롬프트 버전이 실제 내용을 반영하지 않습니다.** 추가 지시문(FR, REL, STT, F1 등)을 붙여도 `prompt_version`이 그대로입니다(`arms.py:92`만 예외). 호출 기록만 보고는 어떤 프롬프트였는지 알 수 없습니다. 붙인 지시문 이름을 버전 문자열에 덧붙입니다.

**B9. 검증자 호출 순서.** `verifier.py:158-163`이 모델 호출을 마친 뒤에야 숫자 출처 검사를 합니다. 코드가 어차피 버릴 주장에도 호출 비용과 "확인 중" 표시가 먼저 발생합니다. 출처 검사를 호출 앞으로 옮깁니다.

**B10. 429 대응이 앱에 없습니다.** 429는 재시도나 대기 없이 `error`로 끝납니다(`llm.py:372`). 문서에 따르면 429는 공용 용량 문제로 자주 납니다. 짧은 지터 재시도 1회나 헤지 요청으로의 전환이 필요합니다.

**B11. 프론트엔드 중복.**
- `fieldLabel` 3벌, `ruleInfo` 2벌, `switchSecondsLeft` 2벌, `cx` 8벌, `isTyping` 2벌.
- "Also answered" 묶기가 진행자(`Chat.tsx`)와 시청자(`viewer/chat.ts`)에 따로 있습니다.
- 맞춤 크기 조절 훅 `useFit`과 `usePdFit`이 같은 로직입니다.
- 업로드 요청 2곳이 공용 `request()`를 거치지 않아 세션 만료 처리가 빠집니다.

**B12. 서버와 클라이언트 타입이 손으로 맞춰져 있습니다.** `types.ts`(512줄)가 백엔드 모델을 수동 복제하고, 이벤트 페이로드는 `any`입니다. 구독 목록 누락(D-320에서 고친 것) 같은 문제가 다시 생길 수 있습니다. 이벤트 이름 목록을 한 곳에서 내보내거나, 리듀서의 `case`와 `EVENT_TYPES`가 양방향으로 일치하는지 검사하는 테스트를 둡니다. 지금 테스트는 한 방향만 봅니다.

**B13. 진행자 화면 렌더 비용.** `useNow(250)`이 `HostView` 전체를 초당 4번 다시 그리고, `useFit`이 매 렌더마다 레이아웃을 측정합니다(`HostScreen.tsx:206`, `Prompter.tsx:84`). 타이머 표시만 따로 떼어 냅니다.

---

### 8.C. 보안과 운영 (P1~P2)

| # | 문제 | 위치 | 고치는 방법 |
|---|---|---|---|
| C1 | 역할을 클라이언트가 고릅니다. `?role=operator`만 붙이면 숨긴 댓글, LLM 호출 기록, 중간 전사를 받습니다. 운영자 조작 라우트도 검사가 없습니다. | `api/sessions.py:48`, `api/events_sse.py:20`, `api/operator.py` | IAP를 유지하더라도 IAP가 넣어 주는 사용자 헤더로 역할을 정합니다. 시청자 화면을 외부에 열 계획이면 필수입니다. |
| C2 | 클라우드에서 데모 도구가 켜져 있습니다. 세션 삭제(`/demo/reset`)와 대사 주입이 열립니다. `GET /api/demo/current`는 잠금 없이 세션을 만듭니다. | `deploy/cloudrun.sh:54`, `api/demo.py:74-102` | 심사용이면 유지하되 `reset`은 운영자만 가능하게 합니다. |
| C3 | `GET /api/catalog`이 시청자에게도 규정 전체와 "승인 안 된 문구" 목록을 돌려줍니다. | `main.py:60` | 역할별로 필드를 줄입니다. |
| C4 | 세션 상태가 메모리에만 있고 인스턴스가 0으로 줄어듭니다. 방송 중 유휴로 판단되거나 재배포되면 방송이 사라집니다. | `store/firestore.py`(빈 껍데기), `deploy/cloudrun.sh` | 단기: `--min-instances=1`. 장기: `docs/SCALE_PLAN.md`의 Firestore 구현. |
| C5 | 비동기 경로에서 동기 I/O를 합니다. 온보딩의 GCS 쓰기와 파일 읽기가 라이브 판정과 같은 이벤트 루프를 막습니다. (타 담당) | `onboarding/storage.py:86`, `sources.py`, `brief.py` | `asyncio.to_thread`로 감쌉니다. |
| C6 | 컨테이너가 root로 실행되고, 프록시 헤더를 모두 신뢰합니다(`--forwarded-allow-ips='*'`). | `Dockerfile:23` | `USER` 지정. Cloud Run 뒤라 헤더 신뢰는 허용 가능하지만 주석으로 이유를 남깁니다. |
| C7 | 처리되지 않은 예외가 500으로 나옵니다. | `main.py:110`, `api/setup.py:18`의 `next(...)`, `api/onboarding.py:202` | 기본값을 주거나 404로 바꿉니다. |
| C8 | 릴리스 버전 번호를 파일 개수로 매겨, 같은 상품을 동시에 승인하면 번호가 겹칠 수 있습니다. **[추정]** (타 담당) | `onboarding/release.py:62` | 버킷의 생성 전용 쓰기를 먼저 하고 실패 시 번호를 올립니다. |

---

### 8.D. 테스트 (P2)

- **D1. E2E 스펙 2개가 통과할 수 없는 상태입니다. [확인]** `frontend/e2e/demo.spec.ts`와 `setup.spec.ts`는 예전 데모 데이터(기본 PDF, 버스트 B1~B5, `promo_time_sale_10`)를 전제합니다. 지금 데모는 릴리스에서 만들어져 이들이 없습니다. A1 때문에 첫 장면에서 멈춥니다. 스펙을 릴리스 기반으로 다시 쓰거나, 음성 시승(`/testdrive`)을 E2E 대상으로 삼습니다.
- **D2. 테스트가 운영 기본값을 검증하지 않습니다. [코드]** `backend/tests/conftest.py:24-32`가 설정 18개를 옛 값으로 고정합니다. 출시 기본값은 `test_d305.py`만 돌립니다. 최소한 발화 파이프라인 핵심 테스트는 출시 기본값으로 한 벌 더 돌려야 합니다.
- **D3. 백엔드 테스트가 개발자 `.env`에 의존합니다. [확인]** `GCP_PROJECT`가 없으면 10개 파일이 수집 단계에서 실패합니다(`tests/test_verify.py:15` 등이 import 시점에 `get_settings()` 호출). conftest에서 `LLM_PROVIDER=mock`을 환경변수로도 넣으면 해결됩니다.
- **D4. 모의 모드 녹화본이 낡았습니다. [확인]** 사실 확인 녹화 응답이 옛 형식과 옛 상품 ID라 `invalid`로 떨어집니다. 모의 모드에서 가격 오류, 성분 오류, 상품 전환 장면이 재현되지 않습니다. README의 "모의 모드로 전체 데모 재생" 설명은 지금 사실이 아닙니다. 요약 문구도 녹화본이라 통계와 어긋납니다(사실 경고가 0건인데 "가격과 성분 경고가 정정됨"이라고 씁니다).
- **D5. 지속 통합이 없습니다. [코드]** `.github/workflows`가 없습니다. pytest, vitest, 빌드만 돌려도 D1~D3이 바로 드러났을 것입니다.
- **D6. 도구 버전이 명시돼 있지 않습니다. [확인]** Vite 8은 Node 20.19 이상이 필요한데 README는 "Node.js 20+"라고 합니다. Node 20.8에서 테스트와 빌드가 모두 실패했습니다. `package.json`에 `engines`를 넣고 README를 고칩니다.
- **D7. 빠진 단위 테스트.** `mic.ts`의 재연결 로직, `sse.ts`의 `openEventStream`, `TestDrive.tsx`, 데모 콘솔 조작.
- **D8. ESLint가 없는데 코드에 `eslint-disable` 주석이 있습니다.** 도입하거나 주석을 지웁니다.

---

### 8.E. 화면 문구

#### E1. 한국어: 같은 것을 다르게 부릅니다 (P1)

| 문제 | 현재 | 제안 |
|---|---|---|
| 진행자와 허브는 "제품", 운영자는 "상품"을 씁니다(17곳 대 12곳). 한 방송 안에서 화면마다 다릅니다. | 방송 중인 **제품**이 없습니다 / 방송 중인 **상품** 없음 | 커머스 맥락이므로 "상품"으로 통일 |
| 번역 표를 합칠 때 운영자 표가 진행자 표에 덮입니다(`i18n.ko.ts:199`). 운영자 화면에 진행자용 번역이 나옵니다. | `READY`: 운영자 "대기" → 실제 표시 "준비" / `Corrected`: "정정됨" → "정정 완료" / `Ready`: "준비됨" → "답변 준비됨" / `AI answered`: "AI 답변" → "AI 답변함" / `Shelf life`: "사용 기한" → "유통기한" | 키를 화면별로 분리하거나(`op.Ready`), 번역을 하나로 맞춤 |
| "준비"가 세 가지 뜻으로 쓰입니다. | `READY` = 준비, `Setup` = 준비, `ready` = 준비됨 | 방송 전 상태 = "방송 대기", Setup = "방송 준비", 상품 상태 = "사용 가능" |
| 닫기와 무시가 섞입니다. | 버튼 `Dismiss` = "닫기", 기록 `Dismissed` = "무시함", `Dismiss false alert` = "오탐으로 닫기" | 버튼 "경고 해제", 기록 "해제함", "잘못된 경고로 해제" |
| "Say"의 번역이 화면마다 다릅니다. | 진행자 "이렇게 말하세요." / 운영자 "대체 멘트:" | 운영자도 "이렇게 말하기:" 또는 둘 다 "대체 멘트" |
| PD 지시 표현이 둘입니다. | `FROM YOUR PD` = "PD 지시" / `From your PD` = "PD가 보냄" | "PD 지시"로 통일 |

#### E2. 한국어: 어색하거나 틀린 표현 (P2)

| 현재 | 문제 | 제안 |
|---|---|---|
| `'자사 시험 기준' 붙이기` + 본문 `결과를 'in our in-house test'와 함께 말하세요.` | 제목은 한국어로 옮기고 본문은 영어 그대로입니다. 진행자가 실제로 말할 문구는 영어이므로 제목이 오해를 부릅니다. | 제목도 `'in our in-house test' 붙이기` |
| `실시간 자막` (Live transcript) | 자막이 아니라 진행자 발화 기록입니다. | "실시간 발화 기록" |
| `머무르기` (Stay) | 버튼 문구로 어색합니다. | "계속 보기" |
| `{b}개 중 {a}` | "3개 중 1"로 끝나 미완성으로 읽힙니다. | "{b}건 중 {a}번째" |
| `높음` / `중간` (HIGH / MEDIUM) | 무엇이 높은지 드러나지 않습니다. | "고위험" / "주의" |
| `보안 차단` / `보안 미검사` (Armor blocked / Unscreened) | 운영자가 뜻을 알기 어렵습니다. | "안전 필터 차단" / "안전 필터 미확인" |
| `Google 공용 용량 혼잡` | 내부 인프라 사정을 운영자에게 노출합니다. | "AI 서버 혼잡" |
| `AI 판정 p50 {v}` | 통계 용어입니다. | "AI 판정 시간(중앙값) {v}" |
| `댓글 스트림` | 직역입니다. | "실시간 댓글" |
| `필터된 댓글 보기` | "필터된"이 어색합니다. | "숨긴 댓글 보기" |
| `회수` (Recall) | 맥락 없이는 뜻이 모호합니다. | "진행자 화면에서 내리기" |
| `제품 띠` (product strip) | 직역입니다. | "상품 정보 바" |
| `감사 인사` (Shout-out) | 호명 인사를 뜻하므로 의미가 좁습니다. | "시청자 인사" |
| `진행` (Direction) | 카드 종류 이름으로 모호합니다. | "진행 안내" |
| `읽어 주기` (Read out) | 상태 라벨인데 동작처럼 읽힙니다. | "읽어 줄 차례" |
| `상위 {n}` (TOP) | | "주요 질문 {n}" |
| `브리프 생성 중` | "브리프"는 내부 용어입니다. | "방송 자료 준비 중" |
| `이 방송은 끝났습니다 (서버가 다시 시작됨).` | 서버 사정을 그대로 노출합니다. | "방송 연결이 끊겼습니다. 새 방송을 시작해 주세요." |
| `시청자 채팅에 60초간 "Correction" 라벨로 고정됩니다.` | 다른 곳에서는 Correction을 "정정"으로 옮겼습니다. | 시청자 화면이 영어라면 그대로 두고, 아니면 "정정" |
| `프롬프터를 다 쓰려면 잠시 기다려 주세요.` | 뜻이 불분명합니다. | "프롬프터 포인트가 모두 준비될 때까지 약 30초 기다려 주세요." |

#### E3. 한국어 번역이 없는 화면 (P2)

- 시청자, 시승, 온보딩, 요약, 구형 설정, 스튜디오, 데모 콘솔 화면은 영어 고정입니다. 화면 언어를 한국어로 바꿔도 허브에서 한 번 들어가면 영어가 됩니다.
- 번역된 화면 안에도 영어가 남습니다: 사실 정정 문장 "say … during the …"(`hostSelectors.ts:74-82`), 출처 "product sheet, …"(`:65-69`), "now"(`selectors.ts:41`), 마이크 메시지 "Reconnecting…", "Microphone unavailable"(`mic.ts`).
- 반대로 영어 전용 화면에 한국어가 섞여 있습니다: "자동 감지 (auto)"(`prefs.ts:73`), "· 실험 중 · 정확도 미측정"(`DemoConsole.tsx:287`).
- 날짜가 `en-GB`로 고정돼 있고(`summary/format.ts:28`), `<html lang="en">`이 바뀌지 않습니다.
- 대문자를 문자열로 넣어 키가 중복됩니다(`"Your prompter"`와 `"YOUR PROMPTER"`, `"Live chat"`와 `"LIVE CHAT"`). CSS `text-transform`으로 처리하면 번역 키가 절반으로 줄어듭니다.

#### E4. 영어 문구 (P2)

| 위치 | 현재 | 문제 | 제안 |
|---|---|---|---|
| 허브 | 버튼 "Start with approved products", 제목 "Previously approved products" | "Previously"가 군더더기이고 두 표현이 다릅니다. | "Approved products" |
| 허브 | "Open Studio (demo) →" 옆에 "Try it with a sample product →" | 주 버튼이 둘이라 어디부터 눌러야 할지 모릅니다. | 심사위원용 진입점인 시승을 주 버튼으로, 스튜디오는 보조로 |
| 허브 | "Live video, product strip and chat with checked AI answers." | "checked"가 모호합니다. | "…chat with fact-checked AI answers." |
| 허브 | 긴 브리프 안내 "…wait for the full prompter." | 명령인지 설명인지 불분명합니다. | "Wait about 30 s for the full prompter, or start now with the approved claims only." |
| 시승 | "Read before: loading…" | 뜻을 알 수 없습니다(이전에 읽어 둔 결과를 불러온다는 뜻). | "Loading the saved reading…" |
| 시승 | "{n} price conflicts · newest used" | 0건이어도 "0 price conflicts · newest used"로 나옵니다. | 0건이면 "No price conflicts", 있으면 "2 price conflicts · newest price used" |
| 시승 | "S$36.00 live" 칩 | "live"가 방송 중 표시와 겹칩니다. | "Live price S$36.00" |
| 시승 | "Review every field instead →" | 어디로 가는지 불분명합니다. | "Review each field yourself →" |
| 시승 | "About 2 minutes…" | | "Reading… about 2 minutes" |
| 온보딩 | "Any documents of one product: …" | 문법이 어색합니다. | "Upload any documents for one product: …" |
| 온보딩 | "Brief failed (...): the show uses the approved claims as points and only the main names as hints." | 내부 용어(brief, hints)가 그대로입니다. | "Show prep failed. The show will use the approved claims as talking points, and speech recognition will know only the main names." |
| 온보딩 | "…never posted to viewers by themselves." | "by themselves"가 어색합니다. | "…never posted to viewers automatically." |
| 온보딩 | "Reading 3 file(s)… about 1–3 minutes." | "file(s)" 표기. 바로 위 버튼은 단복수를 구분합니다. | 같은 방식으로 단복수 처리 |
| 온보딩 | "Not in the documents, or left out" | 뜻이 모호합니다. | "Missing from the documents" |
| 운영자 | "Grouped by intent, ready for your next move." | 과장된 문구입니다. | "Grouped by topic." |
| 운영자 | "Risky lines alerted 0/6", "LLM 0k tokens/h", "Judge p50" | 내부 지표가 운영자 화면에 그대로 있습니다. | 운영자용은 "Alerts 0", 나머지는 접힌 진단 패널로 |
| 운영자 | "Google shared capacity busy" | 인프라 노출. | "AI service busy" |
| 진행자 | "Finish the correction first" | 명령조로 읽힙니다. 경고 중 유일하게 꾸짖는 어투입니다. | "Questions resume after the correction" |
| 진행자 | "AI check slow: alerts may be missing" | "missing"이 불안하게 읽힙니다. | "AI check is slow. Some alerts may be late or skipped." |
| 요약 | 표 머리글 "You said" | 요약은 팀이 보는 화면입니다. | "Host said" |
| 요약 | "Composed answers" / "Instant answers" | 구분이 사용자에게 의미가 없습니다. | "New AI answers" / "Reused AI answers" |
| 세션 종료 | "This show ended (server restarted)." | 인프라 노출. | "This show is no longer available. Start a new one to continue." |
| 데모 콘솔 | "Speech-to-text is off (STT_PROVIDER=mock)" | 환경변수 이름 노출. 심사 화면에 보일 수 있습니다. | "Speech-to-text is off in this environment" |

#### E5. 시청자에게 보이는 문구 (`data/templates/notices.json`) (P2)

| 현재 | 문제 | 제안 |
|---|---|---|
| "Correction: {product_name} {field_label} is {correct_value}." | "Correction: Hydra Barrier Cream volume is 50 ml."처럼 문법이 깨집니다. | "Correction: the {field_label} of {product_name} is {correct_value}." |
| "Correction from {brand}: please disregard what was just said about {product_name}. Only the information on the product page applies." | 무엇이 틀렸는지 알려 주지 않아 시청자가 불안해집니다. | 무엇을 정정하는지 한 구절을 넣을 수 있게 자리표시자 추가 |
| 진행자 유보 멘트 "Good question! I don't want to guess, so I'll check…" | 모든 유보에 같은 문장이 반복됩니다. | 2~3개 변형을 두고 번갈아 사용 |

파일 맨 위에 "실사용 전 브랜드와 법무 승인 필요"라고 적혀 있습니다. 이 문구들은 시청자에게 직접 보이므로 제출 전에 한 번은 사람이 확정해야 합니다.

#### E6. 오류 문구 (P2)

- 화면 6곳이 서버 오류 메시지를 그대로 보여 줍니다(`setError(e.message)`). 사용자가 "unknown run-sheet 'daon_skincare_demo'"나 "HTTP 500"을 보게 됩니다. 오류 코드별 사용자용 문구 표를 한 곳에 둡니다.
- "Failed: {error}"(시승, 온보딩)도 같습니다. 다음에 할 일을 함께 알려 줍니다. 예: "Reading failed. Check the file type and try again."

---

### 8.F. 접근성과 반응형 (P3)

- 운영자 `Modal`에 포커스 가두기와 닫은 뒤 포커스 복귀가 없습니다(`Dialogs.tsx:12-27`). 허브 팝오버에는 있습니다.
- 질문 데스크 탭에 `role="tab"`만 있고 `tabpanel`과 화살표 키 이동이 없습니다.
- 진행자 한 글자 단축키(M, T, N, Q, E)를 끌 수 없습니다. 음성 입력 사용자에게 문제가 됩니다.
- 시청자, 설정, 스튜디오의 `aria-label`이 영어 고정입니다.
- 진행자 화면은 1920x1080 고정 캔버스를 축소하는 방식이라 작은 화면에서 글자가 0.42배까지 줄어듭니다. 혼자 방송하는 초보 진행자가 노트북 한 대로 쓰는 것이 목표라면 좁은 폭 전용 배치가 필요합니다.
- 스튜디오는 중단점이 없습니다.

---

### 8.G. 문서 (P2)

- `README.md`가 10/1 내용입니다. 온보딩, 릴리스, AI PD, 검증자, 시승, Cloud Run 배포가 없고, 없어진 `data/products/`와 레포 밖 `DEV_SPEC.md`를 가리킵니다. 심사위원이 가장 먼저 보는 문서이므로 P1에 가깝습니다.
- `docs/architecture.md`가 10/3 내용이고 에이전트 수가 문서 안에서 6개와 7개로 엇갈립니다.
- `docs/HANDOFF.md`가 옛 프로젝트(`separk-cloocus`)와 옛 리비전을 가리킵니다.
- 통과선이 세 번 바뀌었는데 옛 보고서가 그대로 PASS로 남아 있습니다.
- 잘못된 HIGH 건수가 `CLAUDE.md`(1/1)와 `docs/decks/test_log.html`(0/0)에서 다릅니다.
- `docs/DECISIONS.md`: D-154 누락, D-268 중복, 순서 뒤바뀜.
- `.env.example` 주석이 값과 다릅니다(`JUDGE_ARM` 설명 "guards (today)", 값은 `verify`). `config.py`의 주석도 줄이 밀려 있습니다(`:40, :90, :112-115`).
- 배포 스크립트와 문서에 개인 업무 이메일이 들어 있습니다. 공개 제출 전에 변수로 뺍니다.
- 프로젝트 ID 철자가 `ai-budiler-cup-…`입니다. 실제 ID라 바꿀 수 없으니 오타가 아니라는 주석을 한 줄 둡니다.

---


### 8.H. 라이브 경로 (P1~P2)

3절과 5절에서 나온 개선점입니다. 병목 번호(L)와 세션 관찰 번호(J, U, S)를 함께 적었습니다.

| # | 개선 | 근거 | 우선 |
|---|---|---|---|
| H1 | 규정 판정이 후보를 내면 임시 경고를 즉시 표시하고, 검증자는 확정 또는 취소만 하게 합니다. | L1, L2, 3.4절 | P1 |
| H2 | 검증자를 지연 시 재요청 대상에 넣습니다(`HEDGED_AGENTS`에 `verifier` 추가). | L3 | P1 |
| H3 | 사실 확인이 "승인 문구"와 "승인 안 된 문구" 구획을 사실 출처로 쓰지 못하게 합니다. 기본 경로에서도 이 가드를 실행하거나, 해당 구획을 사실 확인 입력에서 뺍니다. | J2, J3, J5 | P1 |
| H4 | 정정 메모의 정답 값이 말한 값과 같거나 금지 문구이면 메모를 만들지 않습니다. | J2, J3 | P1 |
| H5 | 용어집을 사실 확인과 규정 판정 입력에 넣어, 소리가 비슷한 오인식을 용어집 항목으로 해석할 근거를 줍니다. | J1, S6, 2.1절 | P1 |
| H6 | 사실 확인 프롬프트 기본값을 측정에서 채택한 버전으로 올립니다. 지금 기본은 v1이고 소리 비슷한 값 처리는 v2부터입니다. | J1 | P1 |
| H7 | STT 힌트에 가중치(boost)를 주는 방안을 측정합니다. 지금은 가중치 없이 전달됩니다. | S6 | P2 |
| H8 | 브랜드 규칙과 문서에서 만든 법규에도 즉시 표시용 키워드를 생성합니다. 규칙을 읽을 때 금지 예시 문구에서 뽑을 수 있습니다. H1을 하면 필요성이 줄어듭니다. | L4 | P2 |
| H9 | 한국어 등 다른 방송 언어의 언어팩을 추가합니다. 지금은 `data/lang/en.json`뿐입니다. | L4 | P2 |
| H10 | 숫자도 없고 키워드에도 안 걸린 짧은 조각(1~2단어 추임새)은 판정을 건너뜁니다. | L6, S7 | P2 |
| H11 | 방송 시작 때 다음 상품의 캐시도 미리 만듭니다. 전환 신호 1회 감지 시점에 만들어도 됩니다. | L7, L9, S8 | P2 |
| H12 | 맥락 판정의 고정 앞부분을 캐시 기준(4,096토큰) 이상으로 맞춰 캐시를 타게 합니다. | L8 | P3 |
| H13 | STT 감시를 넣습니다. 음성 레벨이 있는데 일정 시간 결과가 없으면 스트림을 재시작합니다. 재시작 로직은 오류용으로 이미 있습니다. | L10, S5 | P1 |
| H14 | 방송 종료 시 음성 WebSocket을 닫습니다. | L11, S2 | P1 |
| H15 | 429에 짧은 재시도 1회를 넣습니다. | L12 | P2 |
| H16 | 시험 문구 배너의 안내를 실제 조건에 맞춥니다. 10초가 지나면 "결과와 함께 다시 말하세요"로 바꾸거나, 단서만 말해도 인정하는 시간을 늘립니다. | U1, U2 | P2 |
| H17 | 상품 전환을 더 견고하게 합니다. 확인 신호를 "다음 상품의 포인트를 소화한 문장"뿐 아니라 "다음 상품에 대한 사실 확인이 `supported`로 나온 문장"으로도 인정하는 방안을 검토합니다. 지난 세션에서 사실 확인은 세 조각 모두 앰플 기준으로 판정했습니다. | U3 | P2 |
| H18 | 맥락 판정 출력, 전환 신호 계수, 병합과 대기 결정을 INFO 로그에 남깁니다. | L17, U3 | P2 |
| H19 | 무관한 문장이 병합되지 않게 합니다. 앞 조각이 질문 인용("Raj is asking if")이고 뒤가 새 문장이면 병합하지 않는 식입니다. | U6 | P3 |
| H20 | 같은 구절에 대한 경고를 하나로 묶습니다. 규정 HIGH가 뜬 구절에는 사실 메모와 MEDIUM을 겹쳐 띄우지 않습니다. | U7 | P2 |
| H21 | 최소 인스턴스를 1로 두고, 예열 실패 시 재시도합니다. 검증자 모델도 예열 대상에 넣습니다. | L14, S3, S4 | P2 |
| H22 | 검증자 호출 전에 출처 검사를 먼저 합니다. | L16 | P3 |
| H23 | 데모 릴리스 방송에서 댓글 피드를 켭니다. (타 담당) | 6절 | P1 |
| H24 | 검증자 판단의 일관성을 측정합니다. 같은 유형 문장에 유지와 기각이 갈렸습니다. | J4, J5 | P2 |

---

## 9. 통합 우선순위

**1순위: 데모에서 바로 보이는 것**

1. H1, H2: 규정 경고 즉시 표시와 검증자 재요청
2. H3, H4: 금지 문구를 정답으로 안내하는 오류
3. A1, A2, A3: 진행자 화면 비는 문제, "New demo session" 404, 피드 시작 500
4. H23: 댓글 피드 켜기
5. H13, H14: STT 멈춤 감시, 종료 시 마이크 끊기
6. H5, H6: 용어집을 판정에 전달, 사실 프롬프트 기본값

**2순위: 품질과 신뢰**

7. E1: "제품/상품" 통일, 번역 표 덮어쓰기
8. README 갱신(G), A4 허브 카드 경로
9. D3, D5, D6: 다른 사람이 받아서 바로 테스트를 돌릴 수 있게
10. H10, H11, H16, H17, H18, H20, H21
11. E2, E4, E5, E6 문구 다듬기

**3순위: 공개 범위와 유지보수**

12. C1, C2, C4: 외부 공개 범위에 따라
13. B1~B13 구조 정리: 제출 이후에 해도 됩니다. B3의 사실 프롬프트 기본값만은 H6과 같은 건이라 먼저 봅니다
14. D1, D2, D4: E2E 재작성, 출시 기본값 테스트, 모의 녹화본 갱신
15. F 접근성과 반응형

---

## 10. 확정하지 못한 것

- **상품 전환 첫 시도 실패의 원인.** 맥락 판정 출력이 로그에 없습니다. H18을 하면 다음부터 진단할 수 있습니다.
- **STT 36초 멈춤의 원인.** Google 쪽 지연인지 음성 전송 끊김인지 구분되지 않습니다.
- **운영자 헤더 "Risky lines alerted 0/6"이 경고 중에도 0이었던 이유.** 집계 기준을 확인하지 못했습니다.
- **"New demo session" 외에 배포본에서만 나는 문제가 더 있는지.** 배포본 화면을 직접 조작해 보지 못했습니다.
- **댓글 피드 조건을 바꾸면 버튼이 바로 동작하는지.** 코드로만 봤습니다.
- **릴리스 버전 번호 충돌(C8).** 동시 승인 시나리오를 실행하지 않았습니다.
- **잘못된 HIGH 건수.** `CLAUDE.md`는 1/1, `docs/decks/test_log.html`은 0/0으로 다르게 적혀 있습니다.
- **통과선 충족 여부.** 경고 8건으로는 판정할 수 없습니다. 다만 이 8건에서는 5초 선을 절반이 넘겼습니다.

---

## 부록: 로그 다시 뽑는 명령

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="live-studio-us" AND (textPayload:"app.providers.stt" OR textPayload:"app.providers.llm" OR textPayload:"app.pipelines" OR textPayload:"app.agents" OR textPayload:"/rendered")' \
  --project=ai-budiler-cup-uh-team-pjt --freshness=2h --order=asc --limit=5000 \
  --format='value(timestamp,textPayload)'
```

로그에서 볼 줄
- `utterances: final …`: 확정 문장
- `stt final N ms after speech end`: STT 지연
- `llm: agent=… latency_ms=…`: 에이전트별 소요 시간
- `verifier: compliance added N ms`: 검증자가 더한 시간
- `runtime: alert … alert.created`: 경고 생성
- `dropped by code`: 코드나 검증자가 판정을 버린 사유
