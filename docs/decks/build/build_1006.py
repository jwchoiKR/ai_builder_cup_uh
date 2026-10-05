"""10/6 team update deck (google-slide-deck design). Run: python docs/decks/build/build_1006.py"""
import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

HERE = Path(__file__).parent
OUT = HERE.parent / "team_update_1006.html"
RES = Path(r"D:\code_test\study\ai_builder_cup_git\sealed_sets\results")  # numbers only; sealed text never shown


def img(path, maxh=560):
    b = base64.b64encode(Path(path).read_bytes()).decode()
    return (f'<img src="data:image/png;base64,{b}" alt="" style="display:block; max-width:100%; max-height:{maxh}px; '
            f'border:2px solid {LINE}; border-radius:16px; margin:0 auto">')


def stat(value, label, base, color, bg):
    return (f'<div style="flex:1; background:{bg}; border-radius:24px; padding:36px 32px; display:flex; '
            f'flex-direction:column; gap:12px">'
            f'<p style="font-size:30px; font-weight:500; color:{INK}">{label}</p>'
            f'<p style="font-size:80px; font-weight:700; color:{color}; line-height:1.05">{value}</p>'
            f'<p style="font-size:24px; color:{SUB}">{base}</p></div>')


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


def warn(x):
    return f"<span style='color:#B06000'>{x}</span>"


def strict(run, name):
    """First result line of a strict-scoring report, or None."""
    p = RES / run / f"{name}.md"
    if not p.exists():
        return None
    m = re.search(r"detection ([\d.]+)%.*?false alerts ([\d.]+)%.*?extra wrong alerts? ([\d.]+)%", p.read_text(encoding="utf-8"), re.S)
    return m.groups() if m else None


