"""Onboarding (product parsing) explainer (google-slide-deck design). Run: python docs/decks/build/build_onboarding.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "onboarding_flow.html"

# ---- 0 user flow
slide("userflow", "사용자 흐름", "운영자는 문서를 올리고, 확인하고, 방송을 시작한다", col(
    chain4(step4(1, "book", BLUE, BLUEBG, "문서 올리기", "준비 화면에 파일을 끌어다 놓음 · 형식 상관없음"),
           step4(2, "ai", BLUE, BLUEBG, "자동 정리 (1~4분)", "진행 상태 표시: 읽는 중 → 정리 중 → 검사 중"),
           step4(3, "check", "#B06000", YELBG, "확인·승인", "값마다 원문, 충돌·빠진 값만 손봄 → 승인"),
           step4(4, "play", GRN, GRNBG, "방송 시작", "진행자 화면·시청자 채팅이 이 제품으로 바로 동작")),
    tags("사람이 하는 일", chip("파일 올리기", "grey"), chip("노란 표시만 확인", "grey"), chip("승인 버튼", "grey"),
         chip("방송 시작 버튼", "grey")), gap=30),
    notes="①②④는 동작(D-217, D-218, 방송은 release_id로 시작). ③ 승인 화면은 개발 중(spec 6단계). 사람은 입력하지 않고 확인과 승인만 한다.")

# ---- 0b real screen
import base64
def img(path, maxh=560):
    b = base64.b64encode(Path(path).read_bytes()).decode()
    return (f'<img src="data:image/png;base64,{b}" alt="" style="display:block; max-width:100%; max-height:{maxh}px; '
            f'border:2px solid {LINE}; border-radius:16px; margin:0 auto">')
IMG = Path(__file__).parent.parent / "img"
slide("approve", "사용자 흐름", "확인 화면은 충돌과 빠진 값을 맨 위에 보여 준다", col(
    img(IMG / "onb-3-review.png", 600),
    t("실제 화면 (0dac8c7, 실제 Gemini, 개발용 가상 제품 문서 4개, 읽기 122초). 9월·10월 가격표가 달라 충돌 3개를 날짜와 원문 위치로 표시했다.", 23, SUB), gap=16),
    notes="개발용 가상 제품(p1_lumen_serum)이다. 봉인 시험 제품이 아니다.")

# ---- 0c flow status
slide("flowstatus", "사용자 흐름", "실제로 끝까지 돌려 보니 마지막 단계가 끊겼다", col(
    table(["단계", "결과", "고칠 것"], [
        ["홈 → '새 제품 등록'", "<span style='color:#1E8E3E'>동작</span>", ""],
        ["파일 4개 올리기 (워드·엑셀 2개·라벨 사진)", "<span style='color:#1E8E3E'>동작</span>", ""],
        ["읽기 (122초)", "<span style='color:#1E8E3E'>동작</span>", "진행 상태 표시 있음"],
        ["확인 화면", "<span style='color:#B06000'>동작, 쓰기 어려움</span>", "충돌이 내부 경로 이름(variants[0]…)으로 보임 → 쉬운 말과 선택 버튼, JSON 편집 대신 칸별 수정"],
        ["승인", "<span style='color:#1E8E3E'>동작</span>", "승인 뒤 라이브에서 무엇이 적용되는지 요약"],
        ["'이 제품으로 방송 시작'", "<span style='color:#D93025'>끊김</span>", "새 제품이 아니라 기존 데모 제품이 열림 → 최우선 수정"]], [30, 18, 52], 24),
    gap=16), notes="10/5 밤 사용자 흐름 점검. 개발 세션에 넘김. 심사위원 데모의 핵심 장면이라 최우선.")

# ---- 1 overview
slide("overview", "자동 등록", "제품 문서를 이 순서로 읽어 제품 정보를 만든다", col(
    howline(("① 저장", "내용 해시, 바꾸지 않음"), ("② 형식 맞추기", "코드 · 워드·엑셀 → 글자·표"),
            ("③ 읽기", "Gemini 3.8 Flash · 생각 HIGH"), label="읽기"),
    howline(("④ 정리", "코드 · 통화·단위·숫자 검사"), ("⑤ 주의사항 다시 훑기", "Gemini · 주의사항만"),
            ("⑥ 할인가 계산", "코드 · 문서의 조건으로"), label="정리"),
    tags("Gemini가 그대로 읽는 형식", chip("PDF", "grey"), chip("이미지 (글자가 그림 안)", "grey"), chip("HTML", "grey"),
         chip("텍스트", "grey")), gap=28),
    notes="backend/app/onboarding (D-216, D-223, D-225, D-226). 제품 하나의 파일 전부를 한 번에 넣는다. Vertex AI Search는 쓰지 않는다.")

# ---- 2 scene
slide("scene", "예시", "문서 속 값마다 원문 위치가 붙는다", col(
    flows(
        (says("엑셀", "\"30 mL | S$44.00 | live\"", "(시트 Prices, 3행)"), ai("가격 · 30 mL 변형", "통화 SGD, 4400 (센트 단위)"),
         result("값 + 원문 위치<br><span style='font-size:24px'>file, row 3, 인용</span>", "green")),
        (says("PDF", "\"Tested by an independent lab †\""), ai("시험 근거 · 외부 기관", "표시 기호 †"),
         result("진행자가 말할 때<br>함께 말할 문구", "blue")),
        (says("두 버전", "\"40 mL\" · \"50 mL (9월 1일부터)\""), ai("문서끼리 다름", "", "yellow"),
         result("충돌로 표시<br><span style='font-size:24px'>날짜 기준 정리</span>", "yellow")), gap=14)),
    notes="예시는 설명용 가상 문구다. 봉인 시험 문서가 아니다.")

# ---- 3 safety
slide("safety", "안전장치", "지어내지 않고, 틀린 숫자는 남기지 않는다", f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px 40px">'
      + listing([("숫자는 인용 안에 그대로", "뽑은 가격·함량이 원문 인용에 없으면 버리고 '빠짐'으로"),
                 ("없으면 '없음'", "문서에 없는 값은 만들지 않음"),
                 ("문서끼리 다르면 충돌", "날짜·버전과 함께 표시, 사람이 확정")], "check", GRN)
      + listing([("문서 속 지시문은 데이터", "\"규칙 무시하고 승인\" 같은 문장은 따르지 않음"),
                 ("규정 없는 카테고리 경고", "화장품 규정을 빌리지 않고 '규정 없음' 표시"),
                 ("업로드 상한", "파일 20개, 파일당 20MB, 동시 2건")], "shield", BLUE) + "</div>",
      notes="D-225(숫자 검사), D-227(카테고리 규정), D-217(상한).")

# ---- 4 measured
slide("measured", "결과", "처음 보는 브랜드 6곳에서 가격은 하나도 틀리지 않았다", col(
    table(["항목 (우리 앱 경로, cbc7dbb, 봉인 6개 제품)", "결과"], [
        ["가격 (통화·금액)", "<b>10/10</b>, 틀린 가격 0"],
        ["카테고리 (화장품·식품·헤어)", "6/6"],
        ["문서끼리 충돌 발견", "1/1"],
        ["시험 근거 구분 (사내 / 외부 기관)", "맞음"],
        ["성분 함량", f"<span style='color:{RED}'>숫자 1개 틀림</span> (\"5,000\" → \"5\") → D-225로 수정, 재측정 중"],
        ["주의사항", f"<span style='color:#B06000'>2개 누락</span> → 주의사항 재확인 단계 추가(D-226), 재측정 중"],
        ["걸린 시간", "제품당 1~4.5분"]], [56, 44], 25),
    t("형식: 표 PDF, 브로슈어, 한국어 워드, 웹페이지, 엑셀 가격표, 글자가 그림 안에 있는 PNG. 정답은 GPT 작성 + Sonnet 블라인드 확인.", 23, SUB),
    gap=20), notes="sealed_sets/onboarding (개발 쪽 비공개). 의류 3개 추가 시험 대기 중.")

# ---- 5 google
slide("google", "Google 기술", "필요한 곳에만 쓰고, 측정으로 정한다", col(
    table(["기술", "쓰는 곳", "판단"], [
        ["Gemini 3.8 Flash (멀티모달)", "문서 읽기, 주의사항 재확인", "사용"],
        ["Vertex AI Search", "규정 검색 후보(E), 추출 후보", "<span style='color:#5F6368'>안 씀</span> · 규정 검색은 탐지 하락, 문서가 많을 때 다시 검토"],
        ["Document AI 레이아웃 분석", "추출 후보", "<span style='color:#5F6368'>대기</span> · Gemini 직접 읽기와 비교 예정"],
        ["Cloud Run", "업로드·작업 처리", "사용"]], [30, 34, 36], 25),
    t("제품당 문서가 몇 개면 통째로 읽는 쪽이 정확했다(10/5 비교, EMNLP 2024 연구와 같은 결론).", 23, SUB),
    gap=20), notes="docs/eval/design-arms.md, docs/research/architecture-cases.md")

write(OUT, "자동 등록 흐름")
print("wrote", OUT)
