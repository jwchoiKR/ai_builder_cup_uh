"""Final deck 10/8: the frozen live logic (STT -> question hold -> three Flash-Lite judges -> provenance check -> screens)
and how we tested it, round by round. Run: python docs/decks/build/build_final_1008.py
Numbers: sealed_sets/results/all_arms_1008_v7.json + headline7.py (pool 7, voice A). Examples are made up; sealed text never shown."""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "final_1008.html"
S24 = "font-size:24px"

slide("sum", "최종 정리 · 10/8", "처음 보는 제품에서 탐지 95.5%, 잘못된 HIGH 0, 경고 p95 4.2초", col(
    rowx(fx(big("탐지", "95.5%", "", GRN, "#E6F4EA", "위반 134줄 중 128줄 · 기준 95% 이상", "")),
         fx(big("오경고", "1.6%", "", YEL, "#FEF7E0", "정상 127줄 중 2줄 · 기준 1% 미만", "")),
         fx(big("경고 p95", "4.2초", "", GRN, "#E6F4EA", "말 끝나고 화면까지 · 기준 5초", "")), gap=24),
    tags("측정 조건", chip("새 제품 6개 (7차 세트)", "grey"), chip("TTS 음성 → 우리 STT → 앱 판정", "grey"),
         chip("현실적인 진행 문장만", "grey"), chip("잘못된 HIGH 0", "green", "check")),
    gap=26),
    notes="7차 세트, 목소리 A, 1회, 최종 설정(v5 + 질문 보류). 비평(Sonnet) 판정 반영: 정정 인정 2줄, 무벌점 추가 경고 3줄, "
          "소리로 두 가지로 들리는 1줄 제외. 오경고 2줄은 STT가 four를 for로 적은 줄. 로직은 10/8 밤 동결, 클라우드 00006에 배포.")

slide("goal", "목표와 기준", "처음 보는 제품에서, 제품마다 기준을 넘는 것이 목표다", col(
    listing([("탐지 95% 이상", "규정 위반과 사실 오류를 놓치지 않는다"),
             ("오경고 1% 미만", "맞는 말에 경고를 띄우지 않는다"),
             ("잘못된 HIGH 0", "가장 센 경고는 틀리면 안 된다"),
             ("경고 p95 5초 이하", "말이 끝나고 화면에 뜰 때까지")], "check", GRN),
    tags("지킨 원칙", chip("제품별 프롬프트·규칙 없음: 제품은 문서로만 들어온다", "grey"),
         chip("의미 판단은 모델, 코드는 출처 대조만", "grey"), chip("시험은 매번 처음 보는 제품 세트로", "grey")),
    gap=24),
    notes="기준은 docs/eval/proof-plan.md. 제품 평균이 아니라 제품마다 넘어야 한다(사용자 10/6).")

slide("flow", "최종 로직", "방송 중 진행자 말이 경고가 되기까지", col(
    lanes(stage("방송 전 (다른 담당)"),
          (node("person", "제품 문서 올리기", "어떤 형식이든"), node("ai", "문서 읽기·승인본", use="3.8 Flash"),
           node("ai", "브리프", "제품명·성분 단어 목록", use="3.8 Flash"), node("store", "STT 단어 힌트", "방송에 전달")),
          stage("방송 중 (우리 범위) · 판정 셋은 모두 Gemini 3.5 Flash-Lite"),
          (node("person", "진행자 말", "브라우저 마이크"), node("ai", "STT", "STANDARD", "단어 힌트", use="chirp_3"),
           node("code", "질문 보류", "질문이면 답과 함께", "최대 2.5초"),
           stack(node("ai", "규정 판정", use="생각 MEDIUM"), node("ai", "사실 확인 v5", use="생각 LOW"),
                 node("ai", "맥락 판정", use="생각 MINIMAL")),
           node("code", "출처 대조", "근거 문장·숫자", "버린 판정은 로그"),
           stack(node("screen", "진행자 화면", "HIGH 경고·정정"), node("wait", "운영자 화면", "확인 중 표시")))),
    gap=16),
    notes="설정: JUDGE_ARM=single, SINGLE_MODEL=gemini-3.5-flash-lite, SINGLE_THINKING=MEDIUM, SINGLE_FACTS_THINKING=LOW, "
          "FACT_PROMPT=v5, JUDGE_SEED=7, STT_ENDPOINTING=STANDARD, QUESTION_HOLD=true. 질문인지는 맥락 판정 모델이 정한다"
          "(expects_resolution). 판정 셋은 동시에 돈다.")

