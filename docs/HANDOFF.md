# 개발 인계 (10/5)

10/5부터 역할을 나눈다.
- **개발**: 새 Claude 세션
- **기획 세션(Claude)**: 기획, 데이터, 문서 검색, codex·agy 호출
- 기획과 결정은 `docs/PLANNING.md`, 기술 결정은 `docs/DECISIONS.md`에 기록한다.

브랜치는 `multi_agent_test`이다. 아래 변경은 아직 **커밋하지 않았다**.

## 1. 지금 작업 트리의 변경 (누가, 상태)

| 묶음 | 파일 | 만든 사람 | 상태 |
|---|---|---|---|
| 라우터 실험 (Jev, Gemini) | `backend/scripts/eval_routing.py`, `backend/scripts/experiments/{jev_router,gemini_router}.py`, `experiments/prompts/router_purpose.md`, `backend/scripts/eval_agents.py`(jev/gemini 구조), `tests/test_{jev_router,gemini_router,eval_agents_jev,eval_routing_experiments}.py`, `docs/eval/routing-accuracy.*` | codex, Claude | 검증 완료. 운영 경로에는 쓰지 않는다 (PLANNING 3.1). 커밋 여부는 결정 필요 |
| 평가 데이터 | `data/eval/route_cases.jsonl`(40), `holdout_cases.jsonl`(100), `holdout_sequences.jsonl`(12 시나리오, 34턴) | agy, Claude가 라벨 수정·검증 | 검증 완료 (ID·규칙·팩트 값·기존 문장 유사도) |
| 연속 발화 동시 처리 (D-101) | `backend/app/pipelines/utterances.py`, `tests/test_utterance_concurrency.py`, `tests/test_utterance_pipeline.py` | codex, Claude가 테스트 기대값 2개 수정 | 검증 완료: AI PD 연결 전 전체 435개 통과, 동시성 테스트 5회 반복 통과 |
| ADK 의존성 | `backend/pyproject.toml`, `backend/uv.lock` | Claude | google-adk 2.11. ADK 2.x가 OpenTelemetry 1.42 이하를 요구해 FastAPI를 `>=0.133,<0.142`(0.141.1)로 고정, websockets 16.1 → 15.0.1. 435개 통과 확인 |
| AI PD 백엔드 | `backend/app/logic/pd.py`, `backend/app/agents/ai_pd.py`, `backend/app/pipelines/pd.py`, `prompts/ai_pd.md`, `backend/app/models/session.py`(`PdCard`, `Session.pd_card`), `backend/app/pipelines/runtime.py`(`self.pd`, `emit` 훅, `tick_locked` 훅), `backend/app/api/operator.py`(`POST /pd/dismiss`), `backend/app/ids.py`(`pd_` 접두어), `tests/test_pd.py` | Claude | **버그 있음 (2장).** `tests/test_pd.py` 단독은 통과했으나 연결 후 전체 테스트가 끝나지 않음 |
| AI PD 진행자 카드 | `frontend/src/app/{types,sse,state,selectors,api}.ts`, `state.test.ts`, `screens/host/{PdCard.tsx,HostScreen.tsx,host.module.css,host.test.tsx}`, `src/test/fixtures.ts` | agy | **미검증.** `npm test`, `npm run build` 필요 |
| 명시적 캐싱, 제품 문서 통째로, 처음 보는 문장 채점기 | `backend/app/providers/{llm,prompts}.py`, `backend/app/agents/{fact_checker,split_judges,utterance_judge}.py`, `backend/app/config.py`, `backend/scripts/{run_eval,eval_expectations,eval_holdout_sequences}.py`, `tests/test_{context_cache,full_sheet_facts,eval_holdout}.py` | codex | **구현 완료, 미검증** (codex 샌드박스는 Python을 못 돌림). 캐싱 기본값은 꺼짐(`LLM_CONTEXT_CACHE=false`), 측정 후 켠다. 공식 문서상 Gemini 3 계열 캐시 최소 길이는 4,096토큰이라, 고정 부분이 짧은 에이전트는 캐시되지 않는다. 캐시 TTL은 런시트 계획 시간. 실행: `uv run python scripts/eval_agents.py --cases holdout --structure split3 --runs 1`, `uv run python scripts/eval_holdout_sequences.py --runs 1` (보고서 `docs/eval/holdout-*`). 연속 시나리오의 지연은 STT와 화면 렌더링을 뺀 값이다 |
| 기획 문서 | `docs/PLANNING.md`, `docs/DECISIONS.md`(D-101), `docs/HANDOFF.md` | Claude | |

