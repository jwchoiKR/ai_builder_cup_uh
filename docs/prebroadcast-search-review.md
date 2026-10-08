# 방송 전 문서 처리와 검색(Vertex AI Search) 검토

작성 2026-10-09. 대상: 방송 전 파트(문서 업로드, 용어집, 프롬프터 brief, 데이터 스토어)를 맡은 분.
댓글·요약 파트에서 검색을 붙이려고 조사하다가 확인한 내용과 제안을 정리한 것이다. 코드는 건드리지 않았다.
데이터 스토어 조사는 전부 읽기 전용 호출이었다.

수치와 사실에는 출처를 붙였다. "확인 안 함"이라고 적은 것은 실제로 확인하지 못한 것이다.

## 1. 한 줄 요약

- 지금 데이터 스토어는 청킹이 꺼져 있고 나중에 켤 수 없어서, 검색 품질을 올리려면 **새로 만들어야 한다**.
- 검색은 지금의 "제품 기록 문단"을 대체하지 말고 **보태는 방식**이 안전하다. 답변 검증이 문단 ID와 인용문 일치에
  기대고 있기 때문이다.
- 제품별 구분은 메타데이터 필터가 안 되므로 **버킷 경로 규칙**(`products/<제품키>/<파일>`)으로 한다.
- Setup과 Onboarding은 같은 일을 두 번 하고 있다. Onboarding 흐름을 뼈대로 합치고, Setup에서는 "사람이 용어집과
  요점을 확인하는 단계"만 가져오면 된다.

## 2. 지금 GCP에 있는 것 (읽기로 확인, 10/9)

프로젝트 `ai-budiler-cup-uh-team-pjt`.

| 종류 | 이름 | 상태 |
|---|---|---|
| 버킷 | `ai-budiler-cup-uh-data-source` (ASIA) | PDF 2개: `DAON_LAB_Deep_Hydration_Ampoule.pdf`, `DAON_LAB_Hydra_Barrier_Cream.pdf` (루트에 있음) |
| 버킷 | `ai-budiler-cup-uh-data-source-policy` (ASIA) | 비어 있음. 규제 문서용으로 보이며 이번 검토 범위 밖 |
| 데이터 커넥터 | `ai-budiler-cup-uh-data-connector_1791461083755` | GCS, `syncMode: STREAMING`, `state: ACTIVE`, 대상 `gs://ai-budiler-cup-uh-data-source/**` |
| 데이터 스토어 | `ai-budiler-cup-uh-data-connector_1791461083755_gcs_store` (global) | 비정형(`CONTENT_REQUIRED`), 문서 2개 들어가 있음 |
| 검색 앱 | `ai-budiler-cup-uh-search_1791461058419` | `SEARCH_TIER_ENTERPRISE`, 부가 기능 `SEARCH_ADD_ON_LLM` |

데이터 스토어의 처리 설정은 기본 파서뿐이다: `{"defaultParsingConfig": {"digitalParsingConfig": {}}}`. 청킹 설정이 없다.
스키마에는 필드가 없고, 문서의 `structData`도 비어 있다.

버킷에 파일을 올리면 커넥터가 알아서 데이터 스토어에 넣는 구조는 이미 동작한다. 올린 뒤 검색에 잡히기까지 걸리는
시간은 재지 않았다.

## 3. 시험 검색 결과

검색 앱에 질문 5개를 넣어 봤다. 각 1회.

| 질문 | 결과 | 시간 |
|---|---|---|
| how much is the cream | 크림 문서, 가격이 있는 조각 포함 | 760 ms |
| can I use it while pregnant | 두 문서 모두, 주의사항 조각 포함 | 509 ms |
| does it have fragrance | 크림 문서 | 511 ms |
| 크림 용량이 얼마예요? | 결과 0개 | 468 ms |
| do you ship to malaysia | 결과 0개 (문서에 없음, 맞는 결과) | 454 ms |

