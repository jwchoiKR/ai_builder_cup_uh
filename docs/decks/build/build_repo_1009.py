"""Public AI Builder Cup repos vs our service, 10/9: three models score separately (google-slide-deck design).
Sources: scratchpad cup_repos_1009.md (101 public repos, README + commits since 10/6) and our_status_1009.md;
scores by GPT (codex gpt-6-astra high), Gemini (agy gemini-3.8-flash-high) and the Sonnet critic, each alone.
Run: python docs/decks/build/build_repo_1009.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "repo_compare_1009.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


def warn(x):
    return f"<span style='color:#B06000'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 공개 레포 재비교 · 10/9", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">README만 보면 6~14위,<br>우리 측정 자료까지 보면 2~4위</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">공개 레포 101개, GPT·Gemini·Sonnet이 따로 채점, 배포 링크·영상은 뺌</p></div>''',
      notes="GPT(codex gpt-6-astra high), Gemini(agy gemini-3.8-flash-high), Sonnet 비평 세션이 같은 자료로 서로 모르게 채점했다.")

slide("method", "어떻게 매겼나", "공식 배점 그대로, 공개 자료로 확인되는 구현과 검증만 본다", col(
    table(["항목", "배점", "본 것"], [
        ["기술", "40", "AI가 실제로 판단하는 것, 작동 여부, 평가 증거(규모, 처음 보는 데이터, 숫자), 확장"],
        ["문제", "25", "실제로 겪는 문제인지, 가치가 큰지"],
        ["혁신", "25", "같은 문제를 푸는 다른 방법과 무엇이 다른지"],
        ["UX", "10", "사람이 할 일이 줄었는지"]], [14, 10, 76], 25),
    tags("정해 둔 것",
         chip("배포 링크·영상·꾸밈 제외", "grey"), chip("다른 팀은 README와 커밋만", "grey"),
         chip("우리는 측정된 결과만", "grey"), chip("10/9 변경은 측정 전이라 반영 안 함", "grey")), gap=22),
    notes="사용자 규칙: 경쟁 비교는 서비스 내용만(10/5). 다른 팀 코드는 돌려 보지 않았다.")

slide("field", "참가작 현황", "101개 중 작동과 평가 결과가 확인된 곳은 32개", col(
    rowx(big("동작 + 평가", "32", "", GRN, GRNBG, "개 / 101", ""),
         big("초기 시제품", "36", "", "#B06000", YELBG, "개 / 101", ""),
         big("빈 레포·계획만", "33", "", SUB, SURF, "개 / 101", ""), gap=32),
    t("10/6 상위권 중 Gapline, Taal, SentinelGraph, Groundtruth는 10/6 이후 커밋이 없다. "
      "새로 강하게 올라온 곳은 Taal 작성자의 Emergency Green Corridor(10/6 이후 커밋 29개).", 26, SUB), gap=28),
    notes="GitHub 검색 약 14가지 이름 변형, 코드 검색 3가지, 후보 185개 확인. 비공개 레포와 대회 이름을 안 쓴 레포는 못 찾는다. "
          "같은 프로젝트를 합치면 약 98개. Finwings는 10/6에 이어 여전히 404.")

slide("us", "우리 순위", "셋 다 2~4위, 범위로는 1~8위", col(
    table(["채점", "우리 순위", "점수", "범위", "한 줄"], [
        ["GPT", "3위", "7.70", "1~7위", "처음 보는 제품과 실제 STT로 시험한 점이 강점"],
        ["Gemini", "2위", "8.75", "2~5위", "미노출 134줄 95.5%, p95 4.2초를 높게 봄"],
        ["Sonnet", "4위", "7.3", "2~8위", "오경보 1.6%, 사람 진행자 없음, 서버 1대로 깎음"]],
        [12, 13, 10, 12, 53], 26),
    t("범위는 각 모델이 채점 불확실성을 감안해 직접 낸 것이다. 점수 크기는 모델마다 달라서 순위만 비교한다.", 24, SUB), gap=20),
    notes="Gemini는 전체적으로 점수를 높게 준다(1위 8.90). GPT는 UX를 모두 5점으로 고정했다.")

slide("blind", "같은 조건으로 다시", "README만 보고 어느 팀인지 모르게 매기면 6~14위", col(
    table(["채점", "우리 자료 포함", "블라인드 (README만)", "기술 점수 (블라인드)"], [
        ["GPT", "3위", bad("14위"), "6.5 / 10"],
        ["Gemini", "2위", bad("14위"), "7.5 / 10"],
        ["Sonnet", "4위", warn("6위"), "5.5 / 10"]], [16, 24, 28, 32], 26),
    tags("떨어진 이유 (셋 공통)", chip("README에 측정 숫자가 없음", "red", "x"),
         chip("'Cloud Run, Firestore: not started', 'single process'", "red", "x"),
         chip("문제·UX 점수는 그대로 높음", "green", "check")), gap=24),
    notes="처음 채점은 다른 팀은 README 요약, 우리는 직접 쓴 현황 문서라 비대칭이었다. 블라인드는 우리 README도 같은 요약 방식으로 101개 사이에 섞었다. "
          "이후 README를 측정 결과와 조건, 한계까지 넣어 새로 썼다(8c0961a, 우리 브랜치).")

slide("top", "전체 순위", "세 모델 순위의 평균으로 줄 세우면 1~4위가 평균 1위 안쪽 차이다", table(
    ["평균", "팀", "분야", "GPT", "Gemini", "Sonnet", "강점"], [
        ["1", "Groundtruth", "도시 열환경", "1", "3", "3", "'Gemini 단독 0/18 vs 시스템 16/18' 비교, 비용 실측"],
        ["2", "Emergency Green Corridor", "응급차 경로", "6", "1", "1", "정확도 90%, 지연 3.5초, 부하 시험. 합성 클립 12개"],
        ["3", "<b>Live Studio (우리)</b>", "라이브 커머스", "3", "2", "4", "처음 보는 제품, 실제 STT, 제품별 합격선"],
        ["4", "Gapline", "화면 해설", "4", "4", "2", "음성 인식부터 길이 맞추기까지 연결. 완성 4/6"],
        ["5", "ReadiCheck", "사기 예방", "5", "5", "5", "Gemini Live 실시간 통화. 시험 작음"],
        ["6", "SentinelGraph", "카드 사기", "2", "7", "7", "AUC 0.914(홀드아웃). 에이전트 정확도 미확인"],
        ["7", "ARTHA", "소기업 대출", "7", "6", "11", "레드팀 우회 18 → 0. 합성 데이터"],
        ["8", "Taal", "식품 폐기", "9", "8", "9", "닫힌 고리 설계. 실측은 5회"]],
    [7, 22, 13, 7, 9, 9, 33], 23),
    notes="평균은 세 모델 순위의 평균으로 다시 줄을 세웠다(Groundtruth 2.3, Green Corridor 2.7, 우리 3.0, Gapline 3.3).")

slide("rivals", "앞서거나 바짝 붙은 팀", "세 모델이 공통으로 꼽은 경쟁자는 Groundtruth, Green Corridor, Gapline", table(
    ["팀", "우리보다 나은 점", "약한 점"], [
        ["Groundtruth", ok("시스템이 없을 때와 있을 때를 같은 문제로 비교, 질문당 비용"), "18문항으로 작다"],
        ["Emergency Green Corridor", ok("부하 시험, 추적, 테스트 412개, 공공 가치가 큼"), "합성 클립 12개, 예측은 기준 모델보다 약함"],
        ["Gapline", ok("끝까지 나오는 결과물, 클립당 비용과 시간 측정"), "영상 6개 중 4개만 완성"]],
    [24, 46, 30], 25),
    notes="세 모델 모두 이 세 팀을 '우리를 이길 수 있는 팀'으로 꼽았다(GPT는 Green Corridor 대신 SentinelGraph를 셋째로 둠).")

slide("gap", "우리 강점과 약점", "검증은 앞서고, 실사용과 운영 규모 검증이 없다", table(
    ["", "근거"], [
        [ok("앞서는 점"), "개발자가 본 적 없는 제품으로 시험, TTS 음성을 실제 STT 경로로 통과, 제품별 합격선, 4초 안 판정"],
        [bad("밀리는 점"), "오경보 1.6%(기준 1% 미만), 10/9에 바꾼 로직은 측정 전"],
        [bad("밀리는 점"), "실제 사람 진행자 없이 TTS 음성으로만 시험"],
        [bad("밀리는 점"), "서버 1대, 댓글은 재시작하면 복구 안 됨, 방송당 비용 숫자 없음"],
        [warn("GPT·Sonnet"), "'Gemini 단독 vs 우리 시스템' 비교가 없다"]],
    [18, 82], 26),
    notes="세 모델의 공통 지적. 마지막 줄은 GPT와 Sonnet만 짚었다.")

slide("next", "점수를 올릴 일", "새 기능이 아니라 증거가 점수를 올린다", table(
    ["할 일", "보여 주는 것", "동의한 모델"], [
        ["1. 로직 고정 후 새 제품 묶음으로 측정", "오경보 1% 미만, 탐지 95% 이상", "3/3"],
        ["2. 실제 사람 진행자로 방송", "도우미 끔/켬, 정정 성공률, 시간당 경고", "3/3"],
        ["3. 서버 여러 대와 재시작 복구", "부하 중 지연, 방송당 비용", "3/3"],
        ["4. 'Gemini 단독' 비교표", "같은 줄에서 단독 vs 우리 시스템", "2/3"]],
    [40, 46, 14], 26),
    notes="1, 2, 4는 시험이고 비용이 든다. 할지는 사용자가 정한다. 3의 댓글 복구는 댓글 팀 범위다.")

write(OUT, "레포 재비교 10/9")
print("wrote", OUT)
