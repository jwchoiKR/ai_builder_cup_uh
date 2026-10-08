"""10/8 deck: overnight tests 10/7-8: STT hint conditions, pool 5 with production hints, fact prompt v4, and the fresh pool 6
(new products, two hosts). Run: python docs/decks/build/build_test_1008.py
Numbers: sealed_sets/results/all_arms_1008.json (docs_arms.py), stt/stt5_*_STD_*.json. Examples are made up."""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "test_1008.html"
RES = Path(r"C:\code_test\study\ai_builder_cup_git\sealed_sets\results")
D = {}
for f in sorted(RES.glob("all_arms_*.json")):
    D.update(json.load(open(f, encoding="utf-8")))


def ab(arm, pa, pb, key, fmt="{:.1f}%"):
    return f"{fmt.format(D[f'{arm}/{pa}'][key])} / {fmt.format(D[f'{arm}/{pb}'][key])}"


def row(label, arm, pa, pb):
    a, b = D[f"{arm}/{pa}"]["ms_p95"], D[f"{arm}/{pb}"]["ms_p95"]
    return [label, ab(arm, pa, pb, "detection"), ab(arm, pa, pb, "false"), ab(arm, pa, pb, "wrong_high", "{}"),
            f"{a / 1000:.1f} / {b / 1000:.1f}초"]


HEAD = ["설정 (목소리 A / B)", "탐지", "오경고", "잘못된 HIGH", "경고 p95"]
W = ["36%", "16%", "16%", "16%", "16%"]

slide("sum", "10/7~8 밤사이 테스트", "처음 보는 6차 세트에서 탐지 90%대, 기준 미달이라 멈췄다", col(
    rowx(fx(big("6차 탐지", "89.6%", "90.3%", RED, "#FCE8E6", "목소리 A", "목소리 B · 기준 95% 이상")),
         fx(big("6차 오경고", "5.6%", "5.6%", RED, "#FCE8E6", "목소리 A", "목소리 B · 기준 1% 미만")),
         fx(big("5차 오경고", "0.9%", "0.0%", GRN, "#E6F4EA", "목소리 A", "목소리 B · 실제 힌트")), gap=24),
    tags("밤사이 돌린 것", chip("STT 힌트 3가지 비교", "grey"), chip("5차: 실제 방송 힌트로 재측정", "grey"),
         chip("사실 프롬프트 v4", "grey"), chip("6차 세트 (새 제품, 진행자 2명)", "grey")),
    tags("결론", chip("STT 힌트는 지금 것(브리프 포함)으로 충분", "green", "check"), chip("v4는 효과 없어 버림", "red", "x"),
         chip("6차에서 새 실패 유형 3가지", "red", "x")),
    gap=26),
    notes="모든 판정 측정: Flash-Lite 한 번 판정, 규정 MEDIUM, 사실 LOW, 프롬프트 v3, seed 7, STT STANDARD, 1회. "
          "노트북은 10/8 00:31 Windows 업데이트로 재시작됐지만 VM 측정은 그 전에 모두 끝났다.")

slide("hint", "STT 힌트", "실제 방송 힌트(브리프 단어 포함)만으로 150ml와 실험실 이름이 풀렸다", col(
    table(["STT 힌트 (5차 음성 240개, 목소리 A / B)", "단어 오류율", "이름 맞음", "\"one fifty-ml\"", "실험실 이름"],
          [["예전 측정 방식 (브리프 단어 없음)", "11.4 / 12.3%", "85 / 81%", "150 ml ✗", "틀림 ✗"],
           ["실제 방송 지금 (브리프 단어 포함)", "10.5 / 10.3%", "83 / 91%", "One 50 mL ✓", "맞음 ✓"],
           ["늘린 힌트 (실험실·용량 등 추가)", "10.2 / 13.1%", "85 / 87%", "1 50 mL ✓", "맞음 ✓"]],
          ["34%", "16%", "14%", "18%", "18%"]),
    tags("판단", chip("늘린 힌트는 추가 단어가 제품당 0~5개, 일부는 잘못 뽑힘 → 쓰지 않음", "grey"),
         chip("지금까지 측정은 실제보다 STT가 불리한 조건이었다", "yellow", "warn")),
    gap=24),
    notes="D-327 STT_HINTS=base/record, phrases_for_release로 실제 방송과 같은 힌트를 만듦. STT는 같은 음성도 회차마다 14~16줄이 달라져 작은 차이는 우연일 수 있다.")

