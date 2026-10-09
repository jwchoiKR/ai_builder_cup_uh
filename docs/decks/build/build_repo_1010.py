"""Public AI Builder Cup repos vs ours, 10/10: blind scoring of 90 README summaries (google-slide-deck design).
Sources (scratchpad of the 10/10 planning session): cup_repos_1010.md (89 public entries, 816 candidates checked),
our_entry_1010.md (our README summarized by a separate reader with the same rules), blind_entries_1010.md (all 90
mixed, ids E01-E90), scores by GPT (codex gpt-6-astra high), Gemini (Vertex gemini-3.8-flash HIGH) and Sonnet,
each alone; combined_1010.json (mean rank). Run: python docs/decks/build/build_repo_1010.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "repo_compare_1010.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 공개 레포 재비교 · 10/10", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">README만 보고 90개 중 3위,<br>1~3위는 점수 차이가 거의 없다</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">우리를 포함한 90팀을 GPT·Gemini·Sonnet이 어느 팀인지 모른 채 따로 채점</p></div>''',
      notes="10/9에는 README만 보고 매기면 6~14위였다. 그 뒤 README를 측정 결과와 조건, 한계를 넣어 새로 썼다(8c0961a, 10/10 main에 반영).")

slide("method", "어떻게 매겼나", "모든 팀을 README 요약 하나와 같은 배점으로 매겼다", col(
    table(["항목", "배점", "본 것"], [
        ["기술", "40", "AI가 실제로 판단하는 것, 끝까지 도는지, 평가 증거(규모, 처음 보는 데이터, 숫자), 배포 구조"],
        ["문제", "25", "실제 사용자가 겪는 문제인지, 가치가 큰지"],
        ["혁신", "25", "같은 문제를 푸는 뻔한 방법과 무엇이 다른지"],
        ["UX", "10", "사람이 할 일이 얼마나 줄었는지"]], [14, 10, 76], 25),
    tags("정해 둔 것",
         chip("README 요약만 봄 (우리도 같음)", "grey"), chip("우리 요약은 다른 모델이 같은 규칙으로 씀", "grey"),
         chip("레포 이름만 있고 '우리'라는 표시 없음", "grey"), chip("배포 링크·영상·꾸밈 제외", "grey")), gap=22),
    notes="후보 816개를 확인해 대회 참가작 89개를 남겼다(다른 대회, 빈 레포, 비공개 전환 3개 제외). "
          "10/9의 약 98개보다 적은 이유: 이번에는 로그인이 필요한 코드 검색을 못 했다. 대회 이름을 안 쓴 레포와 비공개 레포는 찾을 수 없다.")

slide("top", "전체 순위", "세 모델이 모두 1~3위로 꼽은 팀은 셋, 우리가 그 안에 있다", col(table(
    ["순위", "팀", "분야", "GPT", "Gemini", "Sonnet", "한 줄"], [
        ["1", "Groundtruth", "도시 열환경", "1위 8.35", "2위 8.37", "1위 7.50", "'Gemini 단독 0/18 vs 시스템 16/18' 비교, 질문당 비용"],
        ["2", "Gapline", "화면 해설", "3위 7.92", "1위 8.41", "2위 7.40", "클립 6개 실측, 비용과 지연, 완성은 4/6"],
        ["3", "<b>Live Studio (우리)</b>", "라이브 커머스", "2위 8.30", "3위 8.29", "3위 7.30", "처음 보는 제품 6개, 실제 STT, 탐지 95.5%"],
        ["4", "Nightingale", "보행 안내", "4위", "5위", "6위", "현장 확인 경로, 테스트 547개"],
        ["5", "ARTHA", "소기업 대출", "6위", "6위", "4위", "레드팀 시험, 합성 데이터"],
        ["6", "SentinelGraph", "사기 조사", "5위", "7위", "5위", "홀드아웃 비교, 실제 효과 미확인"],
        ["7", "Green Corridor", "응급차 경로", "9위", "8위", "7위", "테스트 412개, 합성 클립"],
        ["8", "ReadiCheck", "사기 예방", "7위", "9위", "9위", "Gemini Live 통화, 시험 규모가 작음"]],
    [7, 20, 13, 11, 11, 11, 27], 23),
    t("순위는 세 모델 순위의 평균. 점수 평균으로 매기면 우리 2위(7.96), Gapline 3위(7.91)다.", 24, SUB), gap=14),
    notes="순위는 세 모델 순위의 평균으로 다시 줄 세웠다(Groundtruth 1.33, Gapline 2.00, 우리 2.67, Nightingale 5.00). "
          "모델마다 점수 크기가 달라서, 점수를 모델별로 표준화해 평균을 내면 우리가 2위(1.60), Gapline 3위(1.58)로 바뀐다. 1~3위는 동률로 본다.")

slide("us", "우리 점수", "기술 점수는 1위 팀과 같은 수준, Sonnet은 문제·혁신·UX를 낮게 봤다", col(
    table(["채점", "기술", "문제", "혁신", "UX", "합계", "순위", "한 줄"], [
        ["GPT", "8.4", "8.5", "8.1", "7.9", "8.30", "2위", "미노출 제품 음성 시험. 최근 단순화와 사람 사용은 미검증"],
        ["Gemini", "8.6", "8.0", "8.3", "7.7", "8.29", "3위", "실시간 STT와 봉인 세트 측정"],
        ["Sonnet", "8.5", bad("6.5"), bad("6.5"), bad("6.5"), "7.30", "3위", "288줄 봉인 세트, 2회 실행, 경고 지연 측정"]],
        [11, 8, 8, 8, 8, 9, 8, 40], 24),
    t("1위 Groundtruth의 기술 점수는 8.6 / 8.7 / 8.5. Sonnet 합계 차이는 0.2점(7.50 대 7.30)이고, 문제·혁신에서 0.5점씩 벌어졌다.", 26, SUB), gap=20),
    notes="세 모델 모두 기술 점수는 8.4~8.6으로 상위 3팀과 같은 수준이다.")

slide("change", "10/9와 비교", "README를 측정 결과로 다시 쓴 뒤 6~14위에서 2~3위로 올랐다", col(
    rowx(big("10/9 · 고치기 전 README", "6~14위", "", RED, REDBG, "약 101개 중", ""),
         big("10/10 · 고친 README", "2~3위", "", GRN, GRNBG, "90개 중, 모델별", ""), gap=32),
    tags("바뀐 것", chip("측정 숫자와 조건, 한계를 README에 넣음", "green", "check"),
         chip("'not started', 'single process' 문구 삭제", "green", "check"),
         chip("main에 반영 (10/10)", "green", "check")),
    t("참가작 수가 다른 것은 찾는 방법 차이다. 10/9에는 로그인 코드 검색까지 했다.", 24, SUB), gap=26),
    notes="10/9 블라인드 채점에서 세 모델 모두 'README에 측정 숫자가 없다', 'Cloud Run, Firestore: not started'를 이유로 깎았다. "
          "10/10 README 수정 3줄(테스트 결과 출처 박스 삭제 등)은 우리 브랜치에만 있고 main에는 아직 없다.")

slide("rivals", "앞선 두 팀", "앞선 두 팀은 비교 실험과 비용을 숫자로 보여 줬다", table(
    ["팀", "강점", "약한 점"], [
        ["Groundtruth", ok("Gemini 혼자 풀 때와 시스템으로 풀 때를 같은 문제로 비교 (0/18 → 16/18), 질문당 비용"), bad("18문항으로 작다")],
        ["Gapline", ok("클립당 비용과 시간 실측, 결과물이 끝까지 나옴"), bad("영상 6개 중 4개만 완성")],
        ["우리", ok("처음 보는 제품, 실제 STT 경로, 제품별 합격선"), bad("오경고 1.6%, 비용 숫자 없음, 사람 진행자 시험 없음")]],
    [18, 52, 30], 25),
    notes="GPT와 Sonnet 모두 1위의 강점으로 'Gemini 단독 vs 시스템' 비교를 꼽았다.")

slide("next", "점수를 올릴 일", "새 기능보다 증거가 순위를 가른다", table(
    ["할 일", "보여 주는 것", "비용"], [
        ["1. 'Gemini 단독' 비교", "같은 줄을 Gemini 한 번 호출로 판정 vs 우리 시스템", "Gemini 호출 필요 (작게)"],
        ["2. 방송당 비용 숫자", "저장된 호출 기록의 토큰으로 계산", "없음"],
        ["3. 10/9~10/10 변경 후 재측정", "오경고 1% 미만, 탐지 95% 이상", "Gemini 호출 필요"],
        ["4. 사람 진행자 방송", "정정 성공률, 시간당 경고", "사람 시간"]],
    [32, 48, 20], 25),
    notes="1과 3은 비용이 들어서 사용자가 정한다. 2는 Firestore에 남은 agent_calls의 usage로 바로 계산할 수 있다.")

slide("retail", "리테일·커머스 분야", "리테일·커머스 6팀 중에서는 1위", table(
    ["분야 순위", "팀", "전체 순위 (평균)", "한 줄"], [
        ["1", "<b>Live Studio (우리)</b>", "3위", "실시간 판정, 봉인 세트 측정"],
        ["2", "Taal", "10위", "예측 → 할인 계획 → 사람 승인, 합성 데이터"],
        ["3", "Varelyx", "29위", "다국어 공급 차질 대응, 검증은 고정 시나리오"],
        ["4", "AIsle", "50위", "매장 영상 분석 계획, 정확도 측정 없음"],
        ["5", "Hanga", "53위", "소상공인 재고, 모델 연결이 아직 막힘"],
        ["6", "Cutback", "77위", "가상 화면 시제품"]],
    [14, 30, 16, 40], 25),
    notes="README에 Retail & Commerce라고 적은 참가작 기준.")

write(OUT, "레포 재비교 10/10")
print("wrote", OUT)