청크 모드(`searchResultMode: CHUNKS`)로도 호출은 됐고 347~553 ms였다. 다만 돌아온 조각은 일반 모드의 발췌 조각과
같은 크기였고 페이지 정보(`pageSpan`)와 문서 정보(`documentMetadata.uri`)가 비어 있었다.

5개만 돌린 것이라 품질을 잰 것은 아니다. 문제가 어디 있는지 보는 용도다.

## 4. 확인된 문제 네 가지

### 4.1 조각이 크다

한 조각이 670~2,055자, 사실상 페이지 단위다. 지금 앱이 쓰는 근거 문단은 "가격 한 줄", "주의사항 한 줄" 단위라서
훨씬 거칠다. 조각이 크면 답변 모델에 들어가는 글이 늘고, 엉뚱한 문장을 인용할 여지도 커진다.

원인은 청킹이 꺼져 있어서다. 공식 문서에 이렇게 적혀 있다.

> Document chunking can't be turned on or off after data store creation.

즉 지금 스토어로는 고칠 수 없다. 새로 만들 때 켜야 한다. 켜면 조각 크기를 100~500토큰으로 정할 수 있고
(`chunkSize`, 기본 500), 각 조각에 상위 제목을 붙일 수 있다(`includeAncestorHeadings`). 파서를 바꾸는 것은 나중에도
되지만 "새로 들어오는 문서에만 적용"된다고 되어 있다.

### 4.2 제품별로 거를 수 없다

"지금 소개 중인 제품 문서만" 검색하려고 필터를 걸어 봤는데 전부 거부됐다.

| 시도한 필터 | 응답 |
|---|---|
| `uri: ANY("gs://…/DAON_LAB_Hydra_Barrier_Cream.pdf")` | 400 `Unsupported field "uri" on ":" operator` |
| `link: ANY("gs://…")` | 400 `Unsupported field "link"` |
| `id: ANY("<문서 ID>")` | 400 `Unsupported field "id"` |

공식 문서상 필터는 "구조화 데이터, 또는 메타데이터가 있는 비정형 데이터"에서 되고, 필드가 스키마에 색인 가능으로
잡혀 있어야 한다. 버킷에 PDF만 올리는 지금 방식에는 메타데이터가 없다. 스트리밍 커넥터로 메타데이터를 함께 넣는
방법이 있는지는 확인 안 함.

### 4.3 한국어 질문은 못 찾는다

"크림 용량이 얼마예요?"는 결과 0개였다. 문서가 영어라서다. 댓글 분류 단계가 이미 질문을 영어 한 문장으로 정리해
주므로(`canonical_question`), 검색어로는 그 문장을 쓰면 된다.

### 4.4 검색이 뽑아 주는 "요약 답"은 틀릴 수 있다

발췌 답변(`extractive_answers`)에서, 임신 중 사용 질문에 이런 문장이 답으로 뽑혔다.

> Yes. It is suitable for all skin types and all users.

문서의 "남성도 쓸 수 있나요?" 항목에 있는 문장이다. 이 기능을 그대로 시청자 답글에 쓰면 사고가 난다. 원문 조각만
가져와서 지금처럼 답변 작성과 검증을 거쳐야 한다.

## 5. 지금 코드가 실제로 어떻게 돼 있나

### 5.1 검색기

- `RETRIEVER=vertex_search`는 구현이 없다. `backend/app/context.py`에서 `NotImplementedError`를 던진다.
- 지금 검색기는 로컬 BM25 하나다(`backend/app/providers/retriever.py`, `LocalRetriever`).
- Vertex AI Search를 부르는 코드는 `backend/app/providers/rule_search.py` 하나뿐이고, 규제 규칙 ID를 고르는 실험용이다.
  제품 문서 검색에는 쓰이지 않는다.

### 5.2 댓글 답변의 근거는 문서 원문이 아니다

- 제품을 승인하면 "제품 기록"(가격, 용량, 성분, 사용법, 주의사항 등)이 만들어지고, `release_pack`
  (`backend/app/onboarding/release.py`)이 그 기록을 섹션별 문단으로 다시 쓴다. 검색기에 들어가는 것은 이 문단이다.
