"""Running test log of the live path (pool 5, 10/6 onward), rebuilt after every round.
Run: python docs/decks/build/build_test_log.py
Numbers: sealed_sets/results/all_arms_*.json (docs_arms.py <arms>, scorer v3 --semantic --restore, label patches as of the build).
Only numbers and made-up examples; sealed text never shown."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "test_log.html"
RES = Path(r"C:\code_test\study\ai_builder_cup_git\sealed_sets\results")
D = {}
for f in sorted(RES.glob("all_arms_*.json")):
    D.update(json.load(open(f, encoding="utf-8")))

POOL = {"onboarding5_hbase_z": "STT A*", "onboarding5_hbase_d": "STT B*", "onboarding6_sttzs": "6차 A", "onboarding6_sttds": "6차 B", "onboarding6_hbase_z": "6차 A*", "onboarding6_hbase_d": "6차 B*", "onboarding5": "원문", "onboarding5_sttz": "STT A", "onboarding5_sttd": "STT B",
        "onboarding5_sttzs": "STT A", "onboarding5_sttds": "STT B"}


def cell(arm, pool):
    v = D.get(f"{arm}/{pool}")
    if v is None:
        return None
    p95 = f"{v['ms_p95'] / 1000:.1f}초" if v.get("ms_p95") else "기록 없음"
    return [f"{v['detection']:.1f}%", f"{v['false']:.1f}%", str(v["wrong_high"]), p95]


def rows(spec):
    """spec: [(label, arm, [pools])] -> table rows, one per pool."""
    out = []
    for label, arm, pools in spec:
        for i, p in enumerate(pools):
            c = cell(arm, p)
            if c:
                out.append([label if i == 0 else "", POOL[p]] + c)
    return out


HEAD = ["설정", "입력", "탐지", "오경고", "잘못된 HIGH", "경고 p95"]
W = ["38%", "10%", "12%", "12%", "14%", "14%"]

slide("sum", "테스트 기록 · 10/7 기준", "지금 가장 나은 설정은 Flash-Lite 판정 + 사실 확인 프롬프트 v2", col(
    rowx(fx(big("탐지", "97.2%", "98.1%", GRN, "#E6F4EA", "목소리 A", "목소리 B · 기준 95% 이상")),
         fx(big("오경고", "0.9%", "1.9%", YEL, "#FEF7E0", "목소리 A", "목소리 B · 기준 1% 미만")),
         fx(big("경고 p95", "4.2초", "4.1초", GRN, "#E6F4EA", "목소리 A", "목소리 B · 기준 5초 이하")), gap=24),
    tags("지금까지 지나온 길",
         chip("검증 모델 2단계: 정확하지만 3.8 Flash가 느려서 제외", "red", "x"),
         chip("코드 규칙·STT 안내 프롬프트: STT 글자에서 오경고 증가", "red", "x"),
         chip("Flash-Lite 한 번 판정 + 사실 프롬프트 v2: 기준에 가장 가까움", "green", "check")),
    tags("진행 중", chip("v3 (앞 줄 동의 처리)", "blue", "ai"), chip("seed 고정 (흔들림 줄이기)", "blue", "ai"),
         chip("6차 세트 (새 제품 6개, 진행자 2명)", "blue", "ai")),
    gap=28),
    notes="5차 세트(제품 6개, 안전 108줄 + 위험 108줄), 1회 실행. STT A·B는 TTS 두 목소리를 우리 STT로 바꾼 글자. "
          "채점기 v3(--semantic --restore), 라벨 보정 10/7 T4-14 반영. 숫자: sealed_sets/results/all_arms_*.json")

slide("how", "어떻게 재나", "같은 5차 세트를 글자 그대로, 그리고 음성으로 바꿔 STT를 거쳐 잰다", col(
    lanes(stage("시험 문장이 판정까지 가는 길"),
          (node("store", "5차 세트", "제품 6개 · 216줄", "안전 108 · 위험 108"),
           node("ai", "음성 만들기", "목소리 A·B", use="Windows TTS"),
           node("ai", "글자로 바꾸기", use="STT chirp_3"),
           node("ai", "판정", "규정·사실·흐름", use="Flash-Lite"),
           node("code", "채점", "정답과 비교", use="채점기 v3"))),
    tags("기준 (제품마다)", chip("탐지 95% 이상", "grey"), chip("오경고 1% 미만", "grey"), chip("잘못된 HIGH 0", "grey"),
         chip("경고 p95 5초 이하", "grey")),
    tags("주의", chip("설정마다 1회 실행: 한 줄 차이가 0.9%p", "yellow", "warn"),
         chip("5차 세트는 이미 여러 번 본 세트라 진단용", "yellow", "warn")),
    gap=24),
    notes="STT 설정: 10/6까지 SHORT, 10/7부터 STANDARD(문장 끊김 73 → 21). '원문'은 STT를 거치지 않은 글자.")

slide("s1", "1단계 · 10/6 · 원문", "검증 모델을 뒤에 붙이면 정확하지만 3.8 Flash가 느렸다", col(
    table(HEAD, rows([
        ("검증 모델 3.8 Flash (5초)", "r2", ["onboarding5"]),
        ("검증 모델 3.8 Flash (10초)", "r2t10", ["onboarding5"]),
        ("+ 근거 문장 앞뒤만 보기", "win", ["onboarding5"]),
        ("+ 근거 문장 · 검증 Flash-Lite MEDIUM", "winlite", ["onboarding5"]),
        ("+ 근거 문장 · 중복 호출(헤지)", "winhedge", ["onboarding5"]),
        ("3번 판정 다수결", "vote", ["onboarding5"]),
    ]), W),
    tags("판단", chip("근거 문장만 보는 검증: 오경고 0%", "green", "check"),
         chip("3.8 Flash 단독 측정: 평균 3.6초 · p95 8.7초 · 504 5%", "red", "x"), chip("다수결: 탐지 하락", "red", "x")),
    gap=24),
    notes="커밋 8625f6f, c58712d, 899c7ba. 이때는 경고 표시 시간을 따로 기록하지 않아 p95가 없다. 3.8 Flash 속도는 앱 없이 단독 호출 100회로 잼.")

slide("s2", "2단계 · 10/6 · STT A", "STT 글자로 바꾸자 오경고가 늘었고, STT 안내 프롬프트는 더 나빴다", col(
    table(HEAD, rows([
        ("검증 3.8 Flash · 근거 문장", "sttz_win", ["onboarding5_sttz"]),
        ("검증 Flash-Lite MEDIUM", "sttz_winlite", ["onboarding5_sttz"]),
        ("검증 3.5 Flash LOW", "win35", ["onboarding5_sttz"]),
        ("검증 Flash-Lite HIGH", "sttz_litehigh", ["onboarding5_sttz"]),
        ("+ STT 안내 · 20초 문맥 · 숫자 검사", "sttz_aware", ["onboarding5_sttz"]),
        ("+ STT 안내만", "sttz_awareonly", ["onboarding5_sttz"]),
        ("+ 20초 문맥만", "sttz_ctxonly", ["onboarding5_sttz"]),
        ("+ 숫자 검사(코드)만", "sttz_numonly", ["onboarding5_sttz"]),
    ]), W),
    gap=20),
    notes="STT SHORT 설정. 원인: STT가 따옴표를 지우고 이름을 잘못 듣고 문장을 자른다. 안내 프롬프트 세 가지는 모두 되돌림(D-303).")

slide("s3", "3단계 · 10/6 · 한 번에 판정", "검증 단계를 빼고 한 모델로 판정: 3.8 Flash는 시간 초과로 탐지 60%", col(
    table(HEAD, rows([
        ("Flash-Lite HIGH 한 번", "singleAm", ["onboarding5", "onboarding5_sttz"]),
        ("3.8 Flash LOW 한 번", "singleB", ["onboarding5", "onboarding5_sttz"]),
    ]), W),
    tags("판단", chip("3.8 Flash: 시간 초과 370~496건으로 놓침", "red", "x"),
         chip("Flash-Lite HIGH: 원문은 좋지만 STT에서 오경고 9.3%", "yellow", "warn")),
    gap=24),
    notes="6e5fa19, JUDGE_ARM=single, 헤지 켬. 429도 40건 안팎.")

slide("s4", "4단계 · 10/6~7 · Flash-Lite LOW", "STT를 STANDARD로 바꾸니 오경고가 줄고, 원본 문서는 잘못된 HIGH를 늘렸다", col(
    table(HEAD, rows([
        ("LOW · STT SHORT", "lite_base", ["onboarding5_sttz", "onboarding5_sttd"]),
        ("LOW · STT STANDARD", "lite_std", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("LOW · SHORT · 원본 문서", "lite_docs", ["onboarding5_sttz", "onboarding5_sttd"]),
        ("LOW · STANDARD · 원본 문서", "lite_docs_std", ["onboarding5_sttzs", "onboarding5_sttds"]),
    ]), W),
    gap=20),
    notes="193f31c. 원본 문서 = 규정 판정에 제품 문서 전체(COMPLIANCE_DOCS). 상세: docs/decks/docs_test_1007.html")

slide("s5", "5단계 · 10/7 · 규정 MEDIUM", "규정 판정을 MEDIUM으로 올리자 잘못된 HIGH 0, 남은 건 사실 확인 오경고", col(
    table(HEAD, rows([
        ("규정 MEDIUM · 사실 LOW", "litemed", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("+ 원본 문서", "litemed_docs", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("+ 사실 프롬프트 v2", "factv2", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("+ v2 · 사실 MEDIUM", "factv2m", ["onboarding5_sttzs", "onboarding5_sttds"]),
    ]), W),
    gap=20),
    notes="v2에서 바꾼 것(프롬프트만): 진행자가 주장한 것만 확인, 소리가 비슷한 값은 보류, 문서 값을 먼저 적고 비교. a57cb46(litemed), 65f1e8d(v2, D-312). Flash-Lite LOW는 생각 토큰 0(512회 중). v2 MEDIUM은 사실 확인 시간 초과 18·45건으로 목소리 B 탐지 93.5%.")

slide("s6", "6단계 · 10/7 · v3와 seed", "앞 줄 동의까지 확인하는 v3, 흔들림을 줄이는 seed", col(
    table(HEAD, rows([
        ("+ 사실 프롬프트 v3", "factv3_LOW", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("v3 · 사실 MEDIUM", "factv3_MEDIUM", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("v3 · seed 없음 (2회차)", "seed0_r2", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("v3 · seed 7 (1회차)", "seed7_r1", ["onboarding5_sttzs", "onboarding5_sttds"]),
    ]), W),
    gap=20),
    notes="25596c7(v3, D-313), 0ebdc1a(seed, D-314). seed 7·11 각 2회: 같은 설정 2회 사이 바뀐 줄 seed 없음 3/1, seed 7 0/1, seed 11 3/0(2줄은 시간 초과). 상세: docs/decks/live_logic_1007.html")

slide("s7", "7단계 · 10/7~8 밤", "실제 방송 힌트로 5차는 기준선, 처음 보는 6차는 90% 안팎", col(
    table(HEAD, rows([
        ("v3 · seed 7 · 5차 실제 힌트", "p5hbase", ["onboarding5_hbase_z", "onboarding5_hbase_d"]),
        ("v4 · seed 7 · 5차", "factv4", ["onboarding5_sttzs", "onboarding5_sttds"]),
        ("v3 · seed 7 · 6차 예전 힌트", "pool6", ["onboarding6_sttzs", "onboarding6_sttds"]),
        ("v3 · seed 7 · 6차 실제 힌트", "p6hbase", ["onboarding6_hbase_z", "onboarding6_hbase_d"]),
    ]), W),
    gap=20),
    notes="* = 실제 방송과 같은 STT 힌트(브리프 단어 포함). 6차 실패 원인: 동시 발화, 전하는 말, 부정문 HIGH. 상세: docs/decks/test_1008.html")

slide("old", "그 이전 · 10/5~6", "STT 없이 원문으로 잰 1~4차 세트에서는 탐지가 84~91%였다", table(
    ["세트", "커밋", "탐지", "오경고", "잘못된 HIGH", "비고"],
    [["2차 (Q1~6)", "fbb8aa7 무렵", "83~84%", "", "", "새 제품 기준 첫 측정"],
     ["3차 (R1~6)", "fbb8aa7", "84.6%", "", "", "1회"],
     ["4차 (S1~6)", "2153761", "91.0%", "3.1%", "1", "놓친 사실 115건 중 81건이 코드가 지운 정답"],
     ["5차 (T1~6)", "bc9c186", "92.6%", "", "", "채점기 v3 기준, 이후 진단용"]],
    ["16%", "16%", "12%", "12%", "14%", "30%"]),
    notes="숫자는 CLAUDE.md 인수인계 기록과 docs/eval/proof-plan.md. 빈칸은 그때 기록하지 않음.")

write(str(OUT), "테스트 기록")
