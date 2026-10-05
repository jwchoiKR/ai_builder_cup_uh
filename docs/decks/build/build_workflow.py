"""Detailed workflow deck: before, during and after the show, one flow per slide (google-slide-deck design).
Run: python docs/decks/build/build_workflow.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "workflow_detail.html"
# node(), stack(), lanes(), stage(), legend() come from the skill (deck.py)


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
           node("person", "확인·승인", "노란 항목만"), node("store", "승인본 저장", "재배포 없음"),
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
slide("pre-1", "방송 전 ① 제품 등록", "문서를 올리면 AI가 통째로 읽고, 코드와 두 번째 AI가 빠진 것을 찾는다", col(
    lanes(stage("올리기와 읽기 (두 AI가 동시에)"),
          (node("person", "파일 올리기", "PDF·워드·엑셀·사진·HTML", use="POST /api/onboarding/jobs"),
           node("store", "원본 보관", "바꿀 수 없게 저장", use="files.py"),
           stack(node("ai", "전체 읽기", "값마다 파일·위치·원문", use="3.8 Flash · HIGH"),
                 node("ai", "주의·한계만 따로", "작은 글씨·판매처 제한", use="3.8 Flash · MEDIUM")),
           node("code", "숫자 정리", "'이만 구천 원'도 숫자로", "근거 없는 값은 표시", use="D-243·245"),
           node("ai", "칸 다시 나누기", "각주 붙은 주장 → 시험 결과", use="3.8 Flash")),
          stage("빠진 것 찾기와 확인 목록"),
          (node("ai", "카테고리", "제품 종류는 목록에서", "대상 연령은 따로", use="D-256"),
           node("code", "묶음 계산", "병당 × 병 수, 묶음 최저가", use="D-255·259"),
           node("ai", "누락 점검", "문서엔 있고 기록엔 없는 것", use="3.8 Flash · D-249"),
           node("code", "확인 목록 줄이기", "확인된 주의는 자동 인정", "최대 10개", use="lean · D-254"),
           node("wait", "확인 화면", "사람은 노란 항목만 봄"))),
    gap=18),
    notes="봉인 9개 제품 기준 2~6분. 확인 항목: 예전 방식 7~41개 → lean 3~10개. 1차 봉인 세트에서 상품·거버넌스·안전·혜택 9/9(e41fcf4).")

slide("pre-2", "방송 전 ② 승인과 저장", "승인하면 제품 기록이 승인본 파일로 저장되고, 방송은 재배포 없이 그 파일로 시작한다", col(
    lanes(stage("승인"),
          (node("wait", "충돌 고르기", "쉬운 말로 두 값 비교", "칸별로 바로 수정", use="D-231"),
           node("person", "승인", "한 번 누름", use="POST /jobs/{id}/approve"),
           node("ai", "언어별 번역", "주장·주의·피할 말", "검토 전이면 자동 게시 안 함", use="3.8 Flash · LOW · translate.py"),
           node("store", "승인본 저장", "파일 1개, 고치면 v2", use="releases/&lt;id&gt;.json · D-218")),
          stage("방송 데이터 만들기"),
          (node("code", "방송용 팩", "가격·용량·주장·주의", "판정 AI가 읽는 형태", use="release.py to_pack"),
           node("code", "할인가 계산", "AI가 아닌 코드가 계산", use="D-223"),
           node("code", "규정 팩 고르기", "카테고리를 덮는 팩", "없으면 '규정 확인 없음' 표시", use="covers · D-227"),
           node("screen", "방송 시작", "release_id로 세션 생성", use="POST /api/sessions"))),
    tags("승인본 규칙", chip("코드 배포·서버 재시작 없음", "grey"), chip("승인본은 고치지 않고 새 버전을 만듦", "grey"),
         chip("기존 제품 방송은 그대로 동작", "grey")), gap=22),
    notes="코드에서는 승인본을 release라고 부른다(release.py, release_id). 코드 배포가 아니라 데이터 파일 저장이다. 저장 위치는 서버 폴더이고, 다음 배포부터 Cloud Storage 버킷(서버가 꺼져도 남음). FACT_MODE=record(D-242, FR)는 사실 확인이 방송용 팩 대신 승인본 기록을 직접 읽는다. 용량별 가격, 구버전 값, 혜택 조건, 시험 단서까지. 기본값은 FD(D-255).")

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
          (node("code", "제품 시트", "승인본 또는 기존 제품"),
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
slide("live-1", "방송 중 ① 진행자 말", "진행자가 말하면 판정 AI 셋이 동시에 읽고, 사실 확인은 원본 문서까지 본다", col(
    lanes(stage("듣기 → 판정 AI 셋이 동시에 → 코드 확인 → 화면 (규정 3초, 사실 5초)"),
          (node("person", "진행자 말", "마이크", use="WebSocket"),
           node("ai", "글자로 바꾸기", "용어집 힌트", use="STT chirp_3"),
           node("code", "문장 잇기", "끊긴 문장 합침", use="D-088"),
           stack(node("ai", "규정 판정", use="3.5 Flash-Lite · LOW"),
                 node("ai", "맥락 판정", use="3.5 Flash-Lite · MINIMAL"),
                 node("ai", "사실 확인 (FD)", "원본 파일까지", use="3.5 Flash-Lite · LOW")),
           node("code", "판정 확인", "정정엔 원문 인용 필수", use="D-244~261"),
           stack(node("stop", "빨간 경고", "정정할 때까지 유지"), node("screen", "사실 정정", "방송 언어로"),
                 node("screen", "프롬프터", "말한 포인트 체크")))),
    gap=18),
    notes="FACT_MODE=docs(D-247, 기본값 D-255). 원본 파일은 방송 시작 때 Gemini 컨텍스트 캐시에 올린다. 사실 확인 p95 2.3~3.3초(봉인 세트). 코드가 판정을 지우면 이유를 남긴다(D-250).")

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
        ["주의·한계 다시 읽기 · 누락 점검", "gemini-3.8-flash", "MEDIUM", "10분"],
        ["칸 다시 나누기 · 카테고리 · 번역", "gemini-3.8-flash", "기본 · LOW", "10분"],
        ["브리프 · 방송 후 요약", "gemini-3.8-flash", "MEDIUM", "60초 · 30초"],
        ["댓글 답 쓰기 · AI PD", "gemini-3.8-flash", "LOW", "12초 · 이벤트 때"],
        ["규정 판정 · 댓글 분류", "gemini-3.5-flash-lite", "LOW", "2.5초 (경고 3초)"],
        ["사실 확인 (원본 파일 포함)", "gemini-3.5-flash-lite", "LOW", "5초"],
        ["맥락 판정 · 초안 검사", "gemini-3.5-flash-lite", "MINIMAL", "2.5초"],
        ["음성 인식", "chirp_3 (us)", "", "실시간"]], [40, 26, 16, 18], 25),
    notes="backend/app/config.py, onboarding/read.py. 사실 확인 모델은 10/6 밤 3초·5초 × 3종 비교로 골랐다: 3.8 Flash는 판정 한 번에 3초 넘게 걸려 탈락, Flash-Lite는 MINIMAL·LOW 차이가 흔들림 안.")

# ================= 시험
slide("tests-1", "10/5 저녁 시험 (1/2)", "구조와 채점 방식을 다시 쟀다", table(["시험", "결과", "그래서"], [
    ["클라우드 00008 합성 방송 3개 + 지연 100줄", ok("심은 실수 18/18") + " · 운영자 일 -76% · p95 2.50초", "시간 초과 2건 → 재요청(D-184)"],
    ["설계 후보 7개 (A~F)", "A 최고 · D·E 잘못 게시 4~6건", "게시 직전 코드 확인 유지"],
    ["엄격 채점 도입 (두 제품)", "100% → 93~98%", "예전 채점이 너그러웠음"],
    ["동시 실행 vs 단독 실행", "91.1% vs 95.6%", "시험은 하나씩만"],
    ["Vertex AI Search 옵션 조정", "관련도 최저·결과 5~10개 → 9/9", "후보 E는 그래도 탈락"]], [32, 38, 30], 24),
    notes="모든 숫자는 우리 앱 결과다. 상세: docs/eval/proof-plan.md, docs/eval/design-arms.md")

slide("tests-2", "10/5 저녁 시험 (2/2)", "두 제품 봉인 세트, 그때 최신 코드 (21:09~21:50)", table(["시험 (3회 반복)", "결과", "판정"], [
    ["봉인4 90줄 위험 문장", "탐지 94.8% · 오경고 3.0% · 잘못된 높은 경고 3", bad("불합격")],
    ["봉인3 80줄 위험 문장", "탐지 95.0% · 오경고 0.8%", ok("합격")],
    ["튜닝 세트", "탐지 96.8% · 오경고 0.0%", ok("합격")],
    ["말로 한 답 (에이전트 단위)", "잘못 게시 0 · 놓침 0~4", warn("1/3 합격")],
    ["말로 한 답 (실제 런타임)", "잘못 게시 0 · 놓침 6 (모두 시간 초과)", bad("불합격")],
    ["답변 초안 검사", "잘못 게시 0 · 좋은 답 차단 0/90 · 오류 1", warn("오류 1로 불합격")],
    ["댓글 흐름", "분류 100% · 보낼 곳 100% · 캐시 98.1%", warn("캐시만 미달")],
    ["주입 공격 200회", ok("성공 0") + " · 링크 오차단 1", "D-234로 수정"]], [30, 50, 20], 23),
    notes="sealed_sets/results. 봉인 세트 문장은 개발 쪽에 보이지 않는다.")

slide("tests-3", "처음 보는 제품 (1/4)", "밤사이 로직만 고쳐서 85.8%를 97.2%까지 올렸다 (1차 봉인 세트)", table(
    ["코드", "무엇을 바꿨나", "평균 탐지", "오경고"], [
        ["e8e86eb (출발)", "두 제품용 양식으로 옮긴 요약본을 봄", bad("61~89%"), "1.9~11.1%"],
        ["421ca0f", "등록 기록 전체를 보는 사실 확인 FR (식품 제외)", "84.0% → 90.7%", "5.6~7.4%"],
        ["e713447", "글자로 쓴 숫자, KRW 버그, 식품 규정 팩(HSA 원문)", "85.8%", "1.9~13%"],
        ["1d88a00", "코드가 맞는 판정을 지우던 규칙 수정", "85.8%", "평균 1.9%"],
        ["93064de", "영어 숫자 단어, 출처 이름 오인 수정", "88.9%", "평균 2.8%"],
        ["fcfc870 FR", "한국어 숫자 인용, 가격 조건, 중복 사용 칸", "94.7%", "평균 1.6%"],
        ["fcfc870 FD", "사실 확인이 원본 파일까지 봄", ok("97.2%"), "평균 1.6%"]], [18, 50, 16, 16], 23),
    notes="6개 제품 × 36줄 × 3회, Flash-Lite. 탐지율은 결과를 보지 않은 codex가 정한 '말했어야 할 값'으로 채점했다(Sonnet 독립 검토). 제품 정보는 하나도 넣지 않았다.")

slide("tests-4", "처음 보는 제품 (2/4)", "사실 확인은 5초 마감, Flash-Lite로 정했다", table(
    ["마감", "사실 확인 모델", "평균 탐지", "p50 / p95", "판정 못 끝낸 줄 (720줄)"], [
        ["3초", "Flash-Lite MINIMAL", "85.8%", "1.5 / 2.2초", "5"],
        ["3초", "Flash-Lite LOW", "86.7%", "1.5 / 2.2초", "0"],
        ["3초", "3.8 Flash LOW", bad("77.8%"), "2.9 / 6.0초", bad("258")],
        ["5초", "Flash-Lite MINIMAL", "87.0%", "1.5 / 2.4초", "0"],
        ["5초", "Flash-Lite LOW", "86.7%", "1.4 / 2.3초", "0"],
        ["5초", "3.8 Flash LOW", "84.0%", "3.0~3.7 / 8~10초", bad("88")]], [10, 26, 18, 24, 22], 23),
    notes="1d88a00, 같은 승인본. 큰 모델은 느려서 마감 안에 못 끝낸 줄이 놓침이 됐다. 규정 위반 빨간 경고는 3초를 유지한다(사용자 결정 10/6 0시 40분).")

slide("tests-5", "처음 보는 제품 (3/4)", "자동 등록은 9개 제품 모두 통과, 사람이 볼 항목은 10개 이하로 줄였다", table(
    ["코드", "상품", "거버넌스", "안전", "혜택", "사람이 볼 항목"], [
        ["939d043", "7/8", "6/8", "3/9", "8/8", "7~19개"],
        ["e713447", "9/9", "6/9", "9/9 (직접 확인)", "9/9", "8~19개"],
        ["fcfc870", "9/9", "9/9", "9/9 (직접 확인)", "9/9", warn("7~41개")],
        ["e41fcf4 (lean)", ok("9/9"), ok("9/9"), ok("9/9 (직접 확인)"), ok("9/9"), ok("3~10개")]], [22, 13, 15, 20, 12, 18], 24),
    notes="봉인 9개(화장품 3, 식품 1, 헤어 1, 의류 3, 한국어 문서 1). 안전 '직접 확인'은 말레이어·다른 표현을 단어 채점기가 놓친 것을 사람이 확인했다는 뜻. 원문으로 확인된 주의는 자동 인정(제품당 0~12개).")

slide("tests-6", "처음 보는 제품 (4/4)", "처음 보는 제품: 72.5% → 약 84% (2차·3차 세트), 아직 합격선 아래", col(table(
    ["후보", "1차 봉인 (밤새 보며 고친 6개)", "2차 봉인 (처음 보는 6개)", "무엇을 고쳤나"], [
        ["후보 1 e41fcf4", "93.8%", bad("72.5%"), "FD · lean · 묶음 계산"],
        ["후보 3 aa995d1", "93.2%", warn("78.1%"), "카테고리는 제품 종류로, 판매처·시험 조건·구버전 처리"],
        ["후보 4 947084e", ok("94.7%"), warn("84.3%"), "숫자 단어 단서, 부정 구분, 판매처 확인"],
        ["후보 5 fbb8aa7", "재지 않음", warn("83.0%"), "같은 말 정정 버림, 기준 금액 부정"],
        ["3차 봉인 (처음 보는 6개, 한 번만)", "", warn("84.6%"), "후보 5 그대로: 처음 보는 제품 실력은 약 84%"]], [16, 24, 22, 38], 23),
    tags("정직하게", chip("2차 세트도 이제 본 세트: 다음은 3차 세트로", "yellow", "warn"),
         chip("같은 제품이 실행마다 67~78% 흔들림", "grey"), chip("2차 세트 실패는 유형만 개발에 전달", "grey")), gap=20),
    notes="2차 세트: 말레이어 아기 바디워시, 비타민 젤리(식품), HTML 립틴트, 중국어 선스틱, 엑셀 향수, 구·신버전 풋크림. 문서는 codex, 정답은 codex와 Sonnet이 따로 붙여 212/216 일치. 후보 5 제품별 87.0 / 85.2 / 79.6 / 68.5 / 88.9 / 88.9, 오경고 2.5%, 사실 확인 p95 2.5~2.9초.")

slide("tests-7", "채점 정직성", "채점을 고친 것은 모두 따로 기록했다", col(
    listing([("정정 값 채점", "라벨의 맥락 숫자 때문에 맞는 정정을 틀렸다고 셈 → 결과를 안 본 codex가 '말했어야 할 값'을 따로 씀"),
             ("규칙 이름 매핑", "식품 규정 팩(HSA 원문)의 규칙 이름을 시험 전에 미리 대응시킴, Sonnet이 두 개를 빼라고 해서 뺌"),
             ("항목 이름 차이", "복용량 ↔ 사용법, 성분 ↔ 향료처럼 앱의 칸 이름이 다른 경우만 인정")], "check", BLUE),
    t("모든 변경: sealed_sets/LABEL_CHANGES.md. 로직 개선과 섞지 않고 따로 보고한다. 봉인 세트는 개발 쪽에 보이지 않는다.", 24, SUB), gap=20),
    notes="Sonnet이 '첫 숫자' 규칙을 반례 2개로 거부해서 쓰지 않았다. 주의사항을 뒤집은 말은 사실 정정이 떠야 잡은 것으로 센다(규정 경고는 감점 없음).")

write(OUT, "상세 워크플로")
print("wrote", OUT)
