"""Detailed workflow deck: before, during and after the show, one flow per slide (google-slide-deck design).
Run: python docs/decks/build/build_workflow.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "workflow_detail.html"
GREYBG = "#F1F3F4"

# kind -> (label, label colour, background, border)
KIND = {
    "person": ("사람", SUB, GREYBG, LINE),
    "ai": ("AI", BLUE, BLUEBG, "#A8C7FA"),
    "code": ("코드", INK, "#FFFFFF", LINE),
    "store": ("저장", SUB, "#FFFFFF", LINE),
    "screen": ("화면·게시", GRN, GRNBG, "#A8DAB5"),
    "wait": ("운영자", "#B06000", YELBG, "#FDD663"),
    "stop": ("차단", RED, REDBG, "#F6AEA9"),
}


def node(kind, title, *lines, use=""):
    """Small step box: role label, step name, what it does (short lines), and what it uses (API, file, model)."""
    lab, fg, bg, bd = KIND[kind]
    dash = "dashed" if kind == "store" else "solid"
    body = "".join(f'<p style="font-size:22px; line-height:1.35; color:{INK}">{x}</p>' for x in lines)
    u = f'<p style="font-size:21px; line-height:1.3; color:{BLUE if kind == "ai" else SUB}; font-weight:500">{use}</p>' if use else ""
    return (f'<div style="background:{bg}; border:2px {dash} {bd}; border-radius:16px; padding:10px 14px; '
            f'display:flex; flex-direction:column; gap:4px; min-width:0">'
            f'<p style="font-size:22px; font-weight:700; color:{fg}">{lab}</p>'
            f'<p style="font-size:26px; font-weight:700; line-height:1.25; color:{INK}">{title}</p>{body}{u}</div>')


def stack(*nodes):
    """Several outcomes of one step, stacked in one cell."""
    return f'<div style="display:flex; flex-direction:column; gap:10px">{"".join(nodes)}</div>'


def lanes(*rows, n=5):
    """Rows of nodes joined by arrows, in one grid so columns line up. A str row is a full-width stage label."""
    cols = " 44px ".join(["minmax(0,1fr)"] * n)
    cells = []
    for r in rows:
        if isinstance(r, str):
            cells.append(f'<div style="grid-column:1/-1">{r}</div>')
            continue
        r = list(r) + [None] * (n - len(r))
        for k, x in enumerate(r):
            if k:
                cells.append(f'<div>{right(44) if x is not None else ""}</div>')
            cells.append(f'<div style="min-width:0">{x or ""}</div>')
    return (f'<div style="display:grid; grid-template-columns:{cols}; column-gap:8px; row-gap:10px; '
            f'align-items:start">{"".join(cells)}</div>')


def stage(text, color=SUB):
    return f'<p style="font-size:24px; font-weight:700; color:{color}">{text}</p>'


def legend():
    return tags("박스 색", chip("사람", "grey"), chip("AI (Gemini)", "blue"), chip("코드", "grey"),
                chip("화면·게시", "green", "check"), chip("운영자에게", "yellow", "warn"), chip("차단", "red", "x"))


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


def warn(x):
    return f"<span style='color:#B06000'>{x}</span>"


# ---- 1 cover
slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 상세 워크플로 · 10/6", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">방송 전, 방송 중, 방송 후<br>시스템이 하는 일 전부</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">단계마다 누가 하는지, 어떤 API·코드·모델을 쓰는지,<br>결과가 어느 화면에 나오는지</p></div>''',
      notes="코드 기준 421ca0f(multi_agent_test). 클라우드는 00008(코드 0d5565a)이라 온보딩은 아직 배포 전이다.")

# ---- 2 overview
slide("overview", "전체 지도", "제품 문서가 들어와서 방송이 끝날 때까지 세 구간이다", col(
    lanes(stage("방송 전 · 제품 등록과 준비", SUB),
          (node("person", "문서 올리기", "형식 상관없음"), node("ai", "읽고 정리", "원문 위치와 함께"),
           node("person", "확인·승인", "노란 항목만"), node("code", "릴리스", "버전 고정"),
           node("screen", "방송 준비 끝", "진행자 화면")),
          stage("방송 중 · 말과 댓글을 동시에", SUB),
          (node("person", "진행자 말", "마이크"), node("ai", "판정 셋", "규정·맥락·사실"),
           node("screen", "경고·정정", "진행자 화면"), node("ai", "댓글 답변", "근거 인용"),
           node("screen", "채팅 게시", "확인 뒤에만")),
          stage("방송 후 · 정리", SUB),
          (node("code", "통계 계산", "숫자는 코드"), node("ai", "요약 작성", "숫자 밖 문장 삭제"),
           node("screen", "요약 화면", "다음 방송 할 일"))),
    legend(), gap=16),
    notes="이 문서의 나머지 장은 이 지도의 박스 하나하나를 펼친 것이다.")

# ================= 방송 전
slide("pre-1", "방송 전 ① 제품 등록", "문서를 올리면 AI가 통째로 읽고, 코드가 근거 없는 값을 버린다", col(
    lanes(stage("올리기와 저장"),
          (node("person", "파일 올리기", "PDF·워드·엑셀·사진·HTML", use="POST /api/onboarding/jobs"),
           node("code", "상한 확인", "파일 20개·20MB·동시 2건", use="api/onboarding.py"),
           node("store", "원본 보관", "바꿀 수 없게 저장", "sha256 이름", use="onboarding/files.py"),
           node("code", "읽을 형태로", "워드·엑셀은 글자로, 위치 유지", use="files.py")),
          stage("읽기 (두 AI가 동시에)"),
          (stack(node("ai", "전체 읽기", "값마다 파일·위치·원문", use="3.8 Flash · HIGH · read.py"),
                 node("ai", "주의사항만 따로", "작은 글씨·각주·라벨", use="3.8 Flash · MEDIUM · D-226")),
           node("code", "정리", "통화·단위·천 단위 쉼표", "숫자가 원문에 없으면 버림", use="read.py · D-225"),
           node("code", "확인할 것 고르기", "가격·용량·규정·주의·혜택", use="checks.py · VERIFY_MODE"),
           node("wait", "확인 화면", "노란 항목만 사람이 봄"))),
    tags("지키는 것", chip("값을 지어내지 않음, 없으면 '없음'", "grey"), chip("문서끼리 다르면 충돌로 표시", "grey"),
         chip("문서 속 지시문은 따르지 않음", "grey"), chip("링크는 지우고 읽음", "grey")), gap=22),
    notes="읽기 1~5분(봉인 9개 제품 59~312초). 템플릿을 요구하지 않는다: 같은 경로가 브로슈어·표·라벨 사진을 모두 읽는다. VERIFY_MODE=risk는 4개 그룹만 보여 준다(D-236).")

slide("pre-2", "방송 전 ② 승인과 릴리스", "승인하면 바꿀 수 없는 릴리스가 되고, 방송은 그 릴리스로 시작한다", col(
    lanes(stage("승인"),
          (node("wait", "충돌 고르기", "쉬운 말로 두 값 비교", "칸별로 바로 수정", use="D-231"),
           node("person", "승인", "한 번 누름", use="POST /jobs/{id}/approve"),
           node("ai", "언어별 번역", "주장·주의·피할 말", "검토 전이면 자동 게시 안 함", use="3.8 Flash · LOW · translate.py"),
           node("store", "릴리스", "버전 고정, 제품 키는 해시", use="release.py · D-218, D-227")),
          stage("방송 데이터 만들기"),
          (node("code", "방송용 팩", "가격·용량·주장·주의", "판정 AI가 읽는 형태", use="release.py to_pack"),
           node("code", "할인가 계산", "AI가 아닌 코드가 계산", use="D-223"),
           node("code", "규정 팩 고르기", "카테고리를 덮는 팩", "없으면 '규정 확인 없음' 표시", use="covers · D-227"),
           node("screen", "방송 시작", "release_id로 세션 생성", use="POST /api/sessions"))),
    tags("릴리스 규칙", chip("승인된 릴리스는 수정하지 않고 새 버전을 만듦", "grey"),
         chip("기존 제품 방송은 그대로 동작", "grey"), chip("번역 검토 표시는 승인 화면에서 켬", "grey")), gap=22),
    notes="FACT_MODE=record(D-242, FR)는 사실 확인이 방송용 팩 대신 릴리스 기록을 직접 읽는다. 용량별 가격, 구버전 값, 혜택 조건, 시험 단서까지. A와 비교 중.")

slide("pre-3", "방송 전 ③ 규정과 브랜드 규칙", "규정도 제품처럼 문서로 올리고, 사람이 승인한다", col(
    lanes(stage("국가 규정 팩 (D-229)"),
          (node("person", "규제 문서 올리기", "예: 보건 당국 지침", use="POST /lawpacks/jobs"),
           node("ai", "규칙으로 읽기", "규칙마다 원문 근거", use="3.8 Flash · HIGH · lawpack.py"),
           node("person", "승인", use="approve-lawpack"),
           node("store", "버전 저장", "덮는 카테고리 기록"),
           node("screen", "자동 선택", "제품 카테고리에 맞게")),
          stage("브랜드 규칙 팩 (D-241)"),
          (node("person", "브랜드 지침 올리기", "피할 표현·필수 문구", use="POST /brandpacks/jobs"),
           node("ai", "규칙으로 읽기", "같은 읽기 경로"),
           node("person", "승인", use="approve-brandpack"),
           node("screen", "방송에 적용", "규정 팩과 함께 판정"))),
    tags("현재 상태", chip("싱가포르·말레이시아 기본 팩 38개 규칙", "grey"), chip("규제 원문으로 만든 팩 평가는 남음", "yellow", "warn"),
         chip("우리는 법 준수를 보장하지 않음, 확인 도구다", "grey")), gap=22),
    notes="출처 후보: HSA, MOH, ASAS, CCS (docs/research/law-sources-categories.md). 규정 검색은 Vertex AI Search 후보(E)가 탈락해 프롬프트 + 코드 확인 구조를 유지한다.")

slide("pre-4", "방송 전 ④ 방송 준비", "STT 용어집과 프롬프터 포인트를 AI가 만들고 운영자가 확정한다", col(
    lanes(stage("준비 화면 (/setup)"),
          (node("code", "제품 시트", "릴리스 또는 기존 제품"),
           node("ai", "브리프 작성", "STT 용어집 후보", "프롬프터 포인트 초안", use="3.8 Flash · MEDIUM · brief.py"),
           node("person", "확정", "빼고 고치고 확정", use="POST /brief/{id}/confirm"),
           node("store", "용어집 버전", "다음 세션부터 적용", use="pipelines/setup.py"),
           node("screen", "프롬프터", "꼭 말할 포인트")),
          stage("심사위원 체험 (D-238)"),
          (node("person", "체험 버튼", "배포 링크에서 한 번"),
           node("ai", "가상 제품 등록", "번들 문서를 실제로 읽음", use="testdrive.py"),
           node("person", "승인 한 번"),
           node("screen", "장면 재생", "위험 발언·정정·댓글 답변", "AI PD 카드"))),
    tags("왜 필요한가", chip("STT가 브랜드·성분 이름을 틀리게 듣는 문제", "grey"), chip("진행자가 빠뜨린 포인트를 화면이 챙김", "grey")), gap=22),
    notes="용어집은 chirp_3 phrase hints로 들어간다. 체험은 요청 상한이 있다.")

# ================= 방송 중
slide("live-1", "방송 중 ① 진행자 말", "진행자가 말하면 판정 AI 셋이 동시에 읽고, 3초 안에 화면에 뜬다", col(
    lanes(stage("듣기 → 판정 AI 셋이 동시에 (2.5초 제한, 1.5초에 재요청) → 확인 → 화면"),
          (node("person", "진행자 말", "마이크 16kHz", use="WS /sessions/{id}/audio"),
           node("ai", "글자로 바꾸기", "용어집 힌트", use="STT chirp_3 · us"),
           node("code", "문장 잇기", "3.5초 안 끊긴 문장 합침", use="D-088"),
           stack(node("ai", "규정 판정", use="3.5 Flash-Lite · LOW"),
                 node("ai", "맥락 판정", "답 연결·포인트·전환", use="3.5 Flash-Lite · MINIMAL"),
                 node("ai", "사실 확인", "가격·용량·성분", use="3.5 Flash-Lite · MINIMAL"),
                 node("code", "빠른 단어 검사", "혼자 경고 안 띄움", use="reflex.py")),
           node("code", "판정 확인", "규칙 ID·원문 근거", "대체 문구는 승인 문구만", use="alerts.py · qualifier.py"),
           stack(node("stop", "빨간 경고", "정정할 때까지 유지"), node("screen", "사실 정정", "맞는 값과 근거"),
                 node("screen", "프롬프터", "말한 포인트 체크"))), n=6),
    tags("시간 장치", chip("늦은 사실 판정도 6초까지 받음", "grey"), chip("정정은 실제로 고쳐 말해야 인정 (사과만은 안 됨)", "grey"),
         chip("진행자 화면은 SSE로 갱신", "grey")), gap=22),
    notes="JUDGE_MODE=split3. 클라우드 00008: 심은 실수 18/18, 사실 경고 p95 2.50초. 정정 판단 D-089.")

slide("live-2", "방송 중 ② 진행자가 말로 답할 때", "진행자가 말로 답하면 사실 확인을 마친 답만 채팅에 올린다", col(
    lanes(stage("말로 한 답"),
          (node("person", "진행자 답변", "'용량은 50mL예요'"),
           node("ai", "질문과 연결", "어느 질문 묶음의 답인지", use="맥락 판정"),
           node("ai", "사실 확인 완료 대기", "끝나기 전엔 게시 안 함", "실패하면 한 번 더", use="D-195 · D-203"),
           node("code", "숫자 대조", "연결된 초안의 숫자와", "한 문장에 답 여럿도 처리", use="publish.py · D-196"),
           stack(node("screen", "채팅 게시", "2초 안 취소 가능"), node("stop", "게시 안 함", "높은 경고가 있으면")))),
    tags("게시 직전 규칙", chip("사실 확인이 안 끝났으면 게시하지 않음", "grey"), chip("게시 순간 높은 경고를 다시 확인 (D-204)", "grey"),
         chip("운영자가 쓴 답도 같은 확인 (D-205)", "grey")), gap=22),
    notes="말로 한 답 실측(실제 세션 재생): 잘못 게시 0, 놓침 1~3(대부분 시간 초과). 밤 재측정 런타임 모드: 놓침 6(모두 시간 초과).")

slide("live-3", "방송 중 ③ 댓글 거르기와 분류", "댓글은 코드와 Model Armor가 먼저 거르고, AI가 뜻으로 나눈다", col(
    lanes(stage("거르기"),
          (node("person", "시청자 댓글", "채팅"),
           node("code", "1차 거르기", "이메일·전화번호·욕설", "이모지만 있는 반응", use="prefilter.py"),
           node("ai", "공격 검사", "프롬프트 주입·유해 내용", "실패하면 운영자로", use="Model Armor · 0.5초 · D-206"),
           stack(node("stop", "숨김", "개인정보·욕설·공격"), node("code", "링크", "지우고 분류로 보냄", use="D-234")))),
    lanes(stage("분류와 묶기"),
          (node("ai", "댓글 분류", "질문·반응·구매 의사", "어느 제품 이야기인지", use="3.5 Flash-Lite · LOW · 최대 10개 묶음"),
           node("code", "같은 뜻 묶기", "조건이 다르면 따로", use="grouping.py · D-214"),
           node("code", "보낼 곳 정하기", "자동 답·진행자·운영자", use="routing.py · intents.json"),
           node("screen", "다음 장으로", "답 만들기"))),
    gap=22),
    notes="'크림 얼마에요'처럼 물음표가 없어도 분류 AI가 질문으로 본다. 주입 공격 200회: 성공 0.")

slide("live-4", "방송 중 ④ 댓글 답 만들기와 게시", "자료에 있는 답만 자동으로 올리고, 없으면 운영자에게 보낸다", col(
    lanes(stage("답 만들기와 확인"),
          (node("ai", "답 쓰기", "제품 자료를 인용해서", use="3.8 Flash · LOW · 12초"),
           node("code", "코드 확인", "숫자가 인용 원문에 있는지", "금지 표현·대체 문구", use="verify.py"),
           node("ai", "초안 검사", "뜻 뒤집기·지어내기", "주의 약화", use="3.5 Flash-Lite · 2.5초 · D-126"),
           stack(node("screen", "자동 게시", "근거 표시 · 2초 취소"),
                 node("screen", "진행자 카드", "민감 질문은 말로"),
                 node("wait", "운영자", "자료에 없음·확인 실패")))),
    tags("보내는 기준", chip("자료에 있으면 바로 게시, 없으면 운영자", "grey"), chip("번역 검토 전 문장은 자동 게시 안 함", "grey"),
         chip("제품이 바뀌면 이전 제품 질문은 운영자로", "grey"), chip("같은 답은 캐시로 즉시", "grey")), gap=22),
    notes="사용자 원칙: '제품 정보에 없는 질문은 그냥 운영자 화면으로 보낸다.' 답변 검사 봉인 세트: 잘못 게시 0, 좋은 답 차단 0/90.")

slide("live-5", "방송 중 ⑤ AI PD와 운영자", "AI PD는 확인된 카드 중 하나만 고르고, 문장은 쓰지 않는다", col(
    lanes(stage("AI PD"),
          (node("code", "방송 이벤트", "구매·질문 급증·시간"),
           node("code", "후보 카드", "확인된 문장만", "답·혜택·전환 멘트", use="logic/pd.py"),
           node("ai", "하나 고르기", "카드 ID만 고름", use="ADK · 3.8 Flash · LOW"),
           node("code", "실패하면 규칙", "같은 후보에서 선택", use="rule_pick"),
           node("screen", "진행자 카드", "최소 20초 유지")),
          stage("운영자 화면"),
          (node("wait", "질문 처리", "승인·직접 답·거절"),
           node("wait", "경고 처리", "닫기·다시 보내기·공지"),
           node("screen", "성과 숫자", "자동 처리·시간·분모", use="D-240"),
           node("screen", "근거 보기", "답마다 인용 원문", use="D-239"))),
    gap=22),
    notes="빨간 규정 경고와 사실 정정은 AI PD를 거치지 않는다(바로 진행자 화면).")

# ================= 방송 후
slide("post-1", "방송 후 · 요약 에이전트", "숫자는 코드가 세고, AI는 그 숫자로만 요약을 쓴다", col(
    lanes(stage("방송 종료 뒤 자동으로"),
          (node("person", "방송 종료", use="POST /sessions/{id}/end"),
           node("code", "통계 계산", "경고·정정·답변·시간", "운영자 처리 수", use="summary_stats.py"),
           node("store", "먼저 저장", "상태 '계산 중'", use="pipelines/summary.py"),
           node("ai", "요약 쓰기", "한 줄 요약·잘한 점", "주의할 점·다음 할 일", use="3.8 Flash · MEDIUM · 30초"),
           node("code", "숫자 검사", "통계에 없는 숫자 문장 삭제", use="post_validate")),
          stage("결과"),
          (node("screen", "요약 화면", use="GET /sessions/{id}/summary"),
           node("code", "AI 실패 시", "통계만 보여 줌", use="rule_based_summary"))),
    tags("요약에 들어가는 것", chip("headline", "blue"), chip("highlights", "blue"), chip("watch_outs", "blue"),
         chip("follow_ups", "blue")), gap=22),
    notes="BroadcastSummary(agents/broadcast_summary.py, prompts/broadcast_summary.md). 요약 품질은 아직 따로 평가하지 않았다.")

# ================= 모델 표
slide("models", "한눈에", "어느 단계에 어떤 모델과 생각 수준을 쓰는가", table(
    ["단계", "모델", "생각 수준", "시간 제한"], [
        ["문서 읽기 · 규정 문서 읽기", "gemini-3.8-flash", "HIGH", "10분"],
        ["주의사항 다시 읽기", "gemini-3.8-flash", "MEDIUM", "10분"],
        ["번역", "gemini-3.8-flash", "LOW", "10분"],
        ["브리프 · 방송 후 요약", "gemini-3.8-flash", "MEDIUM", "60초 · 30초"],
        ["댓글 답 쓰기 · AI PD", "gemini-3.8-flash", "LOW", "12초 · 이벤트 때"],
        ["규정 판정 · 댓글 분류", "gemini-3.5-flash-lite", "LOW", "2.5초"],
        ["맥락 판정 · 사실 확인 · 초안 검사", "gemini-3.5-flash-lite", "MINIMAL", "2.5~3초"],
        ["음성 인식", "chirp_3 (us)", "", "실시간"]], [40, 26, 16, 18], 25),
    notes="backend/app/config.py, onboarding/read.py. 방송 중에는 빠른 모델, 방송 밖에서는 더 생각하는 모델.")

# ================= 시험
slide("tests-1", "오늘 한 시험 (1/3)", "구조와 채점 방식", table(["시험", "결과", "그래서"], [
    ["클라우드 00008 합성 방송 3개 + 지연 100줄", ok("심은 실수 18/18") + " · 운영자 일 -76% · p95 2.50초", "시간 초과 2건 → 재요청(D-184)"],
    ["설계 후보 7개 (A~F)", "A 최고 · D·E 잘못 게시 4~6건", "게시 직전 코드 확인 유지"],
    ["엄격 채점 도입 (두 제품)", "100% → 93~98%", "예전 채점이 너그러웠음"],
    ["동시 실행 vs 단독 실행", "91.1% vs 95.6%", "시험은 하나씩만"],
    ["Vertex AI Search 옵션 조정", "관련도 최저·결과 5~10개 → 9/9", "후보 E는 그래도 탈락"]], [32, 38, 30], 24),
    notes="모든 숫자는 우리 앱 결과다. 상세: docs/eval/proof-plan.md, docs/eval/design-arms.md")

slide("tests-2", "오늘 한 시험 (2/3)", "두 제품 봉인 세트, 최신 코드 (21:09~21:50)", table(["시험 (3회 반복)", "결과", "판정"], [
    ["봉인4 90줄 위험 문장", "탐지 94.8% · 오경고 3.0% · 잘못된 높은 경고 3", bad("불합격")],
    ["봉인3 80줄 위험 문장", "탐지 95.0% · 오경고 0.8%", ok("합격")],
    ["튜닝 세트", "탐지 96.8% · 오경고 0.0%", ok("합격")],
    ["말로 한 답 (에이전트 단위)", "잘못 게시 0 · 놓침 0~4", warn("1/3 합격")],
    ["말로 한 답 (실제 런타임)", "잘못 게시 0 · 놓침 6 (모두 시간 초과)", bad("불합격")],
    ["답변 초안 검사", "잘못 게시 0 · 좋은 답 차단 0/90 · 오류 1", warn("오류 1로 불합격")],
    ["댓글 흐름", "분류 100% · 보낼 곳 100% · 캐시 98.1%", warn("캐시만 미달")],
    ["주입 공격 200회", ok("성공 0") + " · 링크 오차단 1", "D-234로 수정"]], [30, 50, 20], 23),
    notes="sealed_sets/results. 봉인 세트 문장은 개발 쪽에 보이지 않는다.")

slide("tests-3", "오늘 한 시험 (3/3)", "처음 보는 제품: 여기가 진짜 시험이다", table(["시험", "결과", "그래서"], [
    ["새 브랜드 6개 라이브 216줄 (e8e86eb)", bad("탐지 61~89%"), "사실 확인 재설계 FR(D-242)"],
    ["  유형별", "규정 판정 92~97% · " + bad("끊긴 문장 28% · 비슷한 숫자 50%"), "가격·혜택 조건이 팩에서 빠짐"],
    ["자동 등록 9개 (화장품·식품·헤어·의류)", "상품 7/8 · 거버넌스 6/8 · 안전 6/8 · 혜택 8/8", "로직 수정 3건 dev 전달"],
    ["  놓친 원인", "글자로 쓴 숫자 · 시험 결과가 다른 칸 · 위생 주의가 사용법 칸", "숫자 파서 · 칸 재분류 · 주의 복사"],
    ["A vs FR (같은 216줄)", warn("측정 중"), "진 쪽은 버림"],
    ["사용자 흐름 직접 실행", "방송 시작 버그 → 수정", "D-230 재확인 완료"]], [32, 42, 26], 23),
    notes="자동 등록 채점은 4개 그룹(score_groups.py). 의류 1건은 말레이어 주의를 영어 정답과 비교해 채점기가 놓친 것이라 수동 확인으로 통과 처리했다. 목표는 처음 보는 제품에서 100%.")

write(OUT, "상세 워크플로")
print("wrote", OUT)