- 문단 ID는 `<제품코드>#<섹션>#<항목>` 형식이다. 예: `DL-CR-01#key-facts#live-broadcast-price`.
- 업로드한 원본 파일의 글은 검색기에 들어가지 않는다. 발화 사실 확인 쪽만 원본 파일을 통째로 읽는다.

### 5.3 답변 검증이 요구하는 것

`backend/app/logic/verify.py`의 `verify_answer`가 게시 전에 확인하는 것:

- 답변이 인용한 문단 ID가 답변 모델에 넘겨준 문단 목록에 있어야 한다.
- 인용문이 그 문단 글에 글자 그대로 들어 있어야 한다(공백과 대소문자만 무시).
- 문단의 제품이 질문의 제품과 같아야 한다.
- 답변 속 숫자가 전부 인용문 안에 있어야 한다.

그리고 섹션 이름이 코드 여러 곳에서 열쇠로 쓰인다: "Key facts", "Key ingredients", "How to use", "Cautions",
"In-house test results", "Approved on-air claims". 가격·용량 즉답(`logic/record_answers.py`)은 "Key facts" 문단만 본다.

그래서 검색을 통째로 데이터 스토어로 바꾸면 ID와 섹션 이름이 달라져 이 검증과 즉답이 깨진다.

### 5.4 Setup과 Onboarding

| | Setup (`/setup`) | Onboarding (`/onboarding`) |
|---|---|---|
| 하는 일 | PDF 업로드 → 섹션 분해 → 로컬 색인 교체 → 용어집·요점 초안 → 사람이 확정 | 파일 업로드 → 모델이 읽어 제품 기록 생성 → 사람이 확인·승인 → 릴리스 → brief 자동 생성 |
| 제품 연결 | PDF 안의 제품 코드로 기존 카탈로그에서 찾음. 새 제품은 못 만듦 | 업로드가 곧 새 제품 |
| 문서 형식 | 데모 문서의 8개 제목 형식만 이해 | PDF, 이미지, DOCX, XLSX, HTML 등 |
| GCS | "v1에서는 수동"이라는 문구만 있고 실제 업로드 없음 | `ONBOARDING_GCS_BUCKET`으로 백업·복원 (읽기는 로컬 폴더) |
| 실제 배포에서 | 카탈로그가 비어 있어 업로드가 `unknown_product_code`로 실패 | 동작함 |
| 결과가 방송에 반영되나 | 릴리스로 시작한 방송에는 거의 반영 안 됨 | 반영됨 |

brief를 만드는 에이전트와 프롬프트(`prompts/brief_agent.md`)는 두 곳이 같은 것을 쓴다. 입력과 한도, 사람 확인 여부만
다르다.

### 5.5 프롬프터와 brief 연동

- 릴리스를 승인하면 brief가 자동으로 돌고 `briefs/<release_id>.json`에 저장된다. 그 릴리스로 방송을 만들면 brief의
  요점이 프롬프터 요점이 되고, brief의 용어집이 STT 힌트로 들어간다.
- brief가 끝나기 전에 만든 방송은 예전 요점(승인된 문구)을 계속 쓴다.
- Onboarding의 brief에는 사람이 확인하거나 고치는 단계가 없다.
- Setup에서 확정한 용어집은 릴리스가 없는 세션의 STT에만 쓰인다.

### 5.6 로컬 디스크에 묶여 있는 곳

- 릴리스, brief, 규제 팩 목록을 전부 로컬 폴더 glob으로 읽는다. 버킷은 시작할 때만 내려받는다. 시작 뒤에 다른
  인스턴스가 승인한 릴리스는 보이지 않는다.
- Onboarding 작업 상태(`_jobs`)가 프로세스 메모리에만 있다. 재시작하면 읽기가 끝난 작업도 승인할 수 없다
  (`result.json`은 버킷에 있지만 다시 읽지 않는다).
- 검색기가 프로세스 전체에 하나이고 제품 ID로만 구분한다. 같은 제품의 다른 버전이나 다른 시장·언어 팩을 만들면 서로
  덮어쓰고, 그때마다 전역 문서 버전이 올라가 열려 있는 질문이 닫힐 수 있다.