slide("v5", "사실 확인 v5", "먼저 누구의 말인지 정하고, 진행자 주장만 대조한다", flows(
    t("진행자가 주장하면", 28, RED, 700),
    (says("진행자", "This toner is 106 ringgit.", "(이 토너는 106링깃이에요.)"),
     ai("진행자 주장이라<br>문서와 대조", "문서 92링깃 (HOST_ASSERTS)"), result("사실 정정<br><span style='font-size:24px'>92링깃으로</span>", "red")),
    divider(),
    t("남의 말을 전하면", 28, GRN, 700),
    (says("진행자", "A viewer says it's 106. Not true!", "(시청자가 106이래요. 아니에요!)"),
     ai("전하는 말이라<br>대조 안 함", "(REPORTS_OR_ASKS)"), result("경고 없음", "green")),
    gap=18),
    notes="v5(D-331)는 주장마다 말의 종류(HOST_ASSERTS / HOST_ENDORSES / REPORTS_OR_ASKS)를 먼저 적게 한다. Flash-Lite LOW는 "
          "생각 토큰이 0이라 출력 칸의 순서가 판단 순서가 된다. 문서 값(source_value)을 관계(relation)보다 먼저 적는다. 예시는 지어냄.")

slide("hold", "질문 보류", "질문 줄은 답이 올 때까지 기다렸다가 함께 판정한다", flows(
    t("보류 전", 28, RED, 700),
    (says("두 진행자", "B: How much is the 3-pack?<br>A: 138 ringgit.", "(3개 묶음 얼마예요? / 138링깃이요.)"),
     ai("\"138 ringgit\" 한 줄만 판정", "무엇의 가격인지 모름"), result("엉뚱한 값과 비교<br><span style='font-size:24px'>오경고·놓침</span>", "red")),
    divider(),
    t("보류 후", 28, GRN, 700),
    (says("두 진행자", "B: How much is the 3-pack?<br>A: 138 ringgit.", "(3개 묶음 얼마예요? / 138링깃이요.)"),
     ai("질문과 답을<br>한 발화로 판정", "[앞줄] · [이번 줄] 표시"), result("3개 묶음 가격과 대조<br><span style='font-size:24px'>두 사람 대화 96.6%</span>", "green")),
    gap=18),
    notes="D-334/335. 맥락 판정이 줄을 '답을 기다리는 말'로 보면 다음 줄을 2.5초까지 기다린다. STT는 물음표를 빼먹을 수 있어서 "
          "문장부호가 아니라 모델이 정한다(사용자 제안). 기다리는 동안 운영자 화면에만 '맥락 확인 중'을 띄운다. 7차 두 사람 대화 줄 82.8% → 96.6%.")

slide("code", "코드가 하는 일", "코드는 판정하지 않고, 출처를 대조하고 흐름만 관리한다", col(
    chain4(step4(1, "rules", BLUE, "#E8F0FE", "출처 대조", "모델이 든 근거 문장이 실제 문서에 있나"),
           step4(2, "shield", RED, "#FCE8E6", "승인 문구는 근거 아님", "금지 문구를 정답처럼 안내하지 않음"),
           step4(3, "warn", "#B06000", "#FEF7E0", "버린 판정은 로그", "사유와 함께 남김"),
           step4(4, "check", GRN, "#E6F4EA", "HIGH는 하나만", "같은 문장에 경고를 겹치지 않음")),
    tags("이렇게 바꾼 이유", chip("코드 규칙으로 판단하던 때 STT 글자에서 오경고 19.4%", "red", "x"),
         chip("모델 판단으로 바꾼 뒤 오경고 1~3%대", "green", "check")),
    gap=28),
    notes="D-338: 사실 확인이 '승인 문구' 섹션을 근거로 정정하면 버린다(금지 문구를 정답처럼 안내하던 문제). D-342: 진행자 화면에서 "
          "HIGH가 있는 문장은 그 경고만 보인다. 코드가 판정을 버릴 때는 'dropped by code' 로그를 남긴다.")

