"""Public AI Builder Cup repos vs our current code, 10/6 (google-slide-deck design).
Source: docs/research/repo-rescore-1006.md. Run: python docs/decks/build/build_repo_1006.py"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "old" / "repo_compare_1006.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


def warn(x):
    return f"<span style='color:#B06000'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 공개 레포 재비교 · 10/6", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">서비스 내용만 보면<br>우리는 상위권, 3위는 아직 증명 전</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">레포 146개 요약 + 커밋 기록, 배포 링크·영상·소개 글 꾸밈은 점수에서 뺌</p></div>''',
      notes="에이전트 1차 채점 후 codex(gpt-6-astra high) 교차 검토. 다른 팀은 요약과 커밋만 봤고 코드를 돌리지 않았다.")

slide("method", "어떻게 매겼나", "공식 배점 그대로, 서비스 자체만 본다", col(
    table(["항목", "배점", "본 것"], [
        ["기술", "40", "AI가 실제로 판단하는 것, 코드가 막는 것, 시험 규모, 처음 보는 데이터, 저장·확장"],
        ["문제", "25", "실제 고객이 겪는 문제인지, 범위가 분명한지"],
        ["혁신", "25", "같은 문제를 푸는 다른 방법과 무엇이 다른지"],
        ["UX", "10", "화면에서 사람이 할 일이 줄었는지"]], [14, 10, 76], 25),
    tags("뺀 것", chip("배포 링크", "grey"), chip("영상", "grey"), chip("발표 자료", "grey"), chip("소개 글 배지·꾸밈", "grey")), gap=22),
    notes="사용자 규칙: 경쟁 비교는 서비스 내용만(10/5).")

slide("top", "전체 순위", "상위 팀은 근소한 차이다: 0.5점으로 순위를 가르기는 어렵다", table(
    ["등수", "팀", "분야", "1차 점수", "codex 검토", "한 줄"], [
        ["1", "Gapline", "미디어", "8.70", "8.2~8.5", "음성·영상 이해·음성 합성 검토 반복, 호출마다 비용 기록"],
        ["2", "Taal", "리테일", "8.45", warn("7.8~8.2"), "예측 → ADK 계획 → 사람 승인 → 대조군 측정, 실제 실행 근거는 적음"],
        ["3", "<b>Live Studio (우리)</b>", "리테일", "8.40", warn("7.9"), "규정 경고 3초·사실 정정 5초, 아무 문서 자동 등록, 봉인 시험"],
        ["4", "SentinelGraph", "금융", "8.15", ok("더 높게"), "ADK 조사 도구 선택, 시간 분할 AUC 0.914"],
        ["5", "ARTHA", "금융", "8.03", "약 8.0", "레드팀 에이전트, 작업 대기열"],
        ["6", "ReadiCheck", "금융", "7.93", "약 7.9", "Gemini Live 사기범 역할 통화, 시험 작음"],
        ["7", "Groundtruth", "사회", "7.83", ok("ReadiCheck 위"), "'Gemini만 / 에이전트 / 전체' 비교 0/18 → 16/18"],
        ["7", "Provenance", "금융", "7.83", warn("후함"), "인용 없이는 경보를 못 닫게 함"]], [7, 18, 9, 10, 12, 44], 22),
    notes="docs/research/repo-rescore-1006.md 1-1. 대회 마감 10/18이라 다른 팀도 계속 만든다. 10/6 기준 사진이다.")

slide("retail", "리테일·커머스", "같은 분야에서 실제로 맞붙는 팀은 Taal 하나다", table(
    ["팀", "점수", "상태"], [
        ["Taal", "8.45 (codex 7.8~8.2)", "닫힌 고리 설계는 탄탄, 실제 Gemini 실행은 한 시나리오 5회"],
        ["<b>Live Studio (우리)</b>", "8.40 (codex 7.9)", "라이브 진행자 보조, 처음 보는 제품 83~84%"],
        ["OmniLocate", "7.18", "상품 영상을 나라별 광고로, 1단계 백엔드만"],
        ["IntentGuard", "6.43", "설계 문서뿐"],
        ["Hanga · Reloved · PetZonic · AIsle", "5.2~6.0", "뼈대 단계"]], [30, 22, 48], 25),
    notes="공식 분야가 다른 팀(OmniLocate는 미디어, IntentGuard는 금융)도 주제가 가까워 넣었다.")

slide("us", "우리 점수", "자동 등록과 봉인 시험으로 올랐지만, 처음 보는 제품 숫자가 발목을 잡는다", col(
    table(["", "근거"], [
        [ok("올린 것"), "아무 형식 문서 자동 등록(사람은 확인만, 항목 10개 이하), 규제 원문으로 만든 규정 팩, 원본 파일까지 보는 사실 확인, 주입 공격 200회 성공 0, 처음 보는 제품 봉인 시험"],
        [bad("깎인 것"), "처음 보는 제품(2차 봉인) 83~84%, 1차 세트와 10%p 차이, 서버 1대·메모리 저장, 비용 숫자 없음"]], [16, 84], 25),
    t("1차 채점 8.40 → codex 7.9 (기술 30/40, 문제 20/25, 혁신 21.5/25, UX 7.5/10). codex 검토 때 대표 숫자는 72.5%였고, 지금은 83~84%다.", 24, SUB), gap=20),
    notes="codex: '3위는 증명되지 않았다.' 숫자를 근거로 점수를 다시 매기려면 새 3차 봉인 세트 결과가 필요하다.")

slide("gaps", "점수 올릴 일", "심사위원이 물을 것 순서대로", table(["할 일", "무엇을 보여 주나"], [
    ["1. 처음 보는 제품 합격선", "새 3차 봉인 세트로 일반화 증명"],
    ["2. 사람 진행자 비교 시험", "도우미 끔/켬, 정정 성공률·개입 시간"],
    ["3. 저장과 확장", "Firestore, 재시작 복구, 서버 여러 대"],
    ["4. 비용과 지연 실측", "방송 1시간 비용, 끝에서 끝까지 지연"],
    ["5. 'Gemini 단독' 대비표", "이미 잰 설계 후보 D·E 결과로"]], [40, 60], 26),
    notes="에이전트 1차 채점과 codex 검토가 같은 방향을 가리킨다. 2~5번은 배포·인프라 또는 사람이 필요해 사용자 결정이 필요하다.")

write(OUT, "레포 재비교 10/6")
print("wrote", OUT)