## 6. 제안하는 검색 구조

```
질문 (영어로 정리된 문장)
   ├─▶ 제품 기록 문단            지금 방식 그대로. 가격, 용량, 성분, 주의사항
   └─▶ Vertex AI Search 청크     문서 원문. 기록 항목에 안 잡힌 내용 (FAQ, 보관법, 세부 설명)
            │  결과의 파일 주소가 products/<지금 제품의 키>/ 로 시작하는 것만 남김
            ▼
   두 근거를 합쳐 답변 모델에 전달 → 기존 검증 그대로
```

- **제품 기록 문단은 1차 근거로 남긴다.** 숫자는 여기서 나오게 해서 검증과 즉답이 그대로 동작한다.
- **청크는 추가 문단으로 넣는다.** 문단 ID는 `vs:<문서 ID>#<청크 ID>`처럼 겹치지 않는 형식으로, 섹션 이름은
  "Source document"처럼 기존 이름과 겹치지 않게 한다. 인용문 검증은 청크 글에 대한 부분 문자열 검사로 그대로 된다.
- **제품 구분은 경로로 한다.** 업로드할 때 `gs://ai-budiler-cup-uh-data-source/products/<제품키>/<파일명>`으로 저장한다.
  검색은 넉넉히 받아 온 뒤(예: 10개) 주소 앞부분으로 거른다. 메타데이터가 필요 없고 스트리밍 동기화와 그대로 맞는다.
  문서 수가 아주 많아지면 다른 제품 결과에 밀려 놓칠 수 있으니, 그때는 메타데이터 필터를 다시 검토해야 한다.
- **검색어는 `<제품 이름> <canonical_question>`.** 지금 로컬 검색도 같은 형태다.
- **발췌 답변과 요약 기능은 쓰지 않는다.** 원문 조각만 쓴다.
- **검색이 실패하거나 늦으면 제품 기록 문단만으로 답한다.** 검색 장애가 방송을 멈추지 않는다. 시간 제한은 1.5초 안팎을
  제안한다(시험 호출은 0.35~0.76초).
- **검색은 기록 조회와 동시에 돌린다.** 답글 시간이 검색 시간만큼 통째로 늘지 않게 한다.

요청 본문 예시(청크 모드):

```json
{
  "query": "Hydra Barrier Cream Can it be stored in a car?",
  "pageSize": 10,
  "contentSearchSpec": {"searchResultMode": "CHUNKS", "chunkSpec": {"numPreviousChunks": 0, "numNextChunks": 0}},
  "queryExpansionSpec": {"condition": "DISABLED"},
  "spellCorrectionSpec": {"mode": "SUGGESTION_ONLY"}
}
```

`rule_search.py`가 이미 쓰는 `relevanceThreshold: "LOWEST"`도 같이 검토할 것. HANDOVER.md에 "기본값은 관련도 낮은
결과를 버려서 'It cures eczema'가 0건이었다"는 메모가 있다.

## 7. 데이터 스토어를 새로 만들 때

| 항목 | 값 | 이유 |
|---|---|---|
| 파서 | 레이아웃 파서 | 제목, 표, 목록 구조를 살려서 자른다 |
| 청킹 | 켬. `chunkSize` 300~500 사이에서 측정으로 정함 | 4.1. 생성 후에는 못 바꾼다 |
| `includeAncestorHeadings` | true | 조각만 봐도 어느 절인지 알 수 있게 |
| 원본 | 같은 버킷 `ai-budiler-cup-uh-data-source`, 스트리밍 | 업로드만 하면 반영되는 지금 흐름 유지 |
| 검색 앱 | 부가 기능(LLM) 없이 | 요약·발췌 답변을 쓰지 않는다 |

확인이 필요한 것:

- GCS 커넥터로 스토어를 만들 때 청킹 옵션을 고를 수 있는지. 안 되면 일반 스토어를 만들고 업로드 때 가져오기를
  호출하는 방식으로 바꿔야 한다. 확인 안 함.