slide("stt", "STT 안정성", "STT가 멈추거나 늦어도 방송을 놓치지 않게 했다", col(
    chain4(step4(1, "mic", BLUE, "#E8F0FE", "멈춤 감지", "말이 끝났는데 5초 안에 결과 없음"),
           step4(2, "play", GRN, "#E6F4EA", "다시 연결", "못 받은 20초 음성을 다시 보냄"),
           step4(3, "warn", "#B06000", "#FEF7E0", "음성이 늦게 올 때", "재시작 없이<br>'재연결 중' 표시"),
           step4(4, "x", RED, "#FCE8E6", "방송 끝", "마이크와 STT를 닫음")),
    tags("같이 넣은 것", chip("같은 문장을 두 번 판정하지 않음", "grey"), chip("음성 도착·전송·결과 시각을 문장마다 기록", "grey"),
         chip("Google SLA는 서버 오류만 보장해서 멈춤은 직접 감시", "grey")),
    gap=28),
    notes="D-339. 리뷰에서 본 36초 공백은 침묵이 아니라 결과가 늦게 몰려온 경우였다(27.5초 늦은 문장 포함). 원인(음성 전송 vs Google)은 "
          "새 로그로 가린다. STT 이중화(STT_DUAL)는 같은 리전·같은 음성 경로라 함께 멈출 수 있어 만들지 않았다(GPT·Gemini·Sonnet 의견).")

DEC = [
    ["검증 모델(3.8 Flash) 삭제", "p95 8.7초, 504 5%, 비용", "Flash-Lite 한 번 판정, p95 4초대"],
    ["코드 규칙 판단 삭제", "STT 글자에서 오경고 19.4%·잘못된 HIGH 5", "모델 판단 + 출처 대조만"],
    ["규정 판정 MEDIUM", "LOW에서 잘못된 HIGH 4~13", "잘못된 HIGH 0"],
    ["사실 확인 LOW + 프롬프트 v5", "남의 말·질문을 주장으로 봄 (오경고 6.5~8.3%)", "전하는 말 오경고 14~16 → 3~6줄"],
    ["seed 고정", "같은 입력에 회차마다 다른 답", "두 번 돌려 바뀐 줄 3 → 0"],
    ["STT STANDARD + 단어 힌트", "문장 쪼개짐 73줄, 제품명 오인식", "쪼개짐 21줄, 오인식 해소"],
    ["질문 보류", "두 사람 대화 줄 82.8%", "96.6%, 오경고 0"],
]
slide("why", "왜 이렇게 정했나", "모든 결정은 같은 세트에서 켜고 끄며 잰 숫자로 정했다", table(
    ["결정", "이전 문제 (측정)", "바꾼 뒤 (측정)"], DEC, ["28%", "38%", "34%"]),
    notes="각 결정의 측정은 docs/decks/test_log.html, docs_test_1007.html, test_1008.html, week_1008.html. 모든 후보는 켜고 끄는 설정으로 "
          "만들어 같은 세트로 비교했다. 계획은 GPT·Gemini·Sonnet에 먼저 보내 합의와 이견을 확인했다.")

slide("method", "시험 방법", "실제 방송과 같은 길로, 매번 처음 보는 제품으로 잰다", col(
    chain4(step4(1, "book", BLUE, "#E8F0FE", "새 제품 문서", "GPT가 6개씩 지어냄 · 앱은 못 봄"),
           step4(2, "check", GRN, "#E6F4EA", "정답 매기기", "Sonnet이 줄을 섞어 따로 매김"),
           step4(3, "mic", BLUE, "#E8F0FE", "음성으로", "TTS 음성 → 우리 STT"),
           step4(4, "rules", RED, "#FCE8E6", "앱 판정·채점", "배포와 같은 설정, 1회")),
    tags("채점 원칙", chip("현실적인 진행 문장만 합격 판단 (함정 문장은 따로)", "grey"),
         chip("제품 규정 팩 밖의 위반은 정답 아님", "grey"), chip("라벨 바꾸면 전·후 숫자 함께", "grey"),
         chip("본 세트는 진단용, 새 세트는 한 번만", "grey")),
    gap=28),
    notes="정답 일치: GPT 라벨과 Sonnet 블라인드 라벨 286~288/288. 판정 변경은 sealed_sets/LABEL_CHANGES.md에 기록. 시험 세트는 앱 개발 세션이 보지 않는다.")

slide("timeline", "시험 경과", "처음 보는 세트의 탐지가 84%에서 95.5%까지 올라왔다", col(
    timeline([("10/5", "3차 세트<br>84%", RED), ("10/6", "4차 세트<br>91.0%", "#B06000"),
              ("10/7", "6차 세트<br>89.6~90.3%", "#B06000"), ("10/8 낮", "7차 세트<br>94.0%", "#B06000"),
              ("10/8 밤", "7차 + 질문 보류<br>95.5%", GRN)]),
    tags("세트마다 바뀐 것", chip("3·4차: 글자 입력, 코드 규칙 판단", "grey"), chip("5·6차: TTS → STT 경로, 단일 판정", "grey"),
         chip("7차: 현실적 문장, v5, 질문 보류", "grey")),
    gap=40),
    notes="모두 처음 보는 제품 세트의 탐지율. 3·4차는 글자를 바로 넣은 시험, 6차부터는 음성과 STT를 거친다. 5차(본 세트, 98.1%)는 "
          "세트를 이미 본 뒤라 진단용으로만 쓰고 여기에 넣지 않았다. 6차 오경고 5.6%, 7차 오경고 3.1% → 1.6%.")

