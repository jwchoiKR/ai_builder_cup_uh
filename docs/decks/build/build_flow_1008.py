"""Live logic flow with example data (10/8 night): what each step gets and returns, where it fails today.
Run: python docs/decks/build/build_flow_1008.py   (examples use the public demo product; JSON shapes are the real ones, values made up)"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401

OUT = Path(__file__).parent.parent / "flow_1008.html"


def code(*lines):
    """A small grey box of real field names with example values."""
    body = "<br>".join(lines)
    return (f'<div style="background:{SURF}; border:1px solid {LINE}; border-radius:14px; padding:14px 18px; '
            f'font-family:Consolas,monospace; font-size:23px; line-height:1.45; color:{INK}">{body}</div>')


slide("all", "전체 흐름", "진행자 말 한 줄이 화면 경고가 되기까지", col(
    lanes(stage("방송 중 한 줄 (예: 데모 크림 방송)"),
          (node("person", "진행자 말", "브라우저 마이크"), node("ai", "STT", "STANDARD · 단어 힌트", use="chirp_3"),
           node("code", "질문 보류", "질문이면 다음 줄과 함께", "최대 2.5초"),
           stack(node("ai", "규정 판정", use="생각 MEDIUM"), node("ai", "사실 확인 v5", use="생각 LOW"),
                 node("ai", "맥락 판정", use="생각 MINIMAL")),
           node("code", "흐름 처리", "경고 ID 부여 · 정정 연결", "전환 · 5초 격상"),
           stack(node("screen", "진행자 화면", "경고 · 프롬프터"), node("store", "Firestore", "live-studio")))),
    tags("판정 셋", chip("Gemini 3.5 Flash-Lite, 셋이 동시에", "blue", "ai"), chip("seed 7", "grey"),
         chip("코드는 글자 비교 없음 (D-353)", "green", "check")),
    gap=18),
    notes="설정: JUDGE_ARM=single, FACT_PROMPT=v5, QUESTION_HOLD=true, SWITCH_MODE=immediate, CORRECTION_CHECK=judge, REFLEX_SCAN=false, "
          "STORE=firestore(측정 중). 판정 셋은 같은 줄을 동시에 받는다.")

slide("alert", "① 위반 경고", "위반 한 줄은 경고 하나가 되고, 경고마다 ID가 붙는다", col(
    flows(
        (says("진행자", "This cream cures eczema in three days.", "(이 크림 3일이면 아토피 나아요.)"),
         ai("규정 판정 출력", "violations: rule ASEAN-2D-DISEASE, HIGH, span \"cures eczema\""),
         result("HIGH 경고<br><span style='font-size:24px'>ID al_01M3…7WW · 말 끝나고 약 2초</span>", "red")),
        gap=18),
    rowx(fx(code("규정 판정이 받는 것", "UTTERANCE: \"This cream cures eczema…\"", "RULES: 제품 규정 팩", "ACTIVE_ALERTS: 지금 떠 있는 경고")),
         fx(code("규정 판정이 내는 것", "reason: \"…\"", "correction: {corrects_alert_ids: []}", "compliance: {violations: [...]}")), gap=20),
    gap=22),
    notes="경고 ID는 코드가 붙인다(al_ + 26자 ULID). 5초 안에 정정이 연결되지 않으면 같은 ID로 격상된다. 예시는 데모 제품, 값은 지어냄.")

slide("fix", "② 정정 (지금 실패하는 곳)", "모델은 정정인 줄 아는데, 어느 경고인지를 비워서 해제가 안 된다", col(
    flows(
        (says("진행자", "Sorry, I shouldn't have said it cures eczema.", "(죄송해요, 아토피가 낫는다고 하면 안 되죠.)"),
         ai("규정 판정 출력 (실제 모양)", "reason: \"Host explicitly retracts the previous eczema claim.\""),
         result("corrects_alert_ids: []<br><span style='font-size:24px'>경고 그대로 · 5초 뒤 격상</span>", "red")),
        gap=18),
    rowx(fx(code("모델이 받은 목록", "ACTIVE_ALERTS: [", "  {alert_id: \"al_01M3251N8MBJQ64M7Y6N3FYYWW\",", "   span: \"cures eczema\", rule: ASEAN-2D-DISEASE}]")),
         fx(code("고칠 방법 (검토 중)", "ACTIVE_ALERTS: [{handle: A1, span: \"cures eczema\"}]", "출력: [{handle: A1, fixed_by_this_line: true}]", "코드가 A1 → 실제 ID로 바꿈")), gap=20),
    tags("측정 (정상 흐름 3편)", chip("정정 해제 1/3", "red", "x"), chip("단서 다시 말하기 해제 0/3", "red", "x"),
         chip("이유 칸에는 정정이라고 씀", "yellow", "warn")),
    gap=20),
    notes="원인 후보 둘: 모델이 ID 칸을 비웠거나, 긴 ID를 틀리게 옮겨 적어 utterance_judge.py:412가 기록 없이 버렸다. 짧은 이름(A1)과 경고별 예/아니오로 둘 다 해결. "
          "GPT·Gemini·Sonnet 검토 중.")

slide("qual", "③ 단서 배너", "시험 결과를 출처 없이 말하면 배너, 출처를 붙여 다시 말하면 해제", col(
    flows(
        t("배너가 뜨는 경우", 28, "#B06000", 700),
        (says("진행자", "Skin hydration goes up 45% after one use.", "(한 번 쓰면 수분이 45% 올라가요.)"),
         ai("규정 판정", "TEST-QUALIFIER, MEDIUM"), result("배너: 결과의 출처를 붙여 말해 주세요<br><span style='font-size:24px'>예: 'in our in-house test'</span>", "yellow")),
        divider(),
        t("해제돼야 하는 경우", 28, GRN, 700),
        (says("진행자", "That 45% was from our own test with 30 people.", "(그 45%는 30명 대상 자체 시험 결과예요.)"),
         ai("뜻으로 판단", "같은 결과 + 출처를 밝힘"), result("배너 해제<br><span style='font-size:24px'>지금은 ②와 같은 이유로 실패</span>", "green")),
        gap=16),
    gap=18),
    notes="제안 문구는 예시일 뿐이고, 뜻이 맞으면 해제(사용자 10/8). COMPLIANCE_RESAY=on(D-355)이 이 규칙을 프롬프트에 넣었지만 ID 칸이 비어 해제가 안 됐다.")

slide("switch", "④ 제품 전환", "\"다음\" + 다음 제품 이름이나 종류를 말하면 바로 넘어간다", col(
    flows(
        (says("진행자", "Okay, next up is the ampoule!", "(자, 다음은 앰플이에요!)"),
         ai("맥락 판정 출력", "moving_to_next_named: true · target: 다음 순서 제품"),
         result("프롬프터 전환<br><span style='font-size:24px'>말 끝나고 1.2~1.8초 · 되돌리기 8초</span>", "green")),
        gap=18),
    rowx(fx(code("맥락 판정이 받는 것", "RUN_SHEET: 1. Hydra Barrier Cream (cream) ← 방송 중", "           2. Deep Hydration Ampoule (ampoule) ← 다음", "UTTERANCE + 앞 줄")),
         fx(code("넘어간 뒤 10초", "규정·사실 판정에 두 제품 자료를 같이 줌", "어느 제품 이야기인지는 모델이 고름")), gap=20),
    tags("측정 (정상 흐름 6편)", chip("전환 12/12", "green", "check"), chip("잘못된 전환 0", "green", "check"),
         chip("다다음 제품 이름은 넘어가지 않음", "grey")),
    gap=20),
    notes="D-351. 순서는 방송 전에 고정. 바로 다음 제품만, 이름 또는 종류 단어. 판정 실패 시 한 번 재시도.")

slide("hold", "⑤ 질문 보류", "질문 줄은 답과 묶어서 한 번에 판정한다", flows(
    (says("두 진행자", "B: How much is the 3-pack?<br>A: 138 ringgit.", "(3개 묶음 얼마예요? / 138링깃이요.)"),
     ai("[앞 줄] 질문 + [이번 줄] 답", "한 발화로 판정"), result("3개 묶음 가격과 대조<br><span style='font-size:24px'>두 사람 대화 96.6% (7차)</span>", "green")),
    gap=18),
    notes="D-334/335. 맥락 판정이 답을 기다리는 줄로 보면 다음 줄을 최대 2.5초 기다린다. 기다리는 동안 운영자 화면에만 표시.")

slide("store", "⑥ 저장", "방송 데이터는 Firestore에 세션별로 남는다", col(
    rowx(fx(code("sessions/{세션 ID}", "  transcripts  진행자 문장 (25)", "  alerts       경고, 상태, 정정한 줄 (3)", "  events       화면 이벤트 (133)", "  segments     제품 구간 (3)", "  agent_calls  판정 입력·출력 (77)")),
         fx(col(t("저장 방식", 28, INK, 700), t("화면과 판정은 메모리에서 바로 처리", 26), t("Firestore 쓰기는 뒤에서 순서대로 (경고를 기다리게 하지 않음)", 26),
                t("서버가 새로 떠도 세션을 다시 불러옴", 26), gap=10)), gap=24),
    tags("확인", chip("정상 흐름 3편 모두 저장됨 (10/8)", "green", "check"), chip("배포에는 아직 안 켬", "yellow", "warn")),
    gap=22),
    notes="D-354. 괄호 숫자는 진단 실행 한 편의 실제 문서 수. STORE=firestore는 사용자 결정 후 cloudrun.sh에 넣는다.")

slide("now", "지금 상태", "기본 기능 중 정정과 배너 해제만 남았다", table(
    ["기능", "정상 흐름 결과", "상태"],
    [["제품 전환", "12/12, 잘못된 전환 0, p95 1.5초", "됨"],
     ["위반 경고 표시", "팩 안 규칙 3/3", "됨"],
     ["단서 배너 표시", "6/6", "됨"],
     ["경고 속도", "p95 4.2~5.2초", "기준 근처"],
     ["정정하면 해제", "1/3~2/3", "안 됨 (②)"],
     ["출처 붙여 다시 말하면 해제", "0/3~2/6", "안 됨 (②)"],
     ["Firestore 저장", "3/3 세션", "됨"]],
    ["30%", "44%", "26%"]),
    notes="정상 흐름 6편(F01~F06)과 진단 3편 기준. 예시 문장은 데모 제품으로 바꿔 씀.")

write(str(OUT), "로직 흐름과 예시")