- Standard 등급에서도 청크 검색이 되는지. 확인 안 함.
- 올린 뒤 검색에 잡히기까지의 지연. 화면에 "검색 반영 대기 중 / 반영됨"을 보여 주려면 이 값이 필요하다. 확인 안 함.

버킷 루트에 있는 PDF 2개는 새 경로 규칙으로 다시 올려야 한다.

## 8. 비용

단가는 공식 가격표에서 검색으로 확인한 값이다. 가격 페이지 본문을 직접 열지는 못했으니 청구 전에 콘솔에서 다시 볼 것.

| 항목 | 단가 | 이 프로젝트 규모에서 |
|---|---|---|
| 데이터 스토어 생성·삭제 | 없음 | 0 |
| 문서 파싱 (레이아웃 파서, 첫 청킹 포함) | 1,000페이지당 $10 | 제품 문서 1개가 3~4쪽이면 문서 100개에 $3~4 |
| 다시 청킹 | 1,000페이지당 $0.02 | 무시할 수준 |
| 색인 저장 | GB당 월 $5, 10GB까지 무료 | PDF 몇 MB라 0 |
| 검색, Standard | 1,000회당 $1.50 | 질문 500개짜리 방송 1회에 $0.75 |
| 검색, Enterprise | 1,000회당 $4.00 | 같은 방송 1회에 $2.00 |
| 고급 생성 답변 부가 기능 | 1,000회당 +$4.00 | 쓰지 않음 |

드는 돈은 사실상 검색 횟수다. 240개 댓글 평가 세트를 한 번 돌리면 검색 약 170회, $0.3~0.7다.

## 9. 효과를 재는 방법

댓글 평가 세트 4번(`data/eval/comment_holdout4_*`, 240개)으로 "지금 방식"과 "합친 방식"을 같은 조건에서 나란히 잰다.
채점 스크립트는 `backend/scripts/eval_comment_holdout.py`.

볼 숫자:

- 답할 수 있는 질문에 검증된 답이 나온 비율. 10/9 flash-lite 기준 78~82%였고, 못 나온 것 중에 "문서에는 있는데 기록
  문단에서 못 찾은" 질문이 있었다("can i keep it in my car", "set only for today?" 등).
- 나가면 안 되는데 나간 답의 수. 늘면 안 된다.
- 댓글에서 답글까지 걸린 시간(p50, p95).

## 10. Onboarding과 brief(용어집·요점)를 하나로 합치는 방안

### 10.1 지금 흐름과 문제

```
[Onboarding]  업로드 → 기록 읽기(최대 10분 제한의 모델 호출) → 사람 확인 → 승인 ─┐
                                                                              ├→ 승인 뒤에 brief 자동 실행(약 30초), 확인 단계 없음
[Setup]       PDF 업로드 → 섹션 분해 → brief 실행 → 사람이 용어집·요점 확정 ────┘   (릴리스 방송에는 거의 반영 안 됨)
```

- 용어집과 요점이 **승인 뒤에** 만들어져서, 사람이 볼 기회가 없고 승인 직후 시작한 방송은 예전 요점으로 돈다.
- 같은 에이전트(`BriefAgent`, `prompts/brief_agent.md`)를 두 화면이 서로 다른 입력과 한도로 부른다.
- 사람이 확정한 결과(Setup)와 실제 방송이 쓰는 결과(Onboarding)가 서로 다른 곳에 저장된다
  (`SETUP/glossary`·`SETUP/overrides` 대 `briefs/<release_id>.json`).

### 10.2 합친 흐름