slide("res", "최종 결과", "여섯 제품 중 셋은 모든 기준을 넘고, 셋은 아직 못 미친다", col(
    table(["제품 (7차, 새 제품)", "탐지", "오경고", "잘못된 HIGH"],
          [["립밤", "82.6% (19/23)", "1/21", "0"], ["토너", "100% (23/23)", "0/19", "0"],
           ["오메가3", "100% (23/23)", "0/22", "0"], ["드라이 샴푸", "100% (23/23)", "1/21", "0"],
           ["어린이 선크림", "95.7% (22/23)", "0/22", "0"], ["콜드브루 원액", "94.7% (18/19)", "0/22", "0"]],
          ["40%", "26%", "17%", "17%"]),
    tags("나눠 보면", chip("진행자 한 명 줄 95.2%", "grey"), chip("두 사람 대화 줄 96.6% (보류 전 82.8%)", "green", "check")),
    gap=22),
    notes="립밤 놓친 4줄: 쪼개진 문장의 용량 1, 근처 숫자 가격 1, 주의 뒤집기에서 사실 확인 시간 초과 1, 두 사람 대화 가격 1. 콜드브루 1줄은 시험 조건(사내 시험) 없이 말한 성분 함량. 기준은 제품마다라서 "
          "모든 기준을 넘은 제품: 토너, 오메가3, 어린이 선크림. 립밤(탐지·오경고), 드라이 샴푸(오경고 1줄), 콜드브루(탐지 1줄)는 미달. 목소리 A 1회 측정. 6차·7차 세트 만들 때는 TTS 목소리 2개, 최종 측정은 1개(예산).")

DROP = [
    ["v6 (답은 질문 대상과 비교)", "효과 없음, 잘못된 HIGH 3", "버림 (질문 보류로 대체)"],
    ["최근 3줄을 사실 확인에 넣기", "짝 문장 시험에서 더 나쁨", "버림"],
    ["남의 말 2.5초 보류", "옛 인용 오경고가 되살아남", "버림 (v5로 대체)"],
    ["v7 (동음이의 숫자 규칙)", "오경고 그대로, 틀린 값 1줄 놓침", "버림"],
    ["규정 판정에 원본 문서 넣기", "잘못된 HIGH 3~7 증가", "버림"],
    ["temperature 0", "Flash-Lite가 무시함", "seed로 대체"],
    ["STT 이중화", "같은 경로라 함께 멈출 수 있음", "만들지 않음"],
]
slide("drop", "버린 것", "숫자가 나쁘면 고치지 않고 버렸다", table(["시도", "결과", "판단"], DROP, ["38%", "38%", "24%"]),
      notes="버리는 기준은 측정 전에 정했다. v7 채택 기준: 오경고 감소, 탐지 유지, 잘못된 HIGH 0, 짝 문장 유지, 틀린 값 대조군 전부 경고.")

slide("left", "남은 한계", "알고 있는 한계와 다음에 할 일", col(table(
    ["한계 (예시는 지어냄)", "무슨 일", "다음"],
    [["STT 비슷한 발음", "\"four point five\"를 \"for 0.5\"로 적어 오경고", "실제 진행자 음성으로 빈도 확인"],
     ["동시 발화", "두 사람이 겹쳐 말하면 한 사람 말이 빠짐", "진행자별 마이크"],
     ["제품별 기준", "립밤 82.6%, 콜드브루 94.7%, 드라이 샴푸 오경고 1줄", "새 세트로 다시 재기"],
     ["측정 범위", "TTS 목소리 1개, 1회", "실제 방송 리허설"]],
    ["24%", "44%", "32%"]),
    tags("로직은 동결", chip("v5 + 질문 보류로 고정, 클라우드에 배포", "green", "check"), chip("이후 변경은 측정과 사용자 승인 뒤에만", "grey")),
    gap=28),
    notes="심사위원이 물을 것: 숫자가 TTS 음성 기준인가, 제품마다 넘는가. 답: 실제 진행자 리허설 숫자를 더하고, 제품별 표를 그대로 보여준다.")

write(str(OUT), "최종 로직과 시험 정리")
