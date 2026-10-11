"""Fact-checker and compliance-judge model/thinking arms on sealed pool 8 (10/11 night - 10/12). google-slide-deck design.
Source: sealed_sets/results/pool8s_{base,cot_v,med,38,cmedium_nc,c38_nc,chigh_nc}, scored with rescore_live.py --semantic
--restore and onboarding8/score8.py (headline strata). Examples on the slides are made up; no sealed line is shown.
Run: python docs/decks/build/build_judges_1012.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "judges_1012.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


def warn(x):
    return f"<span style='color:#B06000'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("판정 모델 비교 · 8차 봉인 세트(진단용) · 10/11 밤 ~ 10/12", "blue")}
<h1 style="font-size:80px; font-weight:500; line-height:1.15">팩트체커는 3.8 Flash LOW,<br>규제 판정은 생각을 시키면 잘못된 빨간 경고가 9건에서 1건</h1>
<p style="font-size:36px; color:{SUB}; line-height:1.45">대신 규제 판정이 느려진다. 그리고 00:43(KST)부터 Gemini 호출이 전부 403으로 막혀 두 실험은 끝나지 못했다</p></div>''',
      notes="팩트체커 비교 4가지와 규제 판정 비교 3가지를 같은 336줄(안전)·120줄(위험)로 쟀다. 8차 세트는 이미 본 세트라 진단용이다.")

slide("setup", "어떻게 쟀나", "같은 문장, 한 번에 판정 하나만 바꿨다", col(
    table(["항목", "내용"], [
        ["세트", "8차 봉인 세트: 처음 만든 6개 제품, 위험 120줄 · 안전 336줄(헤드라인). 이미 본 세트라 진단용"],
        ["음성", "목소리 A(Windows TTS) → Chirp 3 STANDARD → 판정. 한 제품씩 차례로, 병렬 없음"],
        ["코드", "fd1f612 (온보딩 팀의 여러 용량 가격 반영, 6개 제품 다시 온보딩, 사람 수정 없음)"],
        ["바꾼 것", "팩트 실험: 팩트체커만 / 규제 실험: 규제 판정만 (팩트체커는 Flash-Lite LOW 고정)"],
        ["속도 재는 법", "판정 호출 1번의 입력→출력. 재시도는 합치지 않고, 실패는 따로 센다 (사용자 10/12)"],
        ["5초", "넘으면 아쉬운 목표이지 답을 버리는 선이 아니다 (사용자 10/12). 규제 실험은 마감 60초로 끊지 않고 쟀다"]],
        [18, 82], 25),
    t("채점: rescore_live (semantic, restore). 바뀐 줄은 모두 열어 봤다. 잘못된 빨간 경고 10줄은 critic이 실험을 가린 채 다시 봤고, 10줄 모두 정말 잘못된 경고였다(라벨 변경 없음).", 24, SUB), gap=18),
    notes="팩트 실험의 규제 판정은 5초 마감이 있던 때의 설정이다. 규제 실험만 60초로 바꿨다.")

slide("fact", "팩트체커 비교", "3.8 Flash LOW가 팩트 오경보를 11줄에서 2줄로 줄였다", col(
    table(["방법", "감지", "오경보 (팩트체커 탓)", "팩트 판정 1번 p50 / p95 / 최대", "판단"], [
        ["Flash-Lite LOW (지금)", "114/120", "14 (11)", "0.9 / 1.5 / 4.6초", "기준"],
        ["CoT (주장마다 이유)", "114/120", "15 (12)", "1.0 / 2.6 / 4.4초", bad("효과 없음")],
        ["Flash-Lite MEDIUM", "114/120", "10 (7)", "2.2 / 4.1 / 5.0초", warn("조금 나음, 느림")],
        ["3.8 Flash LOW", "114/120", ok("5 (2)"), "1.9 / 3.5 / 5.0초", ok("후보")]],
        [24, 11, 20, 27, 18], 25),
    t("CoT가 안 된 이유: 이유를 주장마다 따로 쓰게 해서, 모델이 문장을 먼저 쪼갠 뒤 \"$37\"을 혼자 판정했다. 3.8에 남은 팩트 오경보 2줄은 STT가 문장 모양을 바꾼 경우다(물음표가 빠짐, 단정이 질문이 됨).", 24, SUB),
    t("비용: 3.8 팩트체커는 시간당 약 +$0.5 (입력의 86%가 캐시). 3.8은 2027-01-01부터 가격이 두 배.", 24, SUB), gap=18),
    notes="팩트 판정의 최대 5.0초는 5초 마감에 걸린 호출이다. 감지 114는 네 방법이 같다. MEDIUM과 3.8은 채점표 필드 차이로 1줄(맞게 경고함)을 놓친 것으로 집계돼 실제로는 115다.")

slide("why_comp", "왜 규제 판정을 쟀나", "남은 잘못된 빨간 경고는 모두 규제 판정에서 나왔다", flows(
    t("남의 말을 옮기고 부정한 문장 (만든 예시)", 28, INK, 700),
    (says("진행자", "\"누가 이게 관절염을 낫게 한대요. 아니요, 그렇게 말할 수 없어요.\""),
     ai("규제 판정 (LOW)", "질병 치료 주장으로 판단"), result("빨간 경고 (틀림)", "red")),
    divider(),
    t("사실 오류 문장 (만든 예시)", 28, INK, 700),
    (says("진행자", "\"상처 난 피부에도 발라요.\""),
     ai("규제 판정 (LOW)", "ASEAN 2-d(질병 치료·예방)를 붙임"), result("빨간 경고 (틀림): 주황 사실 경고가 맞음", "red")),
    gap=18),
    notes="Flash-Lite LOW 4번(9, 8, 9, 8건). 생각 토큰 0개. 10/8에 MEDIUM에서 LOW로 낮췄는데(D-360) 이유는 기록에 없다. 7차 세트(규제 MEDIUM)에서는 잘못된 빨간 경고가 0건이었다.")

slide("comp", "규제 판정 비교", "MEDIUM은 잘못된 빨간 경고를 9건에서 1건으로 줄였다", col(
    table(["규제 판정", "잘못된 빨간 경고", "규제 위반 감지", "오경보", "생각 토큰"], [
        ["Flash-Lite LOW (지금, 4번)", "9 · 8 · 9 · 8", "66/66", "14 · 15 · 10 · 5 *", "0"],
        ["Flash-Lite MEDIUM", ok("1"), "65/66", "12", "580"],
        ["3.8 Flash LOW (W1~W3만)", ok("0 (LOW 3)"), "W1~W3 33/33 (LOW 33)", "7 (LOW 9)", "2"],
        ["Flash-Lite HIGH", bad("무효 (403)"), "-", "-", "-"]],
        [27, 19, 22, 18, 14], 25),
    t("* LOW 4번의 오경보 차이는 팩트체커를 바꾼 탓이다. MEDIUM에서 규제 판정 탓 오경보는 3줄 → 0줄. 사라진 빨간 경고 9건: 옮기고 부정한 문장 3줄, 사실 오류에 붙던 빨간 경고 6줄. 남은 1줄은 \"알레르기 걱정 없음\"류.", 24, SUB),
    t("새로 놓친 1줄: STT가 질병 치료 주장을 질문처럼 적은 문장(\"…낫게 해요?\")을 MEDIUM이 질문으로 읽었다.", 24, SUB), gap=18),
    notes="미리 정한 채택 조건: 잘못된 빨간 경고 4건 이하이고 LOW가 맞힌 줄을 새로 틀리지 않음 / 감지 1줄 넘게 줄지 않음 / 오경보 늘지 않음 / 경보 p95 5초 이하, 실패 1% 이하. MEDIUM은 앞의 셋을 통과, 속도에서 걸렸다.")

slide("speed", "속도", "MEDIUM은 정확해졌지만 호출 5%가 5초를 넘는다", col(
    table(["규제 판정 호출 1번", "p50", "p95", "최대", "5초 넘음", "실패"], [
        ["Flash-Lite LOW (5초 마감 있음)", "1.2초", "2.8초", "3.9초", "0/592", "6 (마감)"],
        ["Flash-Lite MEDIUM (마감 없음)", "2.7초", warn("5.1초"), bad("45.7초"), warn("32/592 (5.4%)"), "0"],
        ["3.8 Flash LOW (W1~W3, 마감 없음)", "2.3초", "4.4초", bad("35.4초"), "7/292 (2.4%)", "0 **"]],
        [34, 11, 11, 12, 18, 14], 25),
    table(["진행자 화면 빨간 경고", "p50", "p95", "최대", "5초 넘음"], [
        ["Flash-Lite LOW", "1.5초", "3.4초", "6.2초", "1/80"],
        ["Flash-Lite MEDIUM", "4.1초", warn("5.9초"), bad("37.1초"), warn("15/69")]],
        [34, 14, 14, 14, 24], 25),
    t("** 403으로 막힌 뒤의 호출은 뺐다. 30~45초짜리 긴 꼬리는 드물지만(호출 600번 중 1~2번) 진행자에게는 그 경고가 사실상 안 뜬 것과 같다.", 24, SUB), gap=20),
    notes="빨간 경고 시간은 진행자 화면 기준이라 문장이 끝난 뒤부터 잰다. 재시도는 마감이 없어서 거의 없었다.")

slide("block", "중단", "00:43(KST)부터 이 프로젝트의 Gemini 호출이 전부 403으로 거절된다", col(
    table(["무엇", "상태"], [
        ["오류", "403 PERMISSION_DENIED: \"Request rejected in accordance with our terms of use and policies.\""],
        ["범위", "Flash-Lite, 3.8 Flash, 2.5 Flash 모두. global, us-central1 모두. \"Say OK.\" 한 줄도 거절 (01:30 확인)"],
        ["영향", "Flash-Lite HIGH 전부 무효, 3.8 LOW는 W4~W6 무효. 배포된 앱(Cloud Run)도 같은 프로젝트라 판정이 안 될 것"],
        ["한 것", "실험 중단, VM 끔, 같은 호출 반복 안 함. 권한·설정은 건드리지 않음"]],
        [14, 86], 25),
    tags("사용자가 확인할 것", chip("Cloud 콘솔·프로젝트 소유자 메일의 정책 알림", "yellow", "warn"),
         chip("Vertex AI 사용 제한 여부", "yellow", "warn"), chip("풀리면 HIGH와 3.8 W4~W6만 다시", "grey")), gap=24),
    notes="15:43 UTC부터 VM과 이 PC 모두에서 같은 오류. 원인은 아직 모른다. 429(용량)와 달리 정책 거절 메시지다.")

slide("next", "판단", "규제 판정은 정확도를 위해 생각이 필요하다. 남은 건 속도와 3.8 비교", col(
    table(["", "지금 판단", "다음"], [
        ["팩트체커", ok("3.8 Flash LOW 후보"), "9차 세트(처음 보는 제품, 두 목소리)로 확인 후 기본값 변경"],
        ["규제 판정", warn("MEDIUM: 정확도 통과, 속도 미달"), "막힘이 풀리면 HIGH와 3.8 LOW(W4~W6)를 마저 재고 셋 비교"],
        ["5초 마감", "지금 코드는 5초 넘은 답을 버림", "늦어도 보여 주게 바꿀지 결정 (GPT·Gemini·critic 검토 후 개발)"],
        ["9차 세트", "문서(영어·한국어)·문장·라벨·두 목소리 음성 준비 끝", "온보딩·STT·판정 실행은 Gemini 막힘이 풀린 뒤"]],
        [16, 34, 50], 25),
    t("심사위원 시점: \"모델을 바꿔 좋아졌다\"는 같은 문장으로 나란히 잰 표가 있어 설득력이 있다. 다만 8차는 본 세트라 증거가 약하고, 규제 판정의 30초대 긴 꼬리는 생방송 도구로서 바로 지적받는다. 9차 세트 결과와 긴 꼬리 대책이 함께 있어야 한다.", 24, SUB), gap=20),
    notes="채택 조건은 실험 전에 정했고 GPT·Gemini·critic이 검토했다. 결과를 본 뒤 조건을 바꾸지 않는다.")

write(OUT, "판정 모델 비교 10/12")
print("wrote", OUT)