```
1. 업로드 (화면 하나, 여러 파일)
2. 서버가 버킷에 저장  products/<제품키>/<파일>          → 커넥터가 데이터 스토어로 동기화 (별도로 진행)
3. 한 작업 안에서 동시에 시작
   ├ (a) 제품 기록 읽기        가격, 용량, 성분, 사용법, 주의사항, 승인/비승인 문구
   ├ (b) 용어집 추출           원본 문서만 있으면 됨: 브랜드, 제품명, 성분, 기술 용어와 발음형
   └ (c) 요점 초안             원본 문서에서 4~10개
4. (a)가 끝나면 코드가 (c)에 덧붙임   프로모션 요점, 주의사항 요점 (지금의 BRIEF_OFFERS=code, BRIEF_CAUTIONS)
5. 사람이 한 화면에서 확인·수정      기록 / 용어집 / 요점 세 탭
6. 승인                              기록 + 확정된 용어집·요점이 한 릴리스로 저장됨
7. 방송 시작                         프롬프터와 STT 힌트가 그 릴리스에서 바로 나옴
```

핵심은 두 가지다.

- **brief를 승인 앞으로 당긴다.** 승인하는 순간 릴리스에 용어집과 요점이 이미 들어 있으니 "brief가 끝나기 전에 시작한
  방송" 문제가 없어진다. Hub의 "brief 실행 중" 안내와 2초 폴링도 필요 없어진다.
- **사람이 확정한 것이 곧 방송에 쓰이는 것이 된다.** 저장 위치를 릴리스 하나로 모은다.

### 10.3 병렬로 돌릴 수 있는 부분과 없는 부분

| 산출물 | 필요한 입력 | 기록 읽기와 동시에 가능한가 |
|---|---|---|
| 용어집 | 원본 문서의 글 | 가능. `post_validate`가 "문서에 글자 그대로 있는 용어만" 남기므로 기록이 필요 없다 |
| 요점 초안 (제품 설명, 사용법) | 원본 문서의 글 | 가능 |
| 프로모션 요점 | 기록의 `offers` (금액, 조건) | 불가. 기록이 나온 뒤 코드가 만든다 (`offer_points`) |
| 주의사항 요점 | 기록의 `cautions` | 불가. 기록이 나온 뒤 붙인다 (`_with_cautions`) |
| 요점의 제한 문구 검사 | 규제 규칙 | 기록의 카테고리가 정해진 뒤 |

지금 Onboarding의 brief 입력은 "기록을 문서처럼 다시 쓴 것 + 원본 글"(`release_document`)이다. 병렬로 하려면 brief 호출의
입력을 원본 글만으로 바꾸고, 기록에 의존하는 요점은 4단계에서 코드로 덧붙이면 된다. 이렇게 바꾸면 요점 품질이
달라질 수 있으니 `backend/scripts/eval_brief.py`로 전후를 재야 한다.

기록 읽기가 가장 오래 걸리는 호출이라, 용어집과 요점 초안은 그보다 먼저 화면에 뜬다. 사람이 기록이 나오기를
기다리는 동안 용어집부터 볼 수 있다.

### 10.4 저장 구조

| | 지금 | 합친 뒤 |
|---|---|---|
| 작업 상태 | 프로세스 메모리 `_jobs` (재시작하면 사라짐) | 저장소 문서 `onboarding_jobs/<job_id>`: 단계별 상태(업로드, 기록, 용어집, 요점, 동기화) |
| 기록 | `releases/rel_<키>_v<n>.json` | 같음 |
| 용어집·요점 | `briefs/<release_id>.json` (승인 뒤 자동) 과 `SETUP/glossary`, `SETUP/overrides` (사람 확정) | 릴리스 파일 안에 `brief: {glossary, points, confirmed_by, confirmed_at}` 한 곳 |
| 원본 파일 | 로컬 `<job_id>/<sha256>` + 버킷 백업 | 버킷 `products/<제품키>/<파일>`이 기준, 로컬은 캐시 |

릴리스는 지금처럼 한 번 쓰면 못 고치게 둔다. 용어집이나 요점을 고치고 싶으면 새 버전(`_v2`)을 승인한다. 방송 중에
요점이 바뀌는 일이 없고, 어떤 방송이 어떤 요점으로 돌았는지 남는다.

### 10.5 API

