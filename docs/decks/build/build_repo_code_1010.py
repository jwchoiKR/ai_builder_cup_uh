"""Code-level re-scoring of AI Builder Cup entries, 10/10 (google-slide-deck design).
Sources (scratchpad of the 10/10 planning session): all 95 public entry repos cloned read-only and scanned
(code_scan.csv: lines, tests, Google AI calls); 24 entries reviewed by reading the code (code_sheets_A..F.md:
README top 15 + 9 with large code bases but low README rank); code_entries_1010.md (README summary + code sheet);
scores by GPT (codex gpt-6-astra high), Gemini (Vertex gemini-3.8-flash HIGH) and Sonnet, each alone
(combined_code_1010.json). Run: python docs/decks/build/build_repo_code_1010.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "repo_code_1010.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 코드까지 본 재비교 · 10/10", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">코드까지 보면 24팀 중 3위,<br>상위 5팀은 한 묶음</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">공개 레포 95개를 내려받아 읽고, GPT·Gemini·Sonnet이 따로 채점</p></div>''',
      notes="README만 본 순위(90팀 중 3위)는 repo_compare_1010.html. 이번에는 코드가 README 내용을 실제로 뒷받침하는지 봤다.")

slide("method", "어떻게 매겼나", "README가 아니라 코드를 기준으로 다시 매겼다", col(
    table(["단계", "한 일"], [
        ["1. 전체 훑기", "참가작 레포 95개를 내려받아 코드 줄 수, 테스트 수, Google AI 호출을 셌다 (실행은 안 함)"],
        ["2. 대상 고르기", "README 순위 상위 15팀 + README는 약하지만 코드가 큰 9팀 = 24팀"],
        ["3. 코드 읽기", "팀마다 AI가 실제로 하는 일, 끝까지 도는지, 결과 파일, 테스트, 배포를 사실로만 정리"],
        ["4. 채점", "README 요약 + 코드 요약을 보고 세 모델이 따로 채점. README와 코드가 다르면 코드를 믿음"]],
        [18, 82], 25),
    tags("배점 (대회 공식)", chip("기술 40", "grey"), chip("문제 25", "grey"), chip("혁신 25", "grey"), chip("UX 10", "grey")),
    gap=22),
    notes="우리 레포의 ADK 사용(ai_pd.py)은 코드 요약에서 빠져 있어 코드 위치를 근거로 덧붙였다. 다른 팀의 누락은 확인하지 못했다.")

slide("top", "코드 기준 순위", "상위 5팀은 세 모델 모두 1~5위 안에 넣었다", col(table(
    ["순위", "팀", "분야", "GPT", "Gemini", "Sonnet", "한 줄"], [
        ["1", "Gapline", "화면 해설", "1위", "1위", "2위", "STT·Gemini·TTS가 끝까지 연결, 결과 CSV, 테스트 약 450개"],
        ["2", "Taal", "식품 할인", "2위", "4위", "1위", "평가 원본 결과를 레포에 공개, 나쁜 결과도 그대로"],
        ["3", "<b>Live Studio (우리)</b>", "라이브 커머스", "4위", "2위", "5위", "실시간 STT + 판정 3개 병렬, 숫자는 글로만 있음"],
        ["4", "Green Corridor", "응급차 경로", "5위", "3위", "3위", "ADK 에이전트, 12클립 평가 결과, 테스트 326개"],
        ["5", "Groundtruth", "도시 열환경", "3위", "5위", "4위", "'Gemini 단독 0/18 vs 시스템 16/18' 결과 파일"],
        ["6", "ReadiCheck", "사기 예방", "7위", "8위", "7위", "Gemini Live, 평가 숫자는 결과 파일 없음"],
        ["11", "Project-NoX", "업무 자동화", "11위", "9위", "12위", "코드 최대 규모(약 5만 줄), README 순위는 25위"]],
    [7, 18, 13, 8, 9, 9, 36], 23),
    t("순위는 세 모델 순위의 평균. 우리와 Green Corridor는 평균 순위가 같다(3.67).", 24, SUB), gap=14),
    notes="README만 봤을 때 1위였던 Groundtruth는 5위, 10위였던 Taal은 2위가 됐다.")

slide("gap", "README와 코드가 다른 팀이 많다", "숫자를 결과 파일로 확인할 수 있는 팀이 위로 올라갔다", table(
    ["팀", "코드에서 본 것"], [
        ["Taal, Gapline, Groundtruth", ok("README 숫자가 레포의 결과 파일과 일치")],
        ["ARTHA", bad("기본 설정에서 Gemini를 안 씀, '회피 18 → 0' 결과 없음")],
        ["ReadiCheck", bad("평가 숫자가 문서 글에만 있음, 가리킨 폴더도 없음")],
        ["CatSight, Snowflake RuntimeOS", bad("실제로 도는 서버가 AI를 부르지 않음")],
        ["우리", bad("정확도·오경고·지연 숫자가 덱과 인수인계 문서에만 있음 (봉인 세트라 비공개)")]],
    [30, 70], 25),
    notes="코드 요약은 Sonnet 6개가 나눠 썼고, 모두 같은 지시문으로 읽기만 했다.")

slide("next", "점수를 올릴 일", "기능보다 '확인할 수 있는 증거'가 순위를 가른다", table(
    ["할 일", "효과", "비용"], [
        ["1. 결과 파일 공개", "봉인 문장은 빼고 제품별 집계표(탐지, 오경고, 지연)를 레포에 올림", "없음"],
        ["2. README에 ADK 명시", "AI PD가 ADK LlmAgent인데 README에 없음", "없음"],
        ["3. 로직 확정 후 재측정", "10/9 이후 변경을 측정한 숫자로 교체", "Gemini 조금"],
        ["4. README의 '서버 1대' 설명 고치기", "Cloud Run 자동 확장을 꺼 둔 이유와 재시작 복구(확인함)를 설명, 가능하면 동시 방송 수 측정", "없음 (측정은 조금)"]],
    [30, 52, 18], 25),
    notes="세 모델 공통 감점: 결과 파일 없음, 최근 변경 미측정, README에 적은 'One Cloud Run instance'(max-instances 1). Cloud Run 사용 자체가 아니라 확장을 꺼 둔 설정이 지적됐다.")

write(OUT, "레포 코드 재비교 10/10")
print("wrote", OUT)