# ---- 1 cover
slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 팀 공유 · 10/6", "blue")}
<h1 style="font-size:92px; font-weight:500; line-height:1.15">수동 데모에서<br>자동화 플랫폼으로</h1>
<p style="font-size:40px; color:{SUB}; line-height:1.45">처음 보는 브랜드의 아무 문서를 넣으면<br>몇 분 안에 라이브 준비가 끝나는 서비스</p></div>''',
      notes="10/5 밤 사용자 결정으로 방향을 바꿨다. 이유와 계획, 증명 방법을 공유한다.")

# ---- 2 criteria
slide("criteria", "심사 기준", "점수의 40%는 'AI를 의미 있게, 동작하게, 확장 가능하게'다", col(
    table(["기준", "배점", "심사위원이 보는 것"], [
        ["기술 완성도·생성형 AI 구현", "<b>40%</b>", "AI를 의미 있게 썼나, 실제로 동작하나, 확장 가능한가"],
        ["문제 적합성·임팩트", "25%", "주제(리테일·커머스)에 맞고 이해관계자에게 가치가 분명한가"],
        ["혁신·창의", "25%", "생성형 AI를 독창적으로 썼나"],
        ["UX·설계", "10%", "쉽고, 구성요소가 잘 맞물리나"]], [34, 12, 54], 26),
    tags("제출물", chip("동작하는 배포 링크", "grey"), chip("3분 이내 영상", "grey"), chip("공개 GitHub", "grey"),
         chip("상세 덱", "grey")), gap=28),
    notes="출처: aibuildercup.com/Faqs.html, themes.html. 결선 전에 채점 라운드가 있다.")

# ---- 3 problem
slide("problem", "심사위원 시점", "지금은 새 제품 하나 넣는 데 개발자가 필요하다", col(
    flows(
        t("지금", 28, RED, 700),
        (says("브랜드", "\"우리 제품도 써 볼래요\""), ai("정해진 틀의 문서 +<br>제품 정보 파일 손으로 작성", "", "red"),
         result("개발자 작업<br><span style='font-size:24px'>심사위원: \"준비된 두 제품용 데모\"</span>", "red")),
        divider(),
        t("목표", 28, GRN, 700),
        (says("브랜드", "가진 문서 그대로 올림", "PDF·워드·엑셀·이미지·웹"), ai("Gemini가 읽고 정리", "값마다 원문 위치"),
         result("운영자 승인 한 번<br><span style='font-size:24px'>몇 분 안에 라이브 준비</span>", "green")), gap=16)),
    notes="사용자: '각 회사마다 제품 틀이 다 다를텐데 맞아야 한다고 하는 것 자체가 문제', '수동인 프로세스들은 다 자동화'. 고객에게 틀을 맞추라고 하지 않는다.")

# ---- 4 onboarding flow
slide("flow", "자동 등록", "문서를 올리면 일곱 단계가 자동으로 돈다", col(
    howline(("① 업로드", "아무 형식, 여러 파일"), ("② 읽기", "Gemini 멀티모달 · 원문 위치"),
            ("③ 정리", "코드 · 통화·단위·할인가 계산"), ("④ 만들기", "별칭·용어집·표현·규정"), label="준비"),
    howline(("⑤ 자기 검사", "우리 판정 AI로 시험"), ("⑥ 승인", "근거 보고 한 번에"),
            ("⑦ 반영", "버전 저장 · 재시작 없이"), label="출시"),
    tags("지키는 것", chip("값을 지어내지 않음, 없으면 '없음'", "grey"), chip("문서끼리 다르면 충돌로 표시", "grey"),
         chip("문서 속 지시문은 무시", "grey"), chip("공개 게시 직전 코드 확인은 유지", "grey")), gap=28),
    notes="docs/research/onboarding-spec.md. 브랜드 규정 업로드도 같은 경로. 오늘 밤은 ①~③과 시험 진입점부터.")

# ---- 5 probe
slide("probe", "방법 탐색", "처음 보는 문서 6개에서 가격을 하나도 틀리지 않았다", col(
    rowx(stat("10/10", "가격 추출", "틀린 가격 0 · 새 브랜드 6곳, 파일 10개", GRN, GRNBG),
         stat("6/6", "카테고리", "화장품·식품·헤어", GRN, GRNBG),
         stat("1/1", "문서 충돌 발견", "구버전·신버전 용량 차이", GRN, GRNBG), gap=24),
    t("방법 탐색: 스크립트가 gemini-3.8-flash를 직접 불렀다. 우리 앱 결과가 아니며, 앱의 자동 등록 경로로 다시 잰다. 형식: 표 PDF, 브로슈어, 한국어 워드, 웹페이지, 엑셀, 글자가 그림 안에 있는 PNG.", 24, SUB),
    gap=24), notes="정답은 GPT 작성 + Sonnet 블라인드 추출로 확인(숫자 전부 일치). 봉인 세트라 개발 쪽에 공개하지 않는다.")

# ---- 6 arms
slide("arms", "설계 비교", "AI에게 다 맡기자 틀린 답이 공개 채팅에 올라갔다", col(
    table(["후보", "새 봉인 세트 탐지", "말로 한 답 잘못 게시", "판단"], [
        ["A · 지금 구조 (AI 판정 + 코드 확인)", ok("99.3%"), ok("0"), "기본 구조"],
        ["D · 규정·문서 전부 프롬프트, 코드 확인 제거", bad("90.4%"), bad("6"), "탈락"],
        ["E · D + 규정을 Vertex AI Search로", bad("86.7%"), bad("4"), "탈락"],
        ["F2 · 방송 중 제품 파일만 미리 넣기", ok("99.3%"), ok("0"), "오경고 절반, 새 제품에서 재측정"]], [42, 18, 18, 22], 25),
    t("10/5 로컬 실측(예전 채점). 교훈: 공개 게시 직전에 코드로 숫자를 확인하는 장치는 어떤 구조에서도 남긴다.", 24, SUB),
    gap=22), notes="docs/eval/design-arms.md. A는 두 제품에 맞춰진 비교라 새 제품에서 다시 잰다. F2는 D 계열이라 확인 장치도 빠져 있었다.")

# ---- 7 strict
s4, s3 = strict("tune_e8e86eb", "sealed4"), strict("tune_e8e86eb", "sealed3")
s4o, s3o = strict("p1_56272d3", "sealed4"), strict("p1_56272d3", "sealed3")
def cell(x):
    return f"{x[0]}% · 오경고 {x[1]}%" if x else "측정 중"
slide("strict", "정직한 숫자", "채점을 엄격하게 바꾸자 100%가 93~98%가 됐다 (두 제품 기준)", col(
    table(["시험", "예전 채점", "엄격 채점 (56272d3)", "엄격 채점 (로직 수정 D-207~215 + 예시 제거, e8e86eb)"], [
        ["새 봉인 세트 90줄 × 3: 탐지", "99.3%", cell(s4o), cell(s4)],
        ["이전 봉인 세트 80줄 × 3: 탐지", "100%", cell(s3o), cell(s3)]], [34, 16, 25, 25], 26),
    tags("엄격 채점", chip("맞는 규칙·항목·정정 값이어야 '잡음'", "grey"), chip("엉뚱한 경고 5% 넘으면 불합격", "grey"),
         chip("말로 한 답: 잘못·놓침·중복 모두 0", "grey")),
    t("두 열 차이는 탐지 2줄, 오경고 1문장(3회)으로 반복 시험의 흔들림 안이다. 커밋 13개가 함께 들어가 예시 제거만의 효과는 따로 재지 않았다.", 24, SUB), gap=26),
    notes="예전 채점은 경고가 뜨기만 하면 잡은 걸로 셌다. 심사위원이 믿을 숫자는 오른쪽이다. 합격선은 탐지 95% 이상. 오른쪽을 쓰는 이유는 숫자가 아니라 제품 정보 없는 로직이라서다.")

# ---- 7b unseen products
slide("unseen", "핵심 시험", "처음 보는 제품에서는 61~89%: 사실 확인이 무너졌다", col(
    table(["제품 (가상 브랜드, 자동 등록 그대로)", "위험 문장 탐지", "오경고"], [
        ["나이트 크림", "88.9%", "5.6%"], ["선크림 (용량 2개)", bad("61.1%"), "7.4%"],
        ["한국어 클렌징 폼", "75.9%", "1.9%"], ["콜라겐 음료 (식품)", bad("61.1%"), "1.9%"],
        ["헤어 세럼 (용량 2개, 할인)", "75.9%", "3.7%"], ["배리어 크림 (구·신버전)", "77.8%", "11.1%"]], [52, 24, 24], 24),
    tags("유형별", chip("규정 판정은 일반화: 부정 92% · 인용 92% · STT 오류 97%", "green", "check"),
         chip("사실 확인 붕괴: 끊긴 문장 28% · 비슷한 숫자 50%", "red", "x")), gap=20),
    notes="216줄 × 3회, 봉인(GPT 작성, Sonnet 블라인드 216/216 일치), 코드 e8e86eb. 원인: 용량별 가격이 라이브 데이터에서 사라짐, 할인 조건·구버전 값·다른 시장 가격·외부 시험 문구를 사실 확인이 모름. 사실 확인을 등록 기록 기반으로 새로 짠 FR(D-242)과 A를 같은 세트로 재측정 중.")

# ---- 7c all tests today (1/2)
_H = ["시험", "결과", "의미"]
slide("alltests1", "오늘 한 시험 (1/2)", "현재 구조와 채점 방식을 다시 쟀다", table(_H, [
    ["클라우드 00008 합성 방송 3개 + 지연 100줄", ok("심은 실수 18/18") + " · 운영자 -76% · p95 2.50초", "시간 초과 2건 → 재요청(D-184)"],
    ["설계 후보 7개 비교 (A~F)", "A 최고 · D·E 잘못 게시 4~6건", "게시 직전 코드 확인 유지"],
    ["엄격 채점 도입 (두 제품)", "100% → 93~98%", "예전 채점이 너그러웠음"],
    ["동시 실행 vs 단독 실행", "91.1% vs 95.6%", "시험은 하나씩만"],
    ["주입 공격 200회", ok("공격 성공 0") + " · 링크 오차단 1", "링크 처리 수정(D-234)"]], [32, 36, 32], 24),
    notes="모든 숫자는 우리 앱 결과. 상세: docs/eval/proof-plan.md, design-arms.md")

# ---- 7d all tests today (2/2)
slide("alltests2", "오늘 한 시험 (2/2)", "새 제품과 실제 사용 흐름으로 쟀다", table(_H, [
    ["말로 한 답 게시 (실제 세션 재생)", ok("잘못 게시 0") + " · 놓침 1~3", "대부분 시간 초과 → 재확인(D-203)"],
    ["자동 등록 · 새 브랜드 6개", "상품·규정·할인 6/6 · " + bad("안전 2/6"), "주의사항 재확인(D-226)"],
    ["처음 보는 제품 라이브 216줄", bad("61~89%"), "사실 확인 재설계(FR) 비교 중"],
    ["사용자 흐름 직접 실행", "방송 시작 버그 → 수정", "D-230, 재확인 완료"],
    ["Vertex AI Search 옵션", "관련도 최저 · 결과 5~10개 → 9/9", "후보 E는 그래도 탈락"]], [32, 36, 32], 24),
    notes="research/full-review-1005.md, research/onboarding-gaps.md")

# ---- 8 principles
slide("principles", "원칙", "앞으로 모든 일은 이 다섯 가지로 판단한다", f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px 40px">'
      + listing([("뜻은 AI, 실행은 코드", "판단은 Gemini, 시간·상태·게시 허가는 코드"),
                 ("수동은 설계 결함", "고객에게 틀을 요구하지 않음, 사람은 승인만"),
                 ("우리 로직만 시험", "실행 중 다른 LLM·사람 개입 없음")], "check", BLUE)
      + listing([("측정으로 고른다", "방향이 여럿이면 전부 만들어 비교"),
                 ("안 되면 버린다", "두 번 고쳐도 안 되면 다시 설계"),
                 ("심사위원 시점", "계획·결과마다 약점과 바꿀 것을 적음")], "check", BLUE) + "</div>",
      notes="사용자 10/5 결정들. CLAUDE.md, docs/HANDOFF.md에 기록.")

# ---- 9 scope
slide("scope", "기능 범위", "기능은 충분하다, 빠진 것은 자동화와 증거다", col(
    table(["더할 것", "이유"], [
        ["<b>자동 제품 등록</b> (브랜드 규정 업로드 포함)", "기술 40%의 핵심, 멀티모달 활용"],
        ["심사위원 체험 버튼", "배포 링크를 열면 바로 장면이 재생됨"],
        ["화면의 성과 숫자", "실제 로그, 분모, AI 끔 기준선, 시간당 비용"],
        ["사람 진행자 방송 1회 (AI 끔/켬)", "합성 음성만으로는 '동작'을 증명 못 함"],
        ["업로드 문서 공격 시험과 상한", "공개 업로드에 심사위원이 먼저 물을 질문"]], [48, 52], 25),
    tags("뺄 것", chip("새 라이브 기능", "grey"), chip("카메라·영상 분석", "grey"), chip("언어 추가", "grey"),
         chip("영상 속 화면 순회", "grey")), gap=24),
    notes="codex·agy·Sonnet 토론 결과(PLANNING 10/5 밤). '언어 추가'는 세 모델 모두 반대.")

# ---- 10 cloud
slide("cloud", "클라우드 결과", "지금 구조로 심은 실수는 모두 잡았다", col(
    rowx(stat("18/18", "심은 실수 3초 안 경고", "봉인 방송 3개 · 00008 (실측)", GRN, GRNBG),
         stat("-76%", "운영자가 할 일", "22건 / AI 끔 93건 (실측)", GRN, GRNBG),
         stat("2.50초", "사실 경고 p95", "100줄 · 00007은 3.29초", BLUE, BLUEBG), gap=24),
    t("합성 방송 기준이다. 판정 AI 시간 초과로 놓친 2줄은 고쳤다(재요청, 확인 전 게시 금지).", 24, SUB),
    gap=24), notes="docs/eval/proof-plan.md")

# ---- 11 roles
slide("roles", "역할 분담", "셋이 겹치지 않게 나눈다", col(
    grid3(
        tile("person", BLUE, BLUEBG, "개발 리드", "설계 결정, 개발 AI 지휘, 병합, 배포 승인",
             "예: 비교 결과로 기본 구조 확정"),
        tile("mic", SUB, "#F1F3F4", "진행자 테스트", "직접 방송하며 실수를 섞어 말하고, 경고·시간·사용성 기록",
             "예: 억양·속도·잡음을 바꿔 녹음"),
        tile("check", SUB, "#F1F3F4", "워크플로·성능 검증", "봉인 세트 작성, 비교·클라우드 시험, 결과 기록",
             "예: 녹음을 재생 시험으로 다시 잼"), h=None),
    tags("규칙", chip("봉인 세트는 검증 담당만 본다", "grey"), chip("개발 AI 지시는 한 창구로", "grey"),
         chip("숫자는 우리 앱 결과만 보고", "grey")), gap=30),
    notes="진행자 테스트에서 이상한 일 → 녹음·메모 → 검증 담당이 재생 사례로 확인 → 개발 리드 → 개발 세션.")

# ---- 12 next
slide("next", "다음", "남은 일", table(["할 일", "상태"], [
    ["자동 등록 ①~③ + 시험 진입점", warn("개발 중 (10/5 밤 시작)")],
    ["처음 보는 제품으로 A·F2 비교 (코드 동결)", warn("자동 등록 뒤")],
    ["엄격 채점에서 틀린 유형 정리 → 고치거나 다시 설계", warn("진행 중")],
    ["심사위원 체험 버튼 · 성과 숫자 · 근거 표시", "자동 등록 뒤"],
    ["사람 진행자 방송 1회", "팀원 1"],
    ["배포 (로그인 제거, 비용 상한)", "사용자 승인"]], [58, 42], 26),
    notes="docs/HANDOFF.md 7장")

write(OUT, "라이브 진행자 어시스턴트 10/6")
print("wrote", OUT)
