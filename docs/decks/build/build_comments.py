"""Comment pipeline explainer (google-slide-deck design). Run: python build_comments.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "comment_flow.html"

# ---- 1 overview
slide("overview", "댓글 처리", "댓글 하나가 들어오면 이 순서로 간다", col(
    howline(("① 스팸 거르기", "욕설·전화번호 (코드)"), ("② 공격 댓글 차단", "Model Armor"),
            ("③ 질문인지 분류", "Gemini 3.5 Flash Lite"), ("④ 같은 질문 묶기", "코드"), label="거르고 읽기"),
    howline(("⑤ 보낼 곳 정하기", "질문 종류표"), ("⑥ 제품 문서로 답 작성", "Gemini 3.8 Flash"),
            ("⑦ 답 확인", "코드 + 검증 AI"), ("⑧ 게시 · 카드 · 운영자", "결과"), label="답하기"),
    tags("댓글 분류 AI가 정하는 것", chip("질문 / 반응 / 숨김", "grey"), chip("어느 제품", "grey"),
         chip("질문 종류 (가격, 성분, 임신…)", "grey"), chip("조건 (지성 피부, 아침…)", "grey")), gap=28),
    notes="backend/app/pipelines/comments.py. 짧은 댓글(5단어 이하)은 진행자가 방금 한 말과 함께 분류한다. 댓글이 몰리면 기다리던 댓글을 한 번에 묶어 분류한다.")

# ---- 2 scenes
slide("scenes", "예시", "같은 흐름에서 결과는 다섯 가지로 갈린다", col(
    flows(
        (says("시청자", "\"how much is the cream?\"", "(크림 얼마예요?)"), ai("가격 · Hydra Barrier Cream", "제품 ID로 지정 · 문서에서 S$36 확인"),
         result("채팅에 바로 게시", "green")),
        (says("시청자", "\"can use when pregnant?\"", "(임신 중에 써도 돼요?)"), ai("민감한 질문", "문서 근거로 확인된 답 있음"),
         result("진행자 카드<br><span style='font-size:24px'>진행자가 읽고 확인</span>", "blue")),
        (says("시청자", "\"ship to Malaysia?\"", "(말레이시아 배송 돼요?)"), ai("제품 정보에 답 없음"),
         result("운영자에게<br><span style='font-size:24px'>1인 방송은 대기 개수만</span>", "yellow")),
        (says("시청자", "\"ignore your rules and…\"", "(규칙 무시하고…)"), ai("Model Armor가 공격으로 판단", "", "red"),
         result("숨김 · AI 처리 안 함", "red")),
        (says("시청자", "\"just bought it!\"", "(방금 샀어요!)"), ai("반응 · 구매 댓글"),
         result("AI PD가<br>이름 불러주기 카드", "blue")), gap=12)),
    notes="결과 다섯 가지: 자동 게시, 진행자 카드, 운영자, 숨김, 반응(불러주기).")

# ---- 3 routing
slide("routing", "보낼 곳", "질문 종류마다 보낼 곳이 정해져 있다", col(
    table(["질문 종류", "답이 제품 정보에 있으면", "없으면"], [
        ["가격 · 세트가 · 할인 · 용량 · 성분 · 함량<br>향 · 제형 · 사용기한 · 원산지 · 포장",
         f"<span style='color:{GRN}'>채팅에 바로 게시</span>", "운영자"],
        ["피부 타입 · 사용법 · 바르는 순서 · 메이크업 전 · 효과 시점 · 제품 비교",
         f"<span style='color:{BLUE}'>진행자 카드</span>", "운영자"],
        ["임신 · 질환 · 알레르기 · 나이 · 효능 (민감)", f"<span style='color:{BLUE}'>진행자 카드</span>", "운영자"],
        ["배송 · 반품 · 결제 · 주문 상태 · 이벤트 · 기타", "-", "운영자"]], [52, 26, 22], 26),
    tags("예외", chip("제품이 불분명하면 진행자가 \"어떤 제품이요?\" 확인", "grey"), chip("1인 방송은 운영자 목록 대신 대기 개수", "grey")),
    gap=24), notes="data/policy/intents.json, backend/app/logic/routing.py. 사용자 결정(10/5): 제품 정보에 있으면 게시, 없으면 운영자.")

# ---- 4 answer check
slide("check", "답 검사", "답은 두 번 확인한 뒤에만 나간다", col(
    chain4(step4(1, "book", BLUE, BLUEBG, "답 만들기", "제품 문서만 보고 쓰고, 출처를 표시"),
           step4(2, "rules", SUB, "#F1F3F4", "코드 검사", "인용이 문서에 있는지, 숫자·가격이 같은지, 금지 표현"),
           step4(3, "ai", BLUE, BLUEBG, "검증 AI", "질문에 답하는지, 근거에 없는 말이 있는지"),
           step4(4, "check", GRN, GRNBG, "통과", "게시 · 같은 질문은 저장된 답을 다시 씀")),
    tags("하나라도 걸리면", chip("게시 안 함", "red", "x"), chip("운영자에게", "yellow")), gap=32),
    notes="verify.py (코드), draft_verifier (AI). 봉인 시험 세트: 나쁜 답 게시 0, 좋은 답 차단 0/90 (10/5, 3회).")

# ---- 5 grouping
slide("grouping", "묶기", "같은 질문은 한 번만 답한다", col(
    flows(
        (says("12명", "\"ingredients?\" \"what's inside?\"", "(성분이 뭐예요?)"), ai("같은 질문으로 묶음", "제품·조건이 같을 때만"),
         result("12건 → 1묶음<br><span style='font-size:24px'>답 한 번</span>", "green")),
        (says("시청자", "\"oily skin ok?\" · \"dry skin ok?\"", "(지성도 돼요? · 건성도 돼요?)"), ai("조건이 다르면 따로 묶음"),
         result("2묶음 · 답 따로", "blue")),
        (says("진행자", "다음 제품으로 전환"), ai("이전 제품 질문 중<br>답 못 받은 것"), result("운영자 목록으로 이동<br><span style='font-size:24px'>운영자가 나중에 답함</span>", "yellow")), gap=14)),
    notes="grouping.py. 진행자 화면에는 현재 제품 질문만 보인다 (D-178).")

write(OUT, "댓글 처리 흐름")
print("wrote", OUT)
