"""Week deck 10/6-10/8: the live judging logic we use now, As-is vs To-be, why each decision, and this week's tests.
Run: python docs/decks/build/build_week_1008.py   (numbers: sealed_sets/results/*.json; examples made up; sealed text never shown)"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("SLIDE_DECK_LIB", r"C:\Users\jaewoo\google-slide-deck"))  # the folder that holds deck.py
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "week_1008.html"
V6 = [["7차 (같은 세트 2회차) · v6", "94.0%", "3.1%", "3", "4.3초"],  # v6 + COMPLIANCE_ENDORSE: no gain, dropped
      ["7차 · v5 + 질문 보류 (최종)", "95.5%", "1.6%", "0", "4.2초"],
      ["7차 · v7 (동음이의 규칙)", "95.5%", "1.6%", "0", "4.0초"]]  # v7 rejected by the pre-set rule

slide("sum", "이번 주 정리 · 10/6~8", "판정을 Flash-Lite 한 번으로 바꾸고, 질문 보류로 두 사람 대화를 풀었다", col(
    rowx(fx(big("처음 보는 7차 세트 탐지", "95.5%", "", GRN, "#E6F4EA", "현실적 문장 · 규정 팩 안 · 기준 95%", "")),
         fx(big("7차 오경고", "1.6%", "", YEL, "#FEF7E0", "127줄 중 2줄 (STT 동음이의) · 기준 1% 미만", "")),
         fx(big("경고 p95", "4.2초", "", GRN, "#E6F4EA", "기준 5초 이하 · 잘못된 HIGH 0", "")), gap=24),
    tags("이번 주에 정한 것", chip("검증 모델 2단계 → Flash-Lite 한 번 판정", "blue", "ai"),
         chip("코드 규칙 판단 → 모델 판단, 코드는 출처 대조만", "blue", "ai"),
         chip("사실 확인 프롬프트 v1 → v5 (말의 종류 먼저)", "blue", "ai"), chip("seed 고정 · STT STANDARD", "blue", "ai"), chip("질문 보류: 질문과 답을 한 번에 판정", "blue", "ai")),
    tags("남은 한계", chip("오경고 1.6%: STT가 four를 for로 적는 2줄", "yellow", "warn"), chip("v6·v7은 기준 미달로 버림, v5 + 질문 보류로 동결", "grey")),
    gap=26),
    notes="7차: 새 제품 6개, 목소리 A, 1회, 최종 설정(v5 + QUESTION_HOLD). 비평 판정 반영: 정정 인정 2줄, 무벌점 추가 경고 3줄, 소리로 두 가지로 들리는 1줄 제외. 두 사람 대화 줄 82.8% → 96.6%. 로직은 10/8 밤 동결.")

slide("asis", "As-is → To-be", "방송 중 판정 구조가 이렇게 바뀌었다", col(
    lanes(stage("As-is (10/6 오전)"),
          (node("person", "진행자 말"), node("ai", "STT", "문장 끊기 SHORT", use="chirp_3"),
           stack(node("ai", "규정 판정", use="Flash-Lite · LOW"), node("ai", "사실 확인", use="Flash-Lite · LOW")),
           node("code", "코드 규칙", "인용·부정어·숫자", "판정을 지움"),
           node("ai", "검증 모델", use="3.8 Flash"), node("stop", "경고")),
          stage("To-be (지금)"),
          (node("person", "진행자 말"), node("ai", "STT", "STANDARD · 단어 힌트", use="chirp_3"),
           node("code", "질문 보류", "질문이면 답과 함께", "최대 2.5초"),
           stack(node("ai", "규정 판정", use="Flash-Lite · MEDIUM"), node("ai", "사실 확인", "말의 종류 먼저 (v5)", use="Flash-Lite · LOW")),
           node("code", "출처 대조만", "근거 번호·숫자"), node("stop", "경고", "seed 고정"))),
    gap=16),
    notes="As-is 10/6: R3 코드 게이트 + R2 검증(3.8 Flash). To-be: JUDGE_ARM=single, FACT_PROMPT=v5, QUESTION_HOLD=true (질문인지는 맥락 판정 모델이 정함), JUDGE_SEED=7, STT_ENDPOINTING=STANDARD, 브리프 단어 목록 STT 힌트.")

DEC = [
    ["코드 규칙 판단 삭제", "STT 글자에서 오경고 19.4%·잘못된 HIGH 5", "모델 판단으로 바꿔 오경고 감소"],
    ["검증 모델(3.8 Flash) 삭제", "p95 8.7초, 504 5%, 비용", "Flash-Lite 한 번 판정, p95 4초대"],
    ["규정 판정 MEDIUM", "LOW에서 잘못된 HIGH 4~13", "MEDIUM에서 잘못된 HIGH 0"],
    ["규정 판정에 원본 문서 안 넣음", "넣으면 잘못된 HIGH 3~7건 증가", "문서는 사실 확인에만"],
    ["사실 확인은 LOW 유지", "MEDIUM은 시간 초과 50건 안팎", "LOW + 프롬프트로 보완"],
    ["프롬프트 v2→v3→v5", "남의 말·질문을 주장으로 봄 (오경고 6.5~8.3%)", "5차 오경고 0~0.9%, 전하는 말 부정 오경고 14~16 → 3~6줄"],
    ["seed 고정", "같은 입력에 회차마다 다른 답", "같은 설정 2회 사이 바뀐 줄 3 → 0"],
    ["STT STANDARD + 브리프 힌트", "문장 쪼개짐 73줄, '150ml'·실험실 이름 오인식", "쪼개짐 21줄, 두 오인식 해소"],
]
slide("why", "왜 이렇게 정했나", "모든 결정은 측정 숫자로 정했다", table(
    ["결정", "As-is의 문제 (측정)", "To-be 결과 (측정)"], DEC, ["26%", "37%", "37%"]),
    notes="숫자: docs/decks/test_log.html, docs_test_1007.html, test_1008.html. 5차 세트 기준(진단용).")

slide("drop", "버린 것", "시도했지만 숫자가 나빠서 버린 것도 기록한다", table(
    ["시도", "결과", "판단"],
    [["STT 안내 프롬프트·20초 문맥·숫자 코드 검사", "오경고 증가", "버림"],
     ["3번 판정 다수결", "탐지 하락", "버림"],
     ["temperature 0", "Flash-Lite가 무시함", "seed로 대체"],
     ["남의 말 2.5초 보류", "옛 인용 오경고가 되살아남", "버림 (v5로 대체)"],
     ["부정문 규칙", "걸리는 줄 없음", "끔"],
     ["v4 (조건 빠짐 규칙)", "목표 줄 못 잡고 오경고 1줄 추가", "버림"],
     ["STT 힌트 늘리기", "효과 없음, 잘못 뽑힌 단어", "지금 힌트 유지"]],
    ["40%", "38%", "22%"]),
    notes="모든 시도는 켜고 끄는 설정으로 만들어 같은 세트로 비교했다.")

slide("drop2", "버린 것 (10/8)", "두 사람 대화와 STT 숫자에 대한 시도", table(
    ["시도", "결과", "판단"],
    [["v6 (답은 질문 대상과 비교)", "효과 없음, 잘못된 HIGH 3", "버림 (질문 보류로 대체)"],
     ["최근 3줄을 사실 확인에 넣기", "짝 문장에서 더 나쁨", "버림"],
     ["v7 (동음이의 숫자 규칙)", "오경고 그대로, 대조군 1줄 놓침", "버림"]],
    ["40%", "38%", "22%"]),
    notes="모든 시도는 켜고 끄는 설정으로 만들어 같은 세트로 비교했다.")

slide("tests", "시험 방법도 바꿨다", "현실적인 문장, 규정 팩 안의 위반만 정답으로 센다", col(
    tags("바꾼 원칙", chip("함정 문장(이중 부정 등)은 따로 보고, 합격 판단에서 제외", "grey"),
         chip("제품에 붙은 규정 팩 밖의 위반은 정답이 아님", "grey"),
         chip("동시 발화(마이크 하나)는 따로 보고", "grey"), chip("라벨 변경은 판정 전·후 숫자를 함께", "grey")),
    tags("이번 주 세트", chip("6차: 새 제품 6개, 진행자 2명 포함", "blue", "ai"), chip("7차: 새 제품 6개, 현실적 문장만", "blue", "ai"),
         chip("시험 문장 짝 168줄: 전하는 말·동의·부정·확인 질문", "blue", "ai")),
    tags("정답 확인", chip("작성자가 쓰고 독립 검토자가 줄을 섞어 따로 매김: 286~288/288 일치", "green", "check")),
    gap=26),
    notes="원칙은 LABEL_CHANGES.md에 기록. 규정 팩 밖 라벨: 5차 6줄, 6차 3줄, 7차 4줄(기타 카테고리).")

RES = [
    ["5차 (본 세트) · v5", "98.1%", "0.0%", "0", "3.7초"],
    ["6차 (새 제품) · v3", "89.4~90.8%", "5.0~5.7%", "0", "4.0~4.2초"],
    ["7차 (새 제품) · v5", "94% (판정 전 92.5%)", "3.1%", "0 (판정 전 2)", "4.5초"],
]
if V6:
    RES += V6
slide("res", "결과", "처음 보는 세트에서 탐지·HIGH·지연은 통과, 오경고는 1.6%", col(
    table(["세트 · 프롬프트", "탐지", "오경고", "잘못된 HIGH", "경고 p95"], RES, ["34%", "22%", "16%", "14%", "14%"]),
    tags("기준", chip("탐지 95% 이상", "grey"), chip("오경고 1% 미만", "grey"), chip("잘못된 HIGH 0", "grey"), chip("p95 5초 이하", "grey")),
    gap=24),
    notes="7차: 현실적 문장, 규정 팩 안, 동시 발화 제외. 5차·6차는 규정 팩 밖 줄을 빼기 전 값(6차는 현실적 문장 기준). 5차·7차는 목소리 A, 6차는 A/B 범위.")

slide("left", "남은 문제", "질문과 답은 보류로 풀었고, STT 잡음이 남았다", table(
    ["유형 (예시는 지어냄)", "무슨 일", "대응"],
    [["질문과 답", "\"3개 묶음 얼마예요?\" / \"138링깃\" → 다른 가격과 비교", "풀림: 질문 보류 (두 사람 대화 96.6%)"],
     ["부정하며 새 값", "\"104래요\" / \"아니요, 106이에요\" → 106 확인 안 함", "풀림: 질문 보류"],
     ["동의한 규정 위반", "\"아토피에 좋대요\" / \"네 맞아요\" → 놓침", "풀림: 질문 보류"],
     ["STT 잡음", "\"four point five\" → \"for 0.5\"", "남은 한계 (v7 규칙은 효과 없어 버림)"],
     ["동시 발화", "마이크 하나에서 뒷사람 말이 사라짐", "진행자별 마이크로 확장 가능"]],
    ["22%", "48%", "30%"]),
    notes="v6(D-333) + 규정 동의 판정: 7차 탐지·오경고 그대로(94.0%, 3.1%), 질문·답 2줄은 풀렸지만 다른 2줄을 새로 놓치고 주의 뒤집기 줄에 규정 HIGH 3건이 새로 생김. 시험 문장 짝에서 확인 질문이 22/24(91.7%)로 중단 기준 미달. 그래서 v6은 버리고, 질문 보류(D-334/335)로 풀었다. v7(D-345)은 미리 정한 채택 기준(오경고 감소, 대조군 전부 경고)에 못 미쳐 버렸다.")

write(str(OUT), "이번 주 정리")
