"""10/7 deck: every test with the product documents in the compliance judge (COMPLIANCE_DOCS, D-310), and what is left
of the false alerts. Run: python docs/decks/build/build_docs_test_1007.py
Numbers from sealed_sets/results/docs_arms.json (docs_arms.py, scorer v3 --semantic --restore). Sealed text never shown:
examples are made up."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("SLIDE_DECK_LIB", r"C:\Users\jaewoo\google-slide-deck"))  # the folder that holds deck.py
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "docs_test_1007.html"

slide("sum", "10/7 · 원본 문서 테스트", "원본 문서를 규정 판정에 넣으면 잘못된 HIGH가 늘어서 뺀다", col(
    rowx(fx(big("잘못된 HIGH", "3 · 4건", "0 · 0건", RED, "#FCE8E6", "문서 있음 · 목소리 A·B", "문서 없음 · 기준 0")),
         fx(big("경고 p95 (목소리 B)", "9.2초", "4.4초", YEL, "#FEF7E0", "문서 있음", "문서 없음 · 기준 5초")),
         fx(big("오경고 (목소리 B)", "6.5%", "8.3%", BLUE, "#E8F0FE", "문서 있음", "문서 없음 · 기준 1% 미만")), gap=24),
    tags("결론",
         chip("3가지 설정 모두에서 문서를 넣으면 잘못된 HIGH가 3~7건 늘었다", "red", "x"),
         chip("오경고는 조금 줄었지만 기준(1% 미만)과 거리가 멀다", "yellow", "warn"),
         chip("규정 판정에는 문서를 넣지 않는다 (COMPLIANCE_DOCS 끔)", "green", "check")),
    gap=32),
    notes="5차 세트(제품 6개, 안전 108줄 + 위험 108줄), TTS 두 목소리(A=Zira, B=David)를 우리 STT(chirp_3)로 바꾼 글자로 측정. "
          "채점기 v3(--semantic --restore). 숫자: sealed_sets/results/docs_arms.json.")

slide("setup", "무엇을 시험했나", "같은 세트에서 문서만 켜고 끈 3쌍, 목소리 2개", col(
    table(["쌍", "규정 판정", "사실 확인", "STT 문장 끊기", "코드"],
          [["1", "Flash-Lite LOW", "Flash-Lite LOW", "SHORT (기본)", "193f31c"],
           ["2", "Flash-Lite LOW", "Flash-Lite LOW", "STANDARD", "193f31c"],
           ["3", "Flash-Lite MEDIUM", "Flash-Lite LOW", "STANDARD", "a57cb46"]],
          ["8%", "26%", "22%", "24%", "20%"]),
    tags("문서를 넣는다는 것",
         chip("방송 중인 제품의 원본 문서 전체를 규정 판정의 캐시 앞부분에 넣음", "blue", "ai"),
         chip("규정 판정 입력 4.6천 → 12.5천 토큰 (한 문장당 평균)", "grey")),
    tags("시험 문장 (제품당 36줄 × 6제품, 목소리마다)",
         chip("위험 108줄: 사실 오류 76 · 규정 위반 32", "red", "warn"),
         chip("안전 108줄: 9가지 유형 × 12줄", "green", "check"),
         chip("유형: 바꿔 말하기 · 비슷한 숫자 · 말로 한 숫자 · 부정 함정 · 인용 후 부정 · 단서 빠짐 · 싱글리시 · 문장 나뉨 · STT 잡음", "grey")),
    gap=28),
    notes="vm_lite12.sh(쌍 1·2), vm_litemed.sh(쌍 3). JUDGE_ARM=single, SINGLE_MODEL=gemini-3.5-flash-lite, COMPLIANCE_DOCS=true/false. "
          "한 줄 1회 실행, 동시 2개. 429가 난 칸은 10분 뒤 다시 돌림(최대 3번).")

R = [["1 · LOW · SHORT", "없음", "95.4 / 98.1%", "18.5 / 20.4%", "7 / 6", "1.3초 · 2.4초", "3 / 5"],
     ["", "있음", "98.1 / 98.1%", "16.7 / 13.9%", "10 / 13", "1.5초 · 2.7초", "2 / 11"],
     ["2 · LOW · STANDARD", "없음", "96.3 / 96.3%", "12.0 / 11.1%", "4 / 6", "1.4초 · 2.4초", "14 / 3"],
     ["", "있음", "97.2 / 98.1%", "12.0 / 10.2%", "11 / 13", "1.5초 · 2.6초", "3 / 3"],
     ["3 · MEDIUM · STANDARD", "없음", "95.4 / 98.1%", "6.5 / 8.3%", "0 / 0", "2.1초 · 4.6초", "17 / 8"],
     ["", "있음", "96.3 / 97.2%", "6.5 / 6.5%", "3 / 4", "2.7초 · 9.2초", "34 / 41"]]
slide("res", "결과 (목소리 A / B)", "문서를 넣으면 탐지는 비슷하고, 잘못된 HIGH와 지연이 는다", col(
    table(["설정", "문서", "탐지", "오경고", "잘못된 HIGH", "경고 평균 · p95", "시간 초과"], R,
          ["22%", "8%", "15%", "15%", "13%", "15%", "12%"]),
    tags("기준", chip("탐지 95% 이상", "grey"), chip("오경고 1% 미만", "grey"), chip("잘못된 HIGH 0", "grey"),
         chip("경고 p95 5초 이하", "grey")),
    gap=24),
    notes="경고 평균·p95는 두 목소리 중 큰 값. 시간 초과는 판정 호출 약 780~1,000건 중 우리 쪽 제한 시간을 넘긴 건수. "
          "쌍 3은 문서를 넣으면 규정 판정이 MEDIUM에서 느려져 시간 초과가 2~5배.")

slide("why", "왜 나빠지나", "문서를 본 규정 판정이 사실 오류를 건강 규정 위반으로 올린다", col(
    flows(t("문서 없음", 28, GRN, 700),
          (says("진행자", "Use it three times a day.", "(하루 세 번 쓰세요. 문서는 하루 한 번)"),
           ai("사실 확인: 사용법이 문서와 다름", "규정 판정: 위반 없음"),
           result("사실 정정<br><span style='font-size:24px'>MEDIUM</span>", "yellow")),
          divider(),
          t("문서 있음", 28, RED, 700),
          (says("진행자", "Use it three times a day."),
           ai("규정 판정: 문서와 다른 사용법을 권함", "식단·생활 대체 위반 HIGH", "red"),
           result("빨간 경고 HIGH<br><span style='font-size:24px'>잘못된 HIGH</span>", "red")),
          gap=18),
    tags("문서를 넣은 칸의 잘못된 HIGH",
         chip("사용법·주의 오류에 식단·생활 대체 HIGH", "red", "x"),
         chip("주의 오류에 취약 계층 HIGH", "red", "x"),
         chip("입력이 2.7배라 MEDIUM 판정이 느려짐", "yellow", "warn")),
    gap=24),
    notes="예시는 지어낸 문장. 문서를 넣은 6칸의 잘못된 HIGH 63건 중 대부분이 위험 줄(사실 오류)에 HS-DIET-LIFESTYLE-SUBSTITUTION, "
          "ASEAN-2D-VULNERABLE HIGH가 붙은 경우. 사실 오류는 사실 확인이 MEDIUM 정정으로 이미 잡는다.")

slide("left", "지금 남은 오경고", "남은 오경고 16줄은 인용 질문 9줄, STT 오인식 6줄", col(
    flows(t("인용 후 부정 · 9줄 (사실 확인 LOW)", 28, RED, 700),
          (says("진행자", "Someone asks, \"Can I use two coupons?\"", "(누가 쿠폰 두 장 되냐고 묻네요)"),
           ai("사실 확인: 인용된 질문을<br>진행자 주장으로 봄", "", "red"),
           result("오경고<br><span style='font-size:24px'>다음 줄 \"No\"보다 먼저 뜸</span>", "red")),
          divider(),
          t("STT 오인식 · 6줄 (판정은 받은 글자대로 맞음)", 28, YEL, 700),
          (says("진행자", "one fifty-millilitre tube", "(50ml 한 통)"),
           ai("STT: \"150 ml tube\"<br>실험실 이름도 다르게 들음", "", "yellow"),
           result("오경고<br><span style='font-size:24px'>150ml · 실험실 이름 틀림</span>", "red")),
          gap=18),
    tags("나머지", chip("1줄: 말한 값과 문서 값이 같은데 '다름'으로 냄", "grey")),
    gap=24),
    notes="쌍 3 문서 없음(litemed), 목소리 A 7줄 + B 9줄 = 16줄 / 안전 216줄. 인용 후 부정은 두 줄짜리 시험인데, 첫 줄(인용 질문)만 보고 사실 확인이 경고를 낸다. "
          "규정 판정(MEDIUM)은 인용에서 경고를 내지 않았다. 예시는 지어낸 문장.")

write(str(OUT), "원본 문서 테스트")