slide("p5", "5차 세트 재측정", "실제 힌트로 재니 5차는 거의 기준선, v4는 효과가 없었다", col(
    table(HEAD, [row("v3 · seed 7 · 예전 힌트", "seed7_r1", "onboarding5_sttzs", "onboarding5_sttds"),
                 row("v3 · seed 7 · 실제 힌트", "p5hbase", "onboarding5_hbase_z", "onboarding5_hbase_d"),
                 row("v4 · seed 7 · 예전 힌트", "factv4", "onboarding5_sttzs", "onboarding5_sttds")], W),
    tags("v4 (조건 빠짐 규칙)", chip("목표 줄(제조 시점 기준 100억)을 여전히 놓침", "red", "x"),
         chip("오경고 1줄 새로 생김", "red", "x"), chip("LOW는 생각을 안 해서 미묘한 규칙을 못 지킴", "grey")),
    gap=24),
    notes="5차 세트는 여러 번 본 세트라 진단용이다. v4 = D-325/326.")

slide("p6", "6차 세트 · 처음 보는 제품 6개", "새 제품과 진행자 2명 줄에서는 기준에 못 미쳤다", col(
    table(HEAD, [row("v3 · seed 7 · 예전 힌트", "pool6", "onboarding6_sttzs", "onboarding6_sttds"),
                 row("v3 · seed 7 · 실제 힌트", "p6hbase", "onboarding6_hbase_z", "onboarding6_hbase_d")], W),
    tags("6차 세트", chip("제품당 48줄: 진행자 1명 36줄 + 진행자 2명 12줄", "grey"),
         chip("6개 언어 문서 · 정답 GPT·Sonnet 286/288 일치", "grey")),
    tags("주의", chip("한 번만 돌리는 세트인데 STT 조건을 맞추느라 두 번 돌림 (로직 같음)", "yellow", "warn")),
    gap=24),
    notes="6차 세트: sealed_sets/onboarding6/README.md. 판정 로직은 5차와 같다(0ebdc1a).")

slide("why", "6차에서 틀린 이유", "새로 드러난 실패 유형은 셋이다", col(
    flows(t("① 두 사람이 동시에 말함 · 놓침 7~10줄", 28, RED, 700),
          (says("A·B", "The small bottle is 150 mL. / The large one is 350 mL.", "(동시에: 작은 병 150 / 큰 병 350)"),
           ai("STT: 앞사람 말만 받아 적음", "", "red"), result("놓침<br><span style='font-size:24px'>뒷사람의 틀린 용량</span>", "red")),
          t("② \"시청자가 ~래요\"를 진행자 주장으로 봄 · 오경고 9~11줄", 28, RED, 700),
          (says("A·B", "A viewer says it has 80 mg. / No, it's 18 mg.", "(시청자가 80mg이래요 / 아니요, 18mg)"),
           ai("사실 확인 LOW: 첫 줄을 진행자 주장으로 봄", "", "red"), result("오경고<br><span style='font-size:24px'>\"아니요\"보다 먼저</span>", "red")),
          gap=14),
    tags("③ 부정문에 규정 HIGH · 잘못된 HIGH 2~3줄", chip("\"~하지 마세요\"를 규정 판정이 식단 대체 위반 HIGH로 봄", "red", "x")),
    gap=20),
    notes="예시는 지어낸 문장. ② 5차의 \"Someone asks\"(질문)와 달리 '전하는 말' 형태라 v3 규칙이 LOW에서 적용되지 않았다. 진행자끼리의 질문 줄도 같은 문제.")

slide("next", "정할 것", "원인마다 고칠 길이 다르다", table(
    ["원인", "고칠 길", "대가"],
    [["① 동시 발화", "진행자별 마이크와 STT를 따로", "개발 규모 큼. 아니면 지원 범위 밖으로 정하고 따로 보고"],
     ["② 전하는 말", "(a) 사실 확인 MEDIUM  (b) 전하는 말의 경고는 다음 줄까지 1~2초 기다림", "(a) 시간 초과 (b) 지연 증가"],
     ["③ 부정문 HIGH", "규정 판정 프롬프트에 부정문 규칙 보강", "프롬프트만, 측정 필요"]],
    ["18%", "46%", "36%"]),
    notes="사용자와 방향을 정한 뒤 개발 세션에 넘긴다(실패 시 멈추고 함께 설계 규칙).")

write(str(OUT), "테스트 10/8")
