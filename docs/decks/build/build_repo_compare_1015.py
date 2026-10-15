"""Code-level comparison of every public AI Builder Cup entry, 10/15 (google-slide-deck design).
Sources (outside git, C:\\code_test\\study\\ai_builder_cup_git\\cup1015): cup_repos_1015.md (GitHub search, 2,477 candidates,
227 entries + 22 unclear), all 249 repos plus ours cloned read-only and scanned (code_scan.csv), fact sheets from the code
by 10 Sonnet readers (sheets/sheet_b00..b09.md, 25 repos each), scores by GPT (codex gpt-6-astra high), Gemini (Vertex
gemini-3.8-flash HIGH) and Sonnet, each alone (score_*.md), merged by mean rank (merge_scores.py -> combined_1015.json; after Model Armor was turned on, GPT re-scored ours alone: rescore_armor_gpt.md, merge_scores_armor.py -> combined_1015_armor.json).
Run: python docs/decks/build/build_repo_compare_1015.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "repo_compare_1015.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 전체 참가작 코드 비교 · 10/15", "blue")}
<h1 style="font-size:88px; font-weight:500; line-height:1.15">248팀 중 7위,<br>리테일 28팀 중 2위</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">공개 레포를 모두 내려받아 코드를 읽고, GPT·Gemini·Sonnet이 따로 채점</p></div>''',
      notes="10/10에는 README로 90팀 중 3위, 코드로 24팀 중 3위였다. 이번에는 찾은 참가작 전부의 코드를 읽었다. 그사이 참가작이 크게 늘었다. 처음 채점은 10위였고, Model Armor를 다시 켠 뒤 GPT가 우리만 다시 채점해 88점이 89점이 되면서 7위가 됐다.")

slide("method", "어떻게 매겼나", "README가 아니라 코드를 읽고 매겼다", col(
    table(["단계", "한 일"], [
        ["1. 찾기", "GitHub 검색 156번, 후보 2,477개를 확인했다. 참가작 227개 + 대회 이름만 있는 불분명 22개"],
        ["2. 내려받기", "249개와 우리 레포를 모두 내려받아 코드 줄 수, 테스트 수, Google AI 호출을 셌다 (실행은 안 함)"],
        ["3. 코드 읽기", "Sonnet 10개가 25개씩 나눠 읽고 사실만 정리했다. AI가 하는 일, 끝까지 도는지, 결과 파일, 배포, README와 코드가 다른 곳"],
        ["4. 채점", "세 모델이 정리본 250개를 따로 채점했다. README와 코드가 다르면 코드를 믿는다. 세 순위의 평균으로 최종 순위를 냈다"]],
        [16, 84], 25),
    tags("배점 (대회 공식)", chip("기술 40", "grey"), chip("문제 25", "grey"), chip("혁신 25", "grey"), chip("UX 10", "grey")),
    gap=22),
    notes="다른 대회 이름이 적힌 2개(Code for Communities)는 순위에서 뺐다. 그래서 248팀이다. 비공개 레포와 대회 이름을 안 쓴 팀은 찾을 수 없다.")

slide("top", "코드 기준 순위", "상위 3팀은 세 모델이 모두 1~6위에 넣었다", col(table(
    ["순위", "팀", "분야", "GPT", "Gemini", "Sonnet", "평균 점수"], [
        ["1", "Andon Agent", "제조 고장 원인", "1위", "2위", "1위", "93.3"],
        ["2", "Pramaan", "제조 규제 서류", "2위", "6위", "2위", "91.7"],
        ["3", "CatSight", "재보험 계약", "3위", "4위", "3위", "91.7"],
        ["4", "Taal", "리테일 할인", "6위", "1위", "4위", "91.3"],
        ["5", "GoldenHour Scam", "금융 사기 피해 복구", "4위", "5위", "12위", "89.0"],
        ["7", "<b>Live Studio (우리)</b>", "라이브 커머스", "11위", "11위", "9위", "88.3"],
        ["10", "Shop Honest", "리테일 다크패턴", "14위", "13위", "10위", "87.3"]],
    [8, 26, 22, 10, 11, 11, 12], 24),
    t("우리 점수: 기술 36.0 · 문제 22.3 · 혁신 22.0 · UX 8.0 (세 모델 평균). 상위 4팀의 기술 점수는 37.7 ~ 39.0이다.", 24, SUB), gap=14),
    notes="Model Armor를 켠 뒤 GPT가 우리만 다시 채점했다(88점에서 89점, 기술 +1). 다른 팀은 다시 채점하지 않았다. 처음 채점에서 우리는 10위였다. 6~10위는 점수 차가 1점 안쪽이다. 10/10에 1위였던 Gapline은 19위가 됐다.")

slide("field", "참가작 전체 모습", "참가작 4개 중 1개는 AI가 실제로 돌지 않는다", table(
    ["코드에서 본 것", "팀 수"], [
        ["빈 레포, 템플릿, README만 있음 (평균 30점 미만)", "29"],
        ["평균 50점 미만 (위 29팀 포함)", "64"],
        ["Google AI 호출 코드가 없음 (자동 검사)", "59"],
        ["Gemini가 기본으로 꺼져 있거나 가짜 응답 (읽어서 확인)", "흔함"],
        ["README가 ADK·BigQuery 등을 쓴다는데 코드에 없음", "흔함"]],
    [80, 20], 26),
    notes="'흔함' 두 줄은 Sonnet 10개의 보고에서 셌고 정확한 수는 세지 않았다. 59팀은 자동 검사라 다른 SDK를 쓰는 팀이 섞일 수 있다.")

slide("gap", "위 팀과의 차이", "상위 팀은 결과 파일과 비교 기준을 레포에 올렸다", table(
    ["팀", "레포에 있는 증거"], [
        ["Andon Agent", ok("평가 실행 폴더 10개. 원인 맞힘 전체 시스템 0.983 vs 프롬프트 하나 0.917 vs 기존 방식 0.15")],
        ["Taal", ok("공격 시험 원본 결과, 실패한 공격과 결론 없는 결과까지 공개")],
        ["Pramaan", ok("평가 보고서와 지표 파일. 222개 항목, 실행 날짜별 89 ~ 100%")],
        ["CatSight", ok("결과 파일에 186개 중 185개. 같은 문구로 다듬어 상한이라는 단서까지 적음")],
        ["우리", bad("탐지·오경보·지연 숫자가 README와 덱에만 있음. 봉인 세트라 원본이 레포에 없음")],
        ["우리", "처음 채점 때는 Model Armor가 꺼져 있었음. " + ok("10/15 다시 켬, GPT 재채점 88 → 89점")]],
    [24, 76], 25),
    notes="GPT가 우리에게 단 이유: 'headline sealed-set artifacts unavailable and Model Armor disabled'. Gemini와 Sonnet은 Chirp 3 실시간 STT와 판정 구조, 테스트 596개를 높게 봤다.")

slide("next", "점수를 올릴 일", "기능보다 확인할 수 있는 증거가 순위를 가른다", col(table(
    ["할 일", "효과", "비용"], [
        ["1. 결과 집계 파일 공개", "봉인 문장은 빼고 제품별 탐지·오경보·지연 집계를 레포에 올림", "없음"],
        ["2. 'Gemini 혼자 vs 우리 시스템' 비교", "상위 팀처럼 비교 기준을 둠", "Gemini 조금"],
        ["3. Model Armor 다시 켜기", ok("완료: team-pjt 배포(00034)에서 켬, 댓글 검사 호출 200 확인"), "없음"]],
    [30, 54, 16], 25),
    tags("오늘 고친 것 (d85de43)", chip("README의 판정 모델과 인스턴스 수를 코드와 맞춤", "green", "check"),
         chip("README에 ADK AI PD 에이전트 추가", "green", "check")),
    gap=24),
    notes="README는 판정 3개 모두 Flash-Lite, 인스턴스 최대 3개라고 적혀 있었다. 코드는 판정 4개(사실 확인과 프롬프터는 3.8 Flash), 인스턴스 1개다. 채점은 고친 README 기준이다.")

write(OUT, "참가작 코드 비교 10/15")
print("wrote", OUT)
