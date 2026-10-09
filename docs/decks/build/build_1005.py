"""10/5 team update deck (google-slide-deck design). Run: python build_1005.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("SLIDE_DECK_LIB", r"C:\Users\User.DESKTOP-G5S2APU\google-slide-deck"))  # the folder that holds deck.py
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "old" / "team_update_1005.html"


def stat(value, label, base, color, bg):
    return (f'<div style="flex:1; background:{bg}; border-radius:24px; padding:40px 36px; display:flex; '
            f'flex-direction:column; gap:14px">'
            f'<p style="font-size:30px; font-weight:500; color:{INK}">{label}</p>'
            f'<p style="font-size:88px; font-weight:700; color:{color}; line-height:1.05">{value}</p>'
            f'<p style="font-size:24px; color:{SUB}">{base}</p></div>')


# ---- 1 cover
slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 팀 공유 · 10/5", "blue")}
<h1 style="font-size:96px; font-weight:500; line-height:1.15">라이브 진행자 어시스턴트</h1>
<p style="font-size:42px; color:{SUB}; line-height:1.45">진행자가 말하는 동안 AI가 위험한 말을 잡고,<br>다음에 할 일을 하나씩 짚어 준다.</p></div>''')

# ---- 2 what
slide("what", "무엇을 만드나", "진행자가 말하는 동안 AI가 옆에서 돕는다", col(
    grid3(
        tile("shield", RED, REDBG, "위험한 말을 잡는다", "광고 심의에 걸리는 말을 바로 알려 주고 고쳐 말할 문구를 띄운다",
             "예: \"wrinkles disappear overnight\" → 경고"),
        tile("book", BLUE, BLUEBG, "틀린 제품 정보를 잡는다", "제품 문서와 다른 가격·성분·용량을 바로 알려 준다",
             "예: \"ten percent niacinamide\" → 정답 4%"),
        tile("ai", BLUE, BLUEBG, "AI PD가 진행을 짚어 준다", "남은 필수 포인트, 답할 질문, 전환 시점을 카드 하나로 띄운다",
             "예: 시간 60% 지남 → \"Patch tested…\" 카드"), h=None),
    tags("목표", chip("운영자 일을 줄인다", "grey"), chip("초보자도 1인 방송을 중급자처럼", "grey")), gap=40),
    notes="운영자를 없애는 것이 아니라 줄인다. 1인 방송에서도 동작한다.")

# ---- 3 flow animation
FLOW_CSS = f"""
.fa-row{{display:flex; align-items:center; gap:18px; width:100%}}
.fa-box{{border:3px solid {LINE}; border-radius:20px; background:#fff; padding:22px 24px; display:flex; flex-direction:column; gap:8px; min-width:0}}
.fa-box p{{font-size:28px; line-height:1.35}} .fa-box .fa-k{{font-size:24px; color:{SUB}}} .fa-box .fa-t{{font-size:30px; font-weight:700}}
.fa-arrow{{position:relative; flex:0 0 44px; height:4px; background:{LINE}; border-radius:2px}}
.fa-arrow::after{{content:""; position:absolute; right:-2px; top:-8px; border:10px solid transparent; border-left:14px solid {LINE}}}
.fa-dot{{position:absolute; top:-6px; left:0; width:16px; height:16px; border-radius:50%; background:{BLUE}; opacity:0}}
.fa-stack{{display:flex; flex-direction:column; gap:12px; flex:1.1; min-width:0}}
.fa-time{{display:flex; gap:18px; width:100%; margin-top:6px}} .fa-time p{{font-size:24px; color:{SUB}; text-align:center}}
@keyframes fa-s1{{0%,4%{{border-color:{LINE}}}6%,22%{{border-color:{SUB}; box-shadow:0 0 0 6px #F1F3F4}}26%,100%{{border-color:{LINE}; box-shadow:none}}}}
@keyframes fa-s2{{0%,22%{{border-color:{LINE}}}25%,40%{{border-color:{BLUE}; box-shadow:0 0 0 6px {BLUEBG}}}44%,100%{{border-color:{LINE}; box-shadow:none}}}}
@keyframes fa-s3{{0%,40%{{border-color:{LINE}}}43%,62%{{border-color:{BLUE}; box-shadow:0 0 0 6px {BLUEBG}}}66%,100%{{border-color:{LINE}; box-shadow:none}}}}
@keyframes fa-s4{{0%,62%{{border-color:{LINE}}}65%,82%{{border-color:{RED}; box-shadow:0 0 0 6px {REDBG}}}86%,100%{{border-color:{LINE}; box-shadow:none}}}}
@keyframes fa-s5{{0%,80%{{border-color:{LINE}}}83%,98%{{border-color:{BLUE}; box-shadow:0 0 0 6px {BLUEBG}}}100%{{border-color:{LINE}; box-shadow:none}}}}
@keyframes fa-d1{{0%,20%{{left:0; opacity:0}}21%{{opacity:1}}26%{{left:calc(100% - 16px); opacity:1}}27%,100%{{opacity:0}}}}
@keyframes fa-d2{{0%,38%{{left:0; opacity:0}}39%{{opacity:1}}44%{{left:calc(100% - 16px); opacity:1}}45%,100%{{opacity:0}}}}
@keyframes fa-d3{{0%,60%{{left:0; opacity:0}}61%{{opacity:1}}66%{{left:calc(100% - 16px); opacity:1}}67%,100%{{opacity:0}}}}
.fa-a1{{animation:fa-s1 9s infinite}} .fa-a2{{animation:fa-s2 9s infinite}} .fa-a3{{animation:fa-s3 9s infinite}}
.fa-a4{{animation:fa-s4 9s infinite}} .fa-a5{{animation:fa-s5 9s infinite}}
.fa-d1{{animation:fa-d1 9s infinite}} .fa-d2{{animation:fa-d2 9s infinite}} .fa-d3{{animation:fa-d3 9s infinite}}
@media (prefers-reduced-motion: reduce){{.fa-a1,.fa-a2,.fa-a3,.fa-a4,.fa-a5,.fa-d1,.fa-d2,.fa-d3{{animation:none}}}}
"""

import deck as _deck
_deck.CSS += FLOW_CSS
flow_body = f'''<div class="fa-row">
  <div class="fa-box fa-a1" style="flex:1.15">
    <p class="fa-k">진행자 · 말이 끝남</p><p>"Your wrinkles will disappear overnight."</p><p class="fa-k">(주름이 하룻밤에 사라져요.)</p></div>
  <div class="fa-arrow"><span class="fa-dot fa-d1"></span></div>
  <div class="fa-box fa-a2" style="flex:0.75"><p class="fa-t" style="color:{BLUE}">STT</p><p>문장으로 바꿈</p><p class="fa-k">약 0.9초</p></div>
  <div class="fa-arrow"><span class="fa-dot fa-d2"></span></div>
  <div class="fa-stack">
    <div class="fa-box fa-a3" style="padding:14px 20px"><p class="fa-t" style="color:{RED}">법률</p><p class="fa-k">노화 효능 · HIGH</p></div>
    <div class="fa-box fa-a3" style="padding:14px 20px"><p class="fa-t" style="color:{BLUE}">팩트</p><p class="fa-k">틀린 정보 없음</p></div>
    <div class="fa-box fa-a3" style="padding:14px 20px"><p class="fa-t" style="color:{BLUE}">맥락</p><p class="fa-k">동시에 약 1.2초</p></div>
  </div>
  <div class="fa-arrow"><span class="fa-dot fa-d3"></span></div>
  <div style="display:flex; flex-direction:column; gap:12px; flex:1.2; min-width:0">
    <div class="fa-box fa-a4" style="background:{REDBG}"><p class="fa-t" style="color:{RED}">이렇게 말하세요</p>
      <p>"It helps keep skin hydrated."</p></div>
    <div class="fa-box fa-a5"><p class="fa-k">AI PD 카드 · 다음 할 말</p><p>"Patch tested: 0 of 32 reported reactions."</p></div>
  </div>
</div>'''
slide("flow", "흐름", "말이 끝나고 경고가 뜨기까지 약 2초", flow_body,
      notes="STT p50 0.88초 (latency.md), 판정 p50 약 1.0~1.25초 (holdout, 10/5). 빨간 경고와 틀린 정보 메모는 AI PD를 거치지 않는다.")

# ---- 4 decision
slide("decide", "결정 1", "라우터 대신 셋을 항상 동시에 부른다", col(
    table(["방식", "필요한 호출을 놓친 횟수", "더해지는 시간 (p95)", "비고"], [
        ["<b>병렬 (채택)</b>", "0", "0초", "문장마다 3번 호출"],
        ["Jev 라우터", "0 (임계값 0.3)", "+0.28초", "Google 스택 아님"],
        ["Gemini 3.5 Flash Lite 라우터", "23", "+1.2초", "애매하면 \"아니오\""],
        ["LLM 라우터 (10/2)", "0", "+1.2초", "정확도 이득 없음"]], [30, 26, 20, 24], 28),
    t("라우터 비교: 79문장 × 5회 = 395회 (10/4~10/5). LLM 라우터는 39문장 × 20회 (10/2).", 24, SUB), gap=24),
    notes="출처: docs/eval/routing-accuracy.md, agents-compare.md, orchestration-decision.md")

# ---- 5 AI PD
slide("pd", "AI PD", "AI PD는 띄울 카드 하나만 고른다", col(
    flows(
        (says("상황", "크림 시간 60% 지남", "필수 포인트 하나가 남음"), ai("필수 포인트를 고름"),
         result("\"Patch tested: 0 of 32<br>reported reactions.\"", "blue")),
        (says("상황", "\"지성 피부도 돼요?\" 대기", "검증된 답변 있음"), ai("답할 질문을 고름"),
         result("검증된 답변을<br>그대로 띄움", "blue")),
        (says("상황", "빨간 경고가 떠 있음"), ai("새 카드를 만들지 않음", "", "red"), result("경고가 먼저", "red")), gap=16),
    howline(("사건 감지", "문장·질문·타이머·침묵 8초"), ("후보 만들기", "코드"), ("하나 고르기", "Gemini · ADK"),
            ("15초 고정", "N 키로 넘기기"), label="어떻게"), gap=28),
    notes="문장은 검증된 것만 쓴다 (추천 답변, 프롬프터 포인트, 프로모션 문구). Gemini가 실패하면 규칙으로 고른다.")

# ---- 6 holdout numbers
slide("holdout", "결과 1", "처음 보는 문장에서도 위반을 모두 잡았다", col(
    rowx(stat("75/75", "위반 발언 잡기", "100% · 처음 보는 문장 100개 × 3회 (실측)", GRN, GRNBG),
         stat("1.27초", "경고 판정까지 (p95)", "문장 도착부터 · STT 제외 (실측)", BLUE, BLUEBG),
         stat("42/42", "틀린 정보 잡기", "모델 출력 기준 · 검증기 버그 1건 수정 중", GRN, GRNBG), gap=28),
    tags("남은 문제", chip("따끔거림 답변을 빨간 경고로 판단 (3회 중 1회)", "red", "x"),
         chip("세트 타임세일가를 검증기가 지움", "yellow", "warn")), gap=36),
    notes="docs/eval/holdout-split3-relabeled.md. 라벨 2개는 독립 검토자의 판정으로 고쳤다.")

# ---- 7 sequences
slide("seq", "결과 2", "이어지는 대화에서는 정정 인식이 흔들린다", col(
    rowx(stat("277/285", "연속 대화 검사 통과", "97.2% · 12개 시나리오 × 3회 (실측)", GRN, GRNBG),
         stat("1.39초", "경고 표시까지 (p95)", "문장 도착부터 · STT·화면 제외 (실측)", BLUE, BLUEBG), gap=28),
    tags("수정 중", chip("\"Let me correct my earlier statement…\" 정정을 못 알아봄 (3/3)", "red", "x"),
         chip("새 제품 이야기를 전환 신호로 못 셈 (3/3)", "yellow", "warn")), gap=36),
    notes="docs/eval/holdout-sequences.md. 한 문장 평가에서 정정 인식은 18/18이었다.")

# ---- 8 budget
slide("budget", "3초 목표", "말 끝부터 3초 안에 들어온다",
      col(f'<div style="display:flex; gap:24px; height:420px">' +
          seg("STT", 17, BLUE, "mic", "약 1.0~1.7초", "말 끝 → 문장 (p95)") +
          seg("판정", 13, BLUE, "ai", "약 1.3초", "세 에이전트 동시 (p95)") + "</div>",
          t("합계 약 2.3~3.0초. 단계별 p95를 더한 값이라 보수적이다. 라우터를 넣으면 0.3~1.2초가 더해져 넘친다. Cloud Run 배포 후 다시 잰다.", 26, SUB),
          gap=28),
      notes="STT: docs/eval/latency.md. 판정: holdout-split3.md.")

# ---- 9 cache
slide("cache", "비용", "캐싱은 팩트 체커에서만 효과가 있다", col(
    table(["에이전트", "입력 토큰 (평균)", "캐시 비율 · 끔", "캐시 비율 · 켬"], [
        ["법률", "2,517", "0%", "0%"], ["맥락", "2,371", "0%", "0%"],
        ["팩트 (제품 문서 전체)", "4,947", "44.1%", "<b>72.5%</b>"]], [34, 22, 22, 22], 28),
    t("Gemini 3 계열은 4,096토큰 이상만 캐시한다. 정확도와 속도는 그대로 (100문장 × 3회, 10/5 실측).", 26, SUB), gap=24),
    notes="문장 하나당 입력 약 9,800토큰. 5초에 한 문장이면 시간당 약 700만 토큰 (추정).")

# ---- 10 comments
slide("comments", "댓글", "질문을 한 번에 다 쓰지 않고 아껴 쓴다", col(
    flows(
        (says("시청자", "댓글이 한꺼번에 몰림"), ai("모아서 한 번에 분류", "최대 2초 · 10개"), result("완료 (D-102)", "green")),
        (says("시청자", "진행자용 질문", "저장고에 보관"), ai("쉴 때 하나씩 꺼냄"), result("개발 중", "yellow")),
        (says("시청자", "가격 문의 12명", "채팅에 이미 답함"), ai("읽어줄 카드로 줌"), result("\"많은 분들이<br>물어보시는데…\"", "yellow")),
        (says("Mei", "\"just bought it!\"", "(방금 샀어요!)"), ai("구매 댓글 불러주기"), result("\"Mei님 감사해요!\"", "yellow")),
        gap=14)),
    notes="빠르게 다 처리하면 방송 후반에 진행자가 할 말이 없다 (사용자 지적). 질문 카드 최소 간격 45초 (시작값).")

# ---- 11 operator
slide("operator", "역할", "운영자를 없애지 않고 줄인다", f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px 28px">' +
      listing([("채팅 단순 응답", "가격·배송 같은 반복 질문"), ("위반 발언 감시", "말하는 순간 경고"),
               ("진행 디렉션", "포인트·질문·전환 카드")], "ai", BLUE) +
      listing([("민감한 질문 승인", "임신 중 사용 등"), ("애매한 경고 판단", "사람이 최종 확인"),
               ("1인 방송이면", "판단이 필요한 건 \"보류\"")], "person", SUB) + "</div>",
      notes="왼쪽: AI가 맡는 일. 오른쪽: 사람에게 남는 일. 덱·영상 문구는 'AI가 처리한 비율(실측)'로 쓴다.")

# ---- 13 gates
slide("gates", "결선 관문", "남은 관문은 배포·업무량·영상이다", table(["관문", "상태"], [
    ["처음 보는 문장 평가", f"<span style='color:{GRN}'>완료</span> · 위반 잡기 100%"],
    ["말 끝 → 화면 3초 이내", f"<span style='color:#B06000'>부분</span> · 판정 p95 1.3초, STT 포함 실측 남음"],
    ["ADK AI PD", f"<span style='color:#B06000'>부분</span> · 구현 완료, ADK 구조로 감싸기 남음"],
    ["인터뷰 13개 항목 연결", f"<span style='color:{GRN}'>완료</span>"],
    ["운영자 일을 줄이는 1인 방송", f"<span style='color:#B06000'>진행 중</span> · 페이싱·읽어주기 카드"],
    ["AI가 처리한 업무량 실측", f"<span style='color:{RED}'>남음</span>"],
    ["3분 영상의 AI PD 장면", f"<span style='color:{RED}'>남음</span>"],
    ["배포 링크에서 실제 마이크 동작", f"<span style='color:{RED}'>남음</span>"]], [44, 56], 26),
    notes="docs/PLANNING.md 5.4")

write(OUT, "라이브 진행자 어시스턴트 10/5")