| 지금 | 합친 뒤 |
|---|---|
| `POST /onboarding/jobs` | 그대로. 응답에 단계별 상태 추가 |
| `GET /onboarding/jobs/{id}` | 그대로. `record`, `glossary`, `points`가 준비되는 대로 채워짐 |
| `POST /onboarding/jobs/{id}/preview` | 그대로 |
| `POST /onboarding/jobs/{id}/approve` | 본문에 확정한 `glossary`, `points` 추가 |
| `GET /onboarding/releases/{id}/brief` | 삭제 (릴리스에 들어 있음) |
| `/setup/documents`, `/setup/brief/*`, `/setup/glossary*` | 삭제 |

### 10.6 화면

- `/setup`과 `/onboarding`을 한 화면("제품 준비")으로 합친다. Hub의 "Before the show" 카드가 이 화면으로 간다.
- 진행 표시는 단계 네 개면 된다: 업로드됨 → 읽는 중(기록 / 용어집 / 요점 각각) → 확인 → 승인됨. 여기에 "검색 반영 대기 중 /
  반영됨" 표시 하나.
- 확인 화면은 탭 세 개: 제품 정보(지금의 `RecordReview`), 용어집(지금 Setup의 `GlossaryTable`), 방송 요점(지금 Setup의
  요점 편집). 두 화면의 부품을 그대로 옮겨 쓸 수 있다.
- 화면에 나오는 내부 용어("release", "brief", "lawpack")는 "제품 등록", "방송 요점", "규제 문서"처럼 바꾼다.

### 10.7 없앨 수 있는 코드

- `backend/app/pipelines/setup.py`의 업로드·섹션 분해·로컬 색인 교체 부분(데모 문서 형식 전용 파서 포함). 다만
  `parse_sheet_text`는 `scripts/build_local_index.py`와 테스트용 데모 팩을 만드는 데 쓰이니 그쪽은 남긴다.
- `SETUP/glossary`, `SETUP/overrides`와 그것을 세션에 복사하는 코드(`create_session`의 `prompter_overrides`,
  `Session.glossary_version`).
- `api/onboarding.py`의 `_brief`, `_briefs`, `brief_status`와 Hub의 brief 폴링.
- 설정 `GCS_BUCKET`(문구에만 쓰임).

테스트는 `test_setup.py`, `test_setup_session.py`, `test_brief.py`와 `test_onboarding.py`의 d265·d266(승인 시 brief,
brief 전에 시작한 방송) 부분이 바뀐다.

### 10.8 같이 고치면 좋은 것 (5.6)

- 릴리스 목록을 로컬 glob이 아니라 버킷이나 DB에서 읽기. 그래야 다른 인스턴스가 승인한 제품이 보인다.
- 검색기를 세션(쇼) 단위로 나누기. 지금은 전역 하나라 같은 제품의 다른 버전이 서로 덮어쓴다.

### 10.9 순서 제안

1. 데이터 스토어를 새 설정으로 만들고 버킷 경로 규칙을 정한다 (7장).
2. brief 호출을 원본 글 입력으로 바꾸고 기록 의존 요점을 코드로 분리한다. `eval_brief.py`로 전후 비교.
3. 작업 상태를 저장소로 옮기고, 한 작업에서 세 호출을 동시에 시작한다.
4. 승인 본문과 릴리스 파일에 용어집·요점을 넣는다. 프롬프터와 STT 힌트가 릴리스에서 읽도록 바꾼다.
5. 화면을 합친다. Setup 쪽 코드와 API를 지운다.
6. 검색을 붙이고 (6장) 댓글 세트로 잰다 (9장).

## 11. 참고

- Parse and chunk documents: https://docs.cloud.google.com/generative-ai-app-builder/docs/parse-chunk-documents
- Filter search with metadata: https://docs.cloud.google.com/generative-ai-app-builder/docs/filter-search-metadata
- Agent Search (Vertex AI Search) pricing: https://cloud.google.com/generative-ai-app-builder/pricing
- Document AI pricing: https://cloud.google.com/document-ai/pricing
- 댓글 흐름과 측정 결과: `docs/comments.md`
- 저장 구조: `docs/comments-firestore.md`