## 2. 알려진 문제

**AI PD 연결 후 `uv run pytest -q`가 끝나지 않는다** (평소 약 10초, 10분 넘게 멈춰 중단함).
- 가장 유력한 원인: `backend/app/pipelines/pd.py`의 `_decide`.
  - `st.now - self._last_decision_at < MIN_GAP_MS`이면 `self._again = True`로 두고 반환한다.
  - `_loop`는 `_again`이 켜져 있으면 바로 다시 `_decide`를 부른다.
  - 테스트의 `ManualClock`은 시간이 흐르지 않으므로 무한 반복한다. `scheduler.idle()`도 영원히 기다린다.
- 고치는 방향: MIN_GAP에 걸리면 `_again`을 켜지 말고 그냥 반환한다. 실제 운영에서는 1초 타이머(`tick_locked` → `pd.on_tick`)가 다시 부른다.
- 같은 시각에 codex가 위 1장의 파일을 수정 중이었으므로, 고친 뒤에도 멈추면 codex 변경 쪽도 확인한다.

## 3. AI PD 설계 요약 (상세는 PLANNING 5.1, 5.1.1)

- 판정 에이전트 3개(법률·팩트·맥락)는 STT 최종 문장마다 항상 동시에 호출한다. 빨간 경고와 팩트 메모는 AI PD를 거치지 않는다.
- AI PD는 이벤트(`transcript.final`, `prompter.updated`, `hostqueue.updated`, `group.updated`, `promo.*`, `segment.started`, `alert.*`)와 1초 타이머로 판단한다.
- 후보 카드는 `logic/pd.py`의 `candidates()`가 만든다. 문장은 검증된 것만 쓴다(추천 답변, 프롬프터 포인트, 프로모션 문구). LLM은 후보 id 하나 또는 "none"만 고른다.
- 실제 모드(`LLM_PROVIDER=vertex`)에서는 ADK `LlmAgent`(`agents/ai_pd.py`, 지시문은 callable로 넘겨 JSON 중괄호 치환을 막음)가 고르고, 실패하면 규칙(`rule_pick`)으로 고른다. mock 모드는 규칙만 쓴다.
- 카드는 15초 고정, 빨간 경고 중에는 새 카드를 만들지 않는다. 완료 조건은 포인트 언급·질문 답변·프로모션 종료·제품 전환이다. 진행자는 N 키로 넘기고(`POST /api/sessions/{sid}/pd/dismiss`), 넘긴 주제는 그 제품에서 다시 나오지 않는다.
- 프론트 계약: SSE `pd.card`(카드 또는 null), `/state`의 `session.pd_card`.
- 아직 안 한 것: 세 판정 에이전트를 ADK `ParallelAgent`로 감싸 루트 오케스트레이터 아래에 두기 (PLANNING 5.1.1).

## 4. 남은 개발 작업 (우선순위 순, 상세는 PLANNING 5.2)

1. 2장 버그 수정 → 백엔드 전체 테스트, 프론트 `npm test`·`npm run build`, `npm run e2e`
2. codex의 캐싱·채점기 결과 검증 (기획 세션이 codex 결과를 받아 전달)
3. 1인 모드: 운영자에게만 가던 민감 질문·미검증 답변 초안을 "보류"로 표시, 진행자 화면에서 방송 시작·종료, 프로모션 켜기, 제품 전환 수락
4. 세 판정 에이전트를 ADK 루트 오케스트레이터 아래로 (ParallelAgent 또는 ADK 2.x 워크플로)
5. 처음 보는 문장 평가 실행(기획 세션이 실행·기록), 업무량 집계, 실측 비용표
6. Vertex AI Search: PDF 파싱만. pypdf와 표 추출 품질 비교 후 결정. 데이터 스토어 `daon-product-sheets`(separk-cloocus, global)는 만들어 두었다
7. Cloud Run 배포, Firestore 전환

## 5. 실행 환경 메모

- `.env`(git 제외): `GCP_PROJECT=separk-cloocus`, `OPENROUTER_API_KEY`(Jev 실험용. 운영에서 쓰지 않는다. 노출된 키라 실험 후 폐기·재발급 필요).
- 데모 서버: 기획 세션이 마지막 커밋(HEAD)을 별도 worktree에 꺼내 `http://localhost:8000`에 띄워 두었다 (작업 트리 변경과 무관).
- Windows PowerShell 5의 `Set-Content -Encoding utf8`은 BOM을 붙인다. Python 파일 수정에는 쓰지 않는다.
