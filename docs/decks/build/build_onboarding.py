"""Onboarding (product parsing) explainer (google-slide-deck design). Run: python docs/decks/build/build_onboarding.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

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
slide("flowstatus", "사용자 흐름", "실제 화면으로 끝까지 돌렸다: 업로드부터 방송 시작까지 동작", col(
    table(["단계", "결과", "고칠 것"], [
        ["홈 → '새 제품 등록'", "<span style='color:#1E8E3E'>동작</span>", ""],
        ["파일 4개 올리기 (워드·엑셀 2개·라벨 사진)", "<span style='color:#1E8E3E'>동작</span>", ""],
        ["읽기 (122초)", "<span style='color:#1E8E3E'>동작</span>", "진행 상태 표시 있음"],
        ["확인 화면", "<span style='color:#B06000'>동작, 쓰기 어려움</span>", "충돌이 내부 경로 이름(variants[0]…)으로 보임 → 쉬운 말과 선택 버튼, JSON 편집 대신 칸별 수정"],
        ["승인", "<span style='color:#1E8E3E'>동작</span>", "승인 뒤 라이브에서 무엇이 적용되는지 요약"],
        ["'이 제품으로 방송 시작'", "<span style='color:#1E8E3E'>동작 (D-230 수정)</span>", "처음엔 기존 데모 제품이 열렸음 → 세션별 제품 정보로 수정, 재확인 완료"]], [30, 18, 52], 24),
    gap=16), notes="10/5 밤 사용자 흐름 점검. 개발 세션에 넘김. 심사위원 데모의 핵심 장면이라 최우선.")

# ---- 0c2 show screen
slide("show", "사용자 흐름", "방송을 시작하면 진행자·운영자·시청자 화면이 새 제품으로 바뀐다", col(
    img(IMG / "onb-5-show.png", 600),
    t("실제 화면 (17152ba). 새로 등록한 세럼의 이름·가격 S$44·말할 포인트·주의사항이 진행자 프롬프터에, 브랜드가 운영자·시청자 화면에 나온다.", 23, SUB), gap=16),
    notes="개발용 가상 제품. 성분 칸이 비어 있는 점은 개선 대상(D-230 이후).")

# ---- 0d system path 1: upload to record
slide("path1", "시스템 흐름 ①", "파일을 올리면 이렇게 처리된다: 저장 → 변환 → Gemini 2회 → 코드 검사", col(
    table(["순서", "어디서", "무엇을"], [
        ["1. 업로드", "<b>POST /api/onboarding/jobs</b> (화면: /onboarding)", "파일 여러 개 + 힌트. 상한: 20개·20MB·동시 2건"],
        ["2. 저장", "<b>onboarding/files.py</b> → <code>ONBOARDING_DIR/&lt;draft_id&gt;/&lt;sha256&gt;</code>", "내용 해시로 저장, 변경 불가 (배포 땐 GCS)"],
        ["3. 변환 (코드)", "files.py <code>model_part</code>", "PDF·이미지·HTML은 그대로, 워드·엑셀은 글자·표로"],
        ["4a. 읽기 (LLM)", "<b>onboarding/read.py</b> · gemini-3.8-flash · 생각 <b>HIGH</b>", "파일 전부를 한 번에 → 정해진 형식, 값마다 파일·위치·인용"],
        ["4b. 주의사항 (LLM, 동시)", "read.py <code>read_cautions</code> · 같은 모델 · 생각 <b>MEDIUM</b>", "주의사항만 다시 찾아 놓친 것만 합침"],
        ["5. 정리 (코드)", "read.py <code>normalise</code>", "통화·단위·쉼표 정리. <b>숫자가 인용에 없으면 버림</b>"],
        ["6. 결과", "<b>GET /api/onboarding/jobs/{id}</b>", "진행 상태와 결과를 확인 화면에"]], [16, 40, 44], 24),
    gap=12), notes="backend/app/onboarding (D-216, D-217, D-225, D-226). 같은 경로를 scripts/eval_onboarding.py가 시험에서 그대로 부른다.")

# ---- 0e system path 2: approve to live
slide("path2", "시스템 흐름 ②", "승인하면 출시본이 생기고, 라이브가 그 제품으로 돈다", col(
    table(["순서", "어디서", "무엇을"], [
        ["7. 승인", "<b>POST /api/onboarding/jobs/{id}/approve</b>", "다시 검증·정리, 이 시장에서 방송 가능한지 확인"],
        ["8. 승인본 저장 (재배포 없음)", "<b>onboarding/release.py</b> → <code>releases/&lt;release_id&gt;_vN.json</code>", "버전 붙여 저장, 기존 제품은 그대로"],
        ["9. 라이브용 변환 (코드)", "release.py", "제품 정보·검색 문단·1구간 진행표, <b>할인가는 코드가 계산</b>"],
        ["10. 규정 고르기", "카테고리 → 규정 묶음 <code>covers</code>", "기본 규정 → 원문에서 만든 규정(D-229) → 없으면 '법규 검사 없음'"],
        ["11. 방송 시작", "<b>POST /api/sessions</b> {release_id}", "프롬프터·판정·답변이 이 제품으로 동작"]], [16, 40, 44], 24),
    gap=12), notes="D-218, D-223, D-227, D-229. 현재 11단계 화면 연결에 버그(기존 데모 제품이 열림)가 있어 수정 중.")

# ---- 0f where LLM vs code
slide("llmcode", "역할 나눔", "읽고 판단하는 건 Gemini, 계산과 검사는 코드", col(
    table(["단계", "Gemini", "코드"], [
        ["문서 → 제품 정보", "전체 읽기(HIGH), 주의사항 재확인(MEDIUM)", "변환, 저장, 통화·숫자 정리, 인용 대조 검사"],
        ["규정 원문 → 규칙", "규칙 기록 만들기(HIGH, 조항 번호·인용)", "버전 저장, 카테고리 연결"],
        ["승인", "-", "재검증, 사람이 고친 값 정리"],
        ["라이브", "판정 3개·댓글 분류·답변 작성·답변 검증·AI PD", "할인가 계산, 시간 제한, 게시 직전 숫자 확인, 중복 방지"]], [22, 40, 38], 24),
    tags("사람이 하는 일", chip("파일 올리기", "grey"), chip("충돌·빠진 값 확인", "grey"), chip("승인", "grey")), gap=22),
    notes="원칙: 뜻은 AI, 실행은 코드, 사람은 승인만.")

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
