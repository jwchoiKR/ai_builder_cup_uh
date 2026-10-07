# 세션 인계 (10/6 새벽 기준)

새 세션은 이 문서부터 읽는다. 결정 기록은 `docs/PLANNING.md` 8장, 기술 결정은 `docs/DECISIONS.md`(D-번호), 측정값은 `docs/eval/proof-plan.md`에 있다.

## 0. 10/6 오후 기준 (업무 노트북, 이 절부터 읽는다)

- **새 사용자 규칙 (10/6):** 오경고 1% 미만, 탐지 95% 이상, 잘못된 HIGH 0을 **제품마다** 모두 넘어야 합격이다. 개선은 보고 후 바로 진행하되, 판단은 혼자 하지 않고 GPT·Gemini·Sonnet과 함께 한다. 이전 제품의 데이터를 런타임 바탕에 남기지 않는다(깨끗한 바탕). 한 방송 여러 제품은 범위에 넣는다(세트가는 제외).
- **비용:** 이틀 동안 Gemini 약 40만 원이 나왔다. 거의 전부 라이브 판정 측정의 Flash-Lite 입력 토큰(3일 10억 토큰)과 보조 요청 때문이다. 하루 예산이 정해질 때까지 대량 측정을 멈췄다. 다시 돌릴 때는 문장당 1회, 병렬 2, `HEDGED_AGENTS=compliance`로 하고 예상 토큰을 먼저 보고한다.
- **측정 VM:** `live-studio-eval`(us-central1-a, 외부 IP 없음, IAP SSH)은 지금 정지 상태다. 봉인 세트와 코드 묶음은 비공개 버킷 `separk-cloocus-live-studio-eval`에 있다. 노트북 네트워크는 판정 호출의 40% 이상이 시간 초과라서 라이브 측정은 VM에서만 한다.
- **봉인 세트(이 노트북):** `C:\code_test\study\ai_builder_cup_git\sealed_sets\`. 오늘 4차(진단용), 5차(새 세트, 고정 후보로 한 번만), 여러 제품 세트(M1), 4차 댓글 세트, 5차 인증 세트(제품당 정상 300·위험 60, 작성 중)를 만들었다.
- **오늘 결과(깨끗한 바탕):** 4차 처음부터 측정은 탐지 91.0%(규정 100, 사실 88.2, 시험 단서 70.8), 오경고 3.1%, 잘못된 HIGH 1이었다. 가장 약한 제품은 83.3%다. 놓친 사실 오류 115건 중 81건은 검증 코드가 맞는 판정을 지운 것이고, 모델이 놓친 것은 3건이다.
- **만들었고 측정 대기:** `FACT_FIXES`(F1~F5, R1, Q1E, Q1T, Q2~Q5), `HEDGED_AGENTS`, `REFLEX_ON_FAIL=card`. 기본으로 켜진 것은 댓글 용량 구분(C1/C2), 여러 제품 방송, 데모의 승인본 전환이다.
- **다음(예산 확정 후):** 수정 묶음 켬/끔 비교, 여러 제품 세트, 댓글 수정 전후, 고정 후보로 5차 한 번, 인증 세트. 재작성 기준(세 모델 합의)은 5차에서 사실 탐지 90% 미만이고 놓침의 절반 이상이 코드 삭제면 사실 검증 부분만 다시 만든다는 것이다.

## 1. 누가 무엇을 하나

| 역할 | 누구 | 하는 일 | 하지 않는 일 |
|---|---|---|---|
| 결정 | 사용자 | 설계·범위 결정, 배포 승인 | |
| 기획·평가 | Claude 세션 (ai-builder-cup-uh-d3) | 기획, 시험 데이터, 봉인 세트, 평가 실행, 문서, 덱, 모델 토론 조율 | 앱 코드 작성 |
| 개발 | Claude 세션 (ai-builder-cup-uh-00) | 앱 코드 전부, 테스트, 커밋 | push (사용자가 직접 지시할 때만), 봉인 세트 열람 |
| 비평 | Claude Sonnet 5.5 세션 (ai-builder-cup-uh-38) | 읽기 전용 반박, 블라인드 정답 매기기 | 코드 수정 |
| 토론 | codex, agy | 설계 반박, 시험 문장 작성, 화면 검토 | |

**codex와 agy는 모델을 명시해서 부른다.** 설정 파일 기본값이 바뀐 적이 있다(10/5, `gpt-6.1-sol` low).
- `codex exec -m gpt-6-astra -c model_reasoning_effort=high -s read-only - < brief.md`
- `agy --model gemini-3.8-flash-high -p "$(cat brief.md)"` (agy는 파일 읽기가 막히니 내용을 프롬프트에 넣는다)
- codex 결과를 쓰기 전에 stderr 첫 줄의 `model:`과 `reasoning effort:`를 확인한다.

## 2. 사용자 규칙 (꼭 지킨다)

- 답은 한국어로 한다. 모델이나 다른 세션이 영어로 써도 마찬가지다.
- 내부 시험은 100%가 목표다. 음성 게시 기준은 "모든 실행에서 잘못 게시 0, 놓친 게시 0, 중복 게시 0"이다.
- 봉인 세트는 라운드마다 새로 만들고 개발 쪽에 보여 주지 않는다(5장).
- 설계는 의견으로 정하지 않는다. 방향이 여럿이면 전부 만들어 같은 시험으로 비교하고 고른다. 사용자 제안도 후보 하나로 넣는다.
- 사용자 아이디어는 의견 하나로 본다. 목표는 지키고, 방법은 결과가 좋은 쪽으로 고른다.
- 시청자 질문은 제품 정보에 답이 있으면 게시(종류에 따라 진행자 카드)하고, 없으면 운영자에게 보낸다. 이 원칙으로 풀리는 일은 사용자에게 묻지 않는다.
- 커밋과 push는 작업이 끝날 때마다 한다. push 전에 키 패턴을 검사하고(`sk-or-`, `AIza`, `PRIVATE KEY`, `"private_key"`, `ya29.`), 강제 push는 하지 않는다.
- 덱과 설명용 HTML은 `docs/decks/`에 둔다(빌드 스크립트는 `build/`, 이미지는 `img/`). 사용자가 요청하지 않으면 Artifact로 올리지 않는다.
- 배포는 사용자 승인 뒤에만 한다. Claude Code 자동 권한 검사가 세션의 배포를 막으므로, 사용자가 `! bash deploy/cloudrun.sh`로 직접 실행한다.
- 크롬은 사용자가 쓰고 있으니 건드리지 않는다. 화면 캡처는 Playwright(Edge, headless)로 한다.
- `.env`와 키는 커밋하지 않는다. OpenRouter 키는 지웠고 다시 넣지 않는다. 에이전트 권한·설정 파일은 고치지 않는다.
- 기획, 시험 설계, 결과 해석, 로직 검토 때마다 심사위원 시점을 적는다: 심사위원이 지적할 약점과, 점수를 올리려면 바꿀 것 (사용자 10/5).
- 수동 절차는 설계 결함이다. 고객에게 문서 틀을 맞추라고 하지 않고, 어떤 형식이든 우리가 맞춘다. 사람은 승인만 한다.
- 시험 결과는 우리 앱 로직(코드와 앱이 직접 부르는 Gemini)만으로 낸 것만 인정한다. 실행 중에 다른 LLM이나 사람이 고치거나 돕지 않는다. 다른 모델은 시험 데이터와 정답을 미리, 블라인드로 만드는 데만 쓴다. 직접 Gemini를 부른 스크립트 결과는 '방법 탐색'으로만 표시한다 (사용자 10/5).
- 목표는 범용 플랫폼이다: 처음 보는 어떤 제품(브랜드·카테고리·문서 형식·언어)에서도 100%. 지금 두 제품(DAON 크림·앰플)에 맞춘 프롬프트 예시, 코드 규칙, 규정 예외 문구는 허용하지 않는다. 제품은 자동 등록으로만 들어온다. 시험은 여러 제품 묶음으로 하고, 개발 쪽은 조정용 제품 묶음으로 다듬고, 합격 여부는 봉인 제품 묶음으로 정한다 (사용자 10/5 밤).
- 성능은 제품 정보를 넣거나 고쳐서가 아니라 코드와 LLM 로직(제품 내용 없는 프롬프트, 작업 분해, 근거 연결, 검증, 재시도, 모델·생각 수준 선택)으로 올린다. 정답 수정은 정답이 정말 틀렸을 때만, 다른 모델의 독립 확인을 거쳐 하고, 로직 개선과 따로 보고한다 (사용자 10/5 밤).
- 우리 로직으로 시험해서 목표 성능이 안 나오면 붙잡지 않고 버리고 새로 만든다. 시험 전에 중단 기준(합격선, 수정 횟수 1~2회)을 정해 둔다 (사용자 10/5: "안되는거 붙잡지마").
- 배포 링크 로그인(IAP)은 나중에 없앤다 (사용자 10/5). 심사위원이 바로 열 수 있어야 한다.
- 일정·영상·덱 마감 이야기는 사용자가 먼저 꺼내기 전에는 하지 않는다.

## 3. 지금 상태

- 브랜치 `multi_agent_test`. 코드 최신은 개발 세션의 D-260(947084e)까지다(10/6 새벽 기준 push 여부는 `git log origin/multi_agent_test`로 확인).
- **클라우드:** Cloud Run `live-studio-us` 00009-qcf = 이미지/코드 41411fd (10/6 아침 사용자 배포). `/api/health` 정상, 사실 확인 Flash-Lite LOW. 클라우드에서 FD 컨텍스트 캐시는 아직 제품을 올려 확인하지 않았다. STORE=memory라 재시작하면 올린 제품·릴리스가 사라진다.
- **10/6 밤 기본 구조 (측정으로 결정):**
  - 사실 확인: `FACT_MODE=docs`(FD). 등록 기록 + 원본 파일(방송 시작 때 컨텍스트 캐시). Flash-Lite LOW, 사실 마감 5초, 규정 경고 3초.
  - 자동 등록: Gemini 3.8 Flash로 통째로 읽기 + 주의·한계 다시 읽기 + 칸 재분류 + 카테고리(닫힌 목록, 대상 연령은 따로) + 누락 점검, 코드가 숫자 단어·묶음 계산·근거 확인. `VERIFY_MODE=lean`(사람이 볼 항목 최대 10개).
  - 규정: 시장 팩 + 규제 원문으로 만든 규정 팩(D-229, 식품은 HSA·MOH 원문 19개) + 브랜드 팩.
- **처음 보는 제품 결과 (봉인, 6개 × 36줄 × 3회):** 상세는 `docs/eval/proof-plan.md` 끝부분.
  - 1차 봉인(밤새 실패를 보며 고친 세트): 61~89% → 93.2% (후보 3).
  - 2차 봉인(처음 보는 6개): 72.5% (후보 1) → 84.3% (후보 4) → 83.0% (후보 5).
  - **3차 봉인(새 6개, 한 번만 잼, 대표 숫자): 84.6% (후보 5 fbb8aa7).** 3차 세트에서 찾은 코드 버그를 고친 뒤(809adbf) 86.7%(따로 보고).
  - 자동 등록: 두 세트 모두 상품·거버넌스·안전·혜택 통과(안전은 Sonnet 뜻 채점).
- **아직 합격선(처음 보는 제품 100%) 미달.** 남은 것은 대부분 코드가 맞는 판정을 지우는 경로와 조건·버전 처리다. 개발 세션은 drop 이유를 행마다 남긴다(`row["dropped"]`).

## 4. 설계 후보 비교 (결정됨)

- A~F 구조 비교(10/5): A(판정 AI + 게시 직전 코드 확인)가 이겼다. D·E는 잘못 게시로 탈락. `docs/eval/design-arms.md`.
- 사실 확인 방식(10/6): 요약본(sheet) < 등록 기록(FR) < 기록 + 원본 파일(FD). FD 채택(시험 전 기준: FR + 2%p).
- 사실 확인 모델·마감(10/6): Flash-Lite MINIMAL/LOW 차이 없음, 3.8 Flash는 느려서 탈락. 마감 5초.
- Gemini Live는 사용자 요청으로 나중에 후보로 시험한다.

## 5. 봉인 세트와 시험 실행

- **봉인 세트:** `D:\code_test\study\ai_builder_cup_git\sealed_sets\` (레포 밖, README 있음). 개발 세션에 보여 주지 않는다.
  - `onboarding/` 1차(P1~P9 문서, live_P1~6), `onboarding2/` 2차(Q1~Q6, live_Q1~6). 채점 `rescore_live.py --main --patch --rule-map`(라벨 보정은 LABEL_CHANGES.md), 등록 채점 `onboarding/score_groups.py`, 승인 `approve_sealed.py`, FD 원본 파일 `store_files.py`.
  - 2차 세트 Q1은 말레이시아 상품이라 `MARKET=MY`로 승인·측정한다.
- **시험은 별도 worktree에서 돌린다.** 기본 작업 트리를 건드리지 않기 위해서다.
  - `injtree`: A·B·C 평가용
  - `armtree`~`armtree4`: D, F2, F1, E 평가용
  - `demotree`: mock 서버 :8002, 화면 확인용 vite :5180
  - `deploy158`: 개발 세션용. 건드리지 않는다.
  - 새 worktree를 만들면 `.env`를 다른 worktree에서 복사한다(OpenRouter 키 없음 확인).
- **한 후보 전체 시험:** `injtree/run_arms.ps1 -Arms A,B` (backend에서 `uv run python scripts/...`)
  - `eval_adversarial.py --runs 3 --cases <봉인 절대경로>`: 진행자 말 판정. 합격선은 탐지 99% 이상, 오경고 4.2% 이하, 안전 문장 빨간 경고 0
  - `eval_verbal_post.py --runs 3 [--cases ...]`: 말로 한 답 게시. 잘못 0, 놓침 0
  - `eval_draft_verifier.py --cases <봉인> --llm --runs 3`: 나쁜 답 게시 0, 좋은 답 차단 3% 이하
  - `run_eval.py comments --runs 2`, `eval_comment_flow.py --runs 2 --cases comment_flow_cases.jsonl`: 댓글 분류·흐름 100%
  - `eval_ai_pd.py --cases <봉인> --arms gemini-3.8-flash:LOW --paths adk --runs 3`
- **클라우드 리플레이:** `frontend/e2e/show-replay.mjs <SEED.json> --assistant on|off`(IAP 토큰 `deploy/iap-token.sh`, BASE는 Cloud Run 주소), 지연 시험은 `frontend/e2e/rehearsal-voice.mjs lines ../data/eval/latency_lines.jsonl 1`.
- **한글 출력이 깨지면** `PYTHONIOENCODING=utf-8`을 붙인다.

## 6. 클라우드 자원 (프로젝트 separk-cloocus만)

- **Cloud Run** `live-studio-us`(us-central1, min-instances 0, max 1, IAP는 jaewoo@cloocus.com만). 배포 스크립트는 `deploy/cloudrun.sh`.
- **STT** chirp_3, region `us`. 아시아 리전에서는 쓸 수 없다.
- **Gemini:** global 엔드포인트만 된다.
- **Model Armor** 템플릿 `live-studio-comments`(us-central1).
- **Firestore** `live-studio`(us-central1): 비어 있다. 배포가 `STORE=memory`라 방송 데이터는 메모리에만 있다. 기록은 Cloud Logging에서 읽는다.
- **Vertex AI Search** (10/5 사용자 승인, 후보 E용): 데이터 저장소 `live-studio-rules`(규칙 38개), 엔진 `live-studio-rules-engine`.
  - 설정: `relevanceThreshold LOWEST`, `pageSize` 5~10, `market` 필터, 연결 재사용
  - 만들기·조정 스크립트: `D:\code_test\study\ai_builder_cup_git\ops_scripts\`
  - 배포된 E를 쓰려면 Cloud Run 서비스 계정에 Discovery Engine 뷰어 권한이 필요하다(사용자 승인 필요).
- **gcloud:** 로그인이 만료되면 사용자가 `! gcloud auth login`을 실행한다.

## 7. 남은 일

0. **처음 보는 제품 합격선까지 (지금 약 84%):** 남은 유형은 proof-plan 마지막 항목. 2차·3차 세트도 이제 본 세트라, 다음 판정용 4차 봉인 세트를 새로 만든다(코드: `sealed_sets/onboarding2/` 만든 방식 그대로, codex 작성 + Sonnet 블라인드).
1. 자동 등록 품질: 말레이어로만 남은 주의, 부풀려진 주의 목록, 깨진 금지 주장 문구, 확인 목록에 남은 구버전 값.
2. Gemini Live 설계 후보 (사용자 10/6: 나중에 시험).
3. 사람 진행자 방송 1회, 실제 음성으로 지연 측정.
4. 점수 올릴 항목(레포 재비교 + codex 검토): Firestore 저장·재시작·동시 실행, 방송 1시간 비용 실측, "Gemini 단독" 대비표.
5. 배포(사용자 승인), 로그인 제거(사용자).
6. 문서: `docs/decks/old/team_update_1006.html`(간단), `docs/decks/old/workflow_detail.html`(상세 워크플로, 시험 전부), `docs/research/repo-rescore-1006.md`.

## 8. 팀 역할 분담 (사용자 안, 10/5)

- **개발 리드(사용자):** 설계 결정, 개발 AI 지휘, 병합, 배포 승인
- **진행자 테스트(팀원 1):** 직접 방송하며 실수를 섞어 말하고 경고·시간·사용성을 기록, 녹음 남기기
- **워크플로·성능 검증(팀원 2):** 봉인 세트 작성·검수, 후보 비교·클라우드 시험, 결과 기록, 녹음을 재생 시험으로 만들기
- 봉인 세트는 검증 담당만 본다. 개발 AI 지시는 개발 리드 한 창구로 모은다.
