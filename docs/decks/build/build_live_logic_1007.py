"""10/7 deck: the live judging logic we will use (fact prompt v3, Flash-Lite, seed, STT STANDARD) and its test results.
Run: python docs/decks/build/build_live_logic_1007.py
Numbers from sealed_sets/results/all_arms_1007{b,c}.json (docs_arms.py, scorer v3 --semantic --restore). Examples are made up."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "live_logic_1007.html"
RES = Path(r"C:\code_test\study\ai_builder_cup_git\sealed_sets\results")
D = {}
for f in sorted(RES.glob("all_arms_*.json")):
    D.update(json.load(open(f, encoding="utf-8")))


def ab(arm, key, fmt="{:.1f}%"):
    a, b = D[f"{arm}/onboarding5_sttzs"][key], D[f"{arm}/onboarding5_sttds"][key]
    return f"{fmt.format(a)} / {fmt.format(b)}"


def p95(arm):
    a, b = D[f"{arm}/onboarding5_sttzs"]["ms_p95"], D[f"{arm}/onboarding5_sttds"]["ms_p95"]
    return f"{a / 1000:.1f} / {b / 1000:.1f}초"


def row(label, arm):
    return [label, ab(arm, "detection"), ab(arm, "false"), ab(arm, "wrong_high", "{}"), p95(arm)]


slide("sum", "10/7 · 방송 중 판정 로직", "Flash-Lite 한 번 판정 + 사실 확인 프롬프트 v3 + seed로 간다", col(
    rowx(fx(big("탐지", "97.2%", "99.1%", GRN, "#E6F4EA", "목소리 A", "목소리 B · 기준 95% 이상")),
         fx(big("오경고", "0.9%", "0.9%", YEL, "#FEF7E0", "목소리 A", "목소리 B · 기준 1% 미만")),
         fx(big("경고 p95", "4.3초", "3.6초", GRN, "#E6F4EA", "목소리 A", "목소리 B · 기준 5초 이하")), gap=24),
    tags("5차 세트 전체로는", chip("탐지·잘못된 HIGH·지연은 기준 안", "green", "check"),
         chip("오경고는 108줄 중 1줄 (0.9%)", "yellow", "warn")),
    tags("제품별로는 2개가 아직", chip("1번 제품: 150ml 오경고 1줄", "red", "x"),
         chip("3번 제품: 단서 빠짐 1줄 놓침", "red", "x")),
    gap=28),
    notes="seed 7 1회차 기준(0ebdc1a, FACT_PROMPT=v3, SINGLE_THINKING=MEDIUM, SINGLE_FACTS_THINKING=LOW, JUDGE_SEED=7, STT STANDARD). "
          "5차 세트는 이미 여러 번 본 세트라 진단용. 새 제품 6차 세트(진행자 2명 포함)는 측정 중.")

slide("arch", "로직", "진행자 말 한 줄이 경고가 되기까지", col(
    lanes(stage("문장이 끝나면 세 판정이 동시에 돈다"),
          (node("person", "진행자 말", use="마이크"),
           node("ai", "글자로 바꾸기", "문장 끊기 STANDARD", use="STT chirp_3"),
           stack(node("ai", "규정 판정", "규정 팩", use="Flash-Lite · MEDIUM"),
                 node("ai", "사실 확인", "원본 문서 캐시 · 프롬프트 v3", use="Flash-Lite · LOW"),
                 node("ai", "흐름 판정", "전환·질문 답변", use="Flash-Lite · MINIMAL")),
           node("code", "출처 대조", "근거 번호·숫자가", "문서에 있는지만", use="코드"),
           stack(node("stop", "빨간 경고"), node("screen", "사실 정정"), node("wait", "확인 중", "5초 넘으면 미확인")))),
    tags("정해 둔 것", chip("판단은 모두 모델이, 코드는 출처 대조만", "blue", "ai"),
         chip("같은 입력에 같은 답: seed 고정", "blue", "ai"),
         chip("규정 판정에 원본 문서는 넣지 않음", "grey")),
    gap=20),
    notes="JUDGE_ARM=single(D-309), SINGLE_MODEL=gemini-3.5-flash-lite. 검증 모델 2단계(3.8 Flash)는 느려서 뺐다. "
          "원본 문서를 규정 판정에 넣으면 잘못된 HIGH가 늘어서 뺐다(docs_test_1007).")

slide("v3", "사실 확인 프롬프트 v3", "코드가 아니라 프롬프트로 고친 네 가지", col(
    flows(t("남의 말은 확인하지 않는다", 28, GRN, 700),
          (says("진행자", "Someone asks, \"Can I use two coupons?\"", "(누가 쿠폰 두 장 되냐고 묻네요)"),
           ai("진행자 주장이 아님", "확인 안 함"), result("경고 없음", "green")),
          t("앞 줄에 동의하면 진행자 주장이다", 28, RED, 700),
          (says("진행자", "Someone says it ends on the 3rd. / Correct.", "(3일에 끝난대요. / 맞아요.)"),
           ai("동의한 내용을 문서와 비교", "문서는 30일"), result("사실 정정<br><span style='font-size:24px'>30일에 끝남</span>", "yellow")),
          gap=16),
    tags("나머지 두 가지", chip("소리가 비슷한 값은 보류 (Marro Bey ↔ Marrow Bay)", "blue", "ai"),
         chip("문서 값을 먼저 적고 비교 (같은 값을 '다름'으로 내던 실수)", "blue", "ai")),
    gap=22),
    notes="D-312(v2), D-313(v3). Flash-Lite LOW는 생각 토큰이 0이라(512회 중) 규칙 문구와 출력 순서가 결과를 좌우한다. 예시는 지어낸 문장.")

slide("res", "결과 · 5차 세트 · 목소리 A / B", "프롬프트만 바꿔 오경고 6.5~8.3%가 0.9%로 내려왔다", col(
    table(["설정", "탐지", "오경고", "잘못된 HIGH", "경고 p95"],
          [row("규정 MEDIUM · 사실 LOW (프롬프트 v1)", "litemed"),
           row("+ 프롬프트 v2", "factv2"),
           row("+ 프롬프트 v3", "factv3_LOW"),
           row("v3 · 사실 MEDIUM", "factv3_MEDIUM"),
           row("v3 · seed 7 (1회차)", "seed7_r1"),
           row("v3 · seed 7 (2회차)", "seed7_r2")],
          ["40%", "16%", "16%", "14%", "14%"]),
    tags("기준", chip("탐지 95% 이상", "grey"), chip("오경고 1% 미만", "grey"), chip("잘못된 HIGH 0", "grey"),
         chip("경고 p95 5초 이하", "grey")),
    gap=22),
    notes="사실 MEDIUM은 150ml 오경고를 없앴지만 시간 초과가 50건 안팎으로 늘어 p95가 5초에 닿았다. 그래서 LOW.")

slide("seed", "흔들림", "seed를 고정하면 같은 입력에 같은 답, 남은 흔들림은 서버 지연", col(
    table(["같은 설정 2회 실행", "결과가 바뀐 줄 (A / B)", "이유"],
          [["seed 없음", "3줄 / 1줄", "모델이 매번 다르게 답함"],
           ["seed 7", "0줄 / 1줄", "B 1줄은 확인 필요"],
           ["seed 11", "3줄 / 0줄", "2줄은 규정 판정 시간 초과·429, 1줄은 같은 입력에서 바뀜"]],
          ["26%", "26%", "48%"]),
    tags("판단", chip("seed 값(7·11)에 따른 차이는 작다", "green", "check"),
         chip("Flash-Lite는 temperature를 무시해서 seed만 쓴다", "grey"),
         chip("남은 흔들림은 429·시간 초과", "yellow", "warn")),
    gap=24),
    notes="D-314 JUDGE_SEED. 개발 세션 직접 호출: 기본값 5번 중 5개가 다른 답, seed 고정 5번 중 1개 답, temperature 0은 무시됨.")

slide("left", "남은 문제", "늘 틀리는 줄 셋은 원인이 모두 다르다", table(
    ["줄 (예시는 지어냄)", "무슨 일", "원인", "고칠 길"],
    [["\"one fifty-ml tube\"", "STT가 150 ml로 적고, 사실 확인이 '다름'", "STT + LOW가 보류 규칙을 못 지킴", "MEDIUM이면 풀림, 대신 느림"],
     ["\"100억 균\" (문서: 제조 시점 기준)", "단서가 빠졌는데 '일치'", "프롬프트에 단서 규칙 없음", "프롬프트 한 줄 (v4 후보)"],
     ["싱글리시 한 줄 (목소리 A만)", "STT가 한 단어도 못 받음", "STT", "실제 사람 녹음으로 확인"]],
    ["24%", "28%", "24%", "24%"]),
    notes="각각 1번 제품 오경고, 3번 제품 놓침, 2번 제품 놓침(목소리 A). 서버 용량: 429·시간 초과가 회차마다 10~20건.")

slide("cloud", "클라우드 상태", "지금 클라우드는 아직 예전 판정 구조로 돈다", table(
    ["항목", "클라우드 (00004)", "이 로직으로 바꾸려면"],
    [["판정 구조", "검증 모델 2단계 (JUDGE_ARM=verify)", "JUDGE_ARM=single, SINGLE_MODEL=gemini-3.5-flash-lite"],
     ["판정 강도", "규정 LOW · 사실 LOW", "SINGLE_THINKING=MEDIUM, SINGLE_FACTS_THINKING=LOW"],
     ["사실 확인 프롬프트", "v1", "FACT_PROMPT=v3"],
     ["seed", "없음", "JUDGE_SEED=7"],
     ["STT 문장 끊기", "SHORT", "STANDARD (다음 배포에 들어감)"]],
    ["22%", "34%", "44%"]),
    notes="배포 환경 변수만 바꾸면 된다(deploy/cloudrun.sh). 6차 세트 결과를 보고 사용자가 정한다.")

write(str(OUT), "판정 로직 10/7")
