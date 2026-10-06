"""10/6 deck: where hand-written code makes meaning judgments, and the plan to compare each on/off.
Run: python docs/decks/build/build_rule_code_1006.py  (numbers only; sealed text never shown, examples are made up)"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "rule_code_1006.html"
S = 24  # table text

slide("sum", "10/6 · 코드 규칙 점검", "뜻을 판단하는 코드가 STT 앞에서 무너졌다", col(
    rowx(
        big("코드 검증 (R3)", "19.4%", "0.9%", RED, REDBG, "STT를 거친 오경고", "글자 직접 입력 오경고"),
        big("모델 검증 (R2-창)", "0.9%", "0.0%", GRN, GRNBG, "STT를 거친 오경고", "글자 직접 입력 오경고"),
        gap=32),
    t("측정: 5차 세트 216줄, 1회, 채점 v3. STT는 합성 음성(여자 목소리) → chirp_3. 잘못된 HIGH는 R3 5건, R2-창 0건", 24, SUB),
    gap=24),
    notes="R3 = b14047f(코드 게이트 마지막 패치), R2-창 = c58712d JUDGE_ARM=verify VERIFY_EVIDENCE=window. 남자 목소리에서도 R3 오경고 15.7%.")

slide("why", "왜 무너졌나 · 1", "따옴표가 사라지면 코드는 인용을 못 알아본다", flows(
    t("As-is · 글자 직접 입력 (따옴표 있음)", 28, GRN, 700),
    (says("진행자", "Someone asks, 'Is it safe for babies?' No, not under three.", "(누가 \"아기한테 괜찮아요?\"라고 묻는데요. 아니요, 세 살 미만은 안 돼요.)"),
     annotate(ai("코드: 따옴표 안은 인용<br>진행자 주장 아님"), "규칙: 따옴표로 인용 판단", "grey"),
     result("경고 안 함<br><span style='font-size:24px'>맞는 판단</span>", "green")),
    divider(),
    t("To-be · STT 입력 (따옴표 사라짐)", 28, RED, 700),
    (says("진행자", "Someone asks is it safe for babies. No, not under three.", "(STT는 따옴표를 받아 적지 않는다)"),
     annotate(ai("코드: 따옴표 없음<br>진행자 주장으로 판단"), "규칙: 인용 못 알아봄", "red", "x"),
     result("오경고<br><span style='font-size:24px'>안전 보장 HIGH</span>", "red")),
    divider(),
    rowx(chip("모델(R2-창)은 \"Someone asks\"를 보고 인용으로 판단해서 두 경우 모두 경고하지 않음", "green", "check"), align="center"),
    gap=16), notes="예시는 지어낸 문장이다. 5차 STT 측정에서 R3 오경고 중 인용 때문에 생긴 것이 7건이었다.")

slide("why2", "왜 무너졌나 · 2", "브랜드를 잘못 받아 적으면 코드는 시험 주체를 못 찾는다", flows(
    t("As-is · 글자 직접 입력 (이름 정확)", 28, GRN, 700),
    (says("진행자", "Lumi Lab tested it on 20 people.", "(루미랩이 20명에게 시험했어요.)"),
     annotate(ai("코드: 시험 주체 찾음<br>단서 있다고 판단"), "규칙: 철자 비교", "grey"),
     result("경고 안 함<br><span style='font-size:24px'>맞는 판단</span>", "green")),
    divider(),
    t("To-be · STT 입력 (이름이 비슷한 소리로 바뀜)", 28, RED, 700),
    (says("진행자", "Loomy Lap tested it on 20 people.", "(STT가 Lumi Lab을 Loomy Lap으로 받아 적음)"),
     annotate(ai("코드: 시험 주체 못 찾음<br>단서 빠졌다고 판단"), "규칙: 철자 비교", "red", "x"),
     result("오경고<br><span style='font-size:24px'>시험 단서 경고</span>", "red")),
    divider(),
    rowx(chip("모델(R2-창)은 소리가 비슷한 이름을 같은 회사로 보고 경고하지 않음", "green", "check"), align="center"),
    gap=16), notes="예시는 지어낸 이름이다. 5차 STT 측정에서 이 유형이 5건, 잘린 문장이 4건이었다.")

slide("live1", "실시간 판정 · 1", "문장 판정 뒤에 붙은 코드 규칙", table(
    ["규칙", "하는 일", "위치"],
    [["시험 단서 게이트 (G4, D-116, L7, Q1E)", "시험 관련 단어나 기록된 결과와 글자로 안 맞으면 판정 삭제", "agents/utterance_judge.py"],
     ["주장 종류·대상 (CK, G7)", "HIGH인데 대상(아기 등)이 문장에 글자로 없으면 삭제", "agents/utterance_judge.py"],
     ["부정 처리 (Q3)", "부정 단어가 있으면 경고 안 함", "agents/utterance_judge.py"],
     ["인용 후 정정 (Q2, G1, D-298)", "틀린 값 인용 뒤 맞는 값을 말하면 삭제", "agents/fact_checker.py"],
     ["숫자 가드", "정정 값의 숫자가 문서에 없으면 삭제 (대조라서 남길 후보)", "agents/fact_checker.py"]],
    [34, 46, 20], S),
    notes="R2(JUDGE_ARM=verify)는 이 규칙들을 끄고 모델이 최종 판정한다. 숫자 가드는 출처 대조라 R2에도 남아 있다.")

slide("live2", "실시간 판정 · 2", "판정 앞뒤에도 글자로 뜻을 정하는 곳이 있다", table(
    ["규칙", "하는 일", "STT 영향", "위치"],
    [["제품 전환", "다음 제품 이름이 글자 그대로 나와야 전환", "<b style='color:#D93025'>큼</b>", "logic/segments.py · pipelines/utterances.py"],
     ["문장 합치기·보류", "마침표와 영어 단어 목록으로 문장 끝 판단", "<b style='color:#D93025'>큼</b>", "pipelines/utterances.py"],
     ["정정 인정", "단어 60% 겹침, 앞 5글자 일치로 정정 여부 판단", "<b style='color:#D93025'>큼</b>", "logic/corrections.py"],
     ["자사 시험 덧붙임", "짧은 문장이 정규식에 맞으면 시험 단서 경고 해제", "중간", "pipelines/utterances.py"],
     ["진행자가 말로 한 답 게시", "\"I think\" 같은 말이 있으면 게시 보류", "중간", "logic/publish.py"],
     ["금지어 즉시 표시", "단어 목록으로 임시 경고, 4단어 안 부정어 확인", "중간", "logic/reflex.py"],
     ["판정에 보낼 제품", "제품 이름 글자 매칭으로 문서·규정 선택", "<b style='color:#D93025'>큼</b>", "logic/catalog.py · agents/fact_checker.py"]],
    [18, 44, 11, 27], S),
    notes="모두 기본으로 켜져 있다. DESIGN_ARM=B/C로 일부는 이미 모델 쪽으로 넘길 수 있다(arms.meaning_to_llm, no_reflex).")

slide("comm", "댓글", "댓글 쪽은 타자로 친 글이라 STT 영향은 작다", table(
    ["규칙", "하는 일", "위치"],
    [["질문 제품·의도 덮어쓰기", "세트가 단어가 있으면 분류를 덮어씀, 별칭으로 제품 지정", "logic/product_mapping.py · logic/catalog.py"],
     ["답변 초안 코드 검사", "길이·문장 수, 주어 창, 자사 시험 정규식, 금지어(부정이어도 막음)", "logic/verify.py"],
     ["반응·욕설 거르기", "3글자 미만이고 물음표 없으면 반응으로 분류", "logic/prefilter.py"],
     ["질문 묶기·답 재사용", "의도별 열린 묶음에 무조건 합침, 성분 앞 5글자로 답 공유", "logic/grouping.py · pipelines/comments.py"],
     ["샤웃아웃", "정규식으로 인사·호명 판단", "logic/shoutout.py"]],
    [24, 50, 26], S),
    notes="답변 초안 검사 중 근거 문장 존재, 인용 일치, 숫자 대조(규칙 2~4)는 출처 대조라 남긴다.")

slide("onb", "온보딩과 남길 것", "남기는 코드는 대조와 보안뿐이다", col(
    tags("온보딩의 뜻 판단 (실시간 영향 작음, 나중에 비교)",
         chip("법 규정 주제 → 단어 목록 연결", "yellow"), chip("가격 반올림 규칙 정규식", "yellow"),
         chip("시험 결과 연결을 단어 겹침으로 판단", "yellow"), chip("브리프 할인 기준", "yellow"), chip("금지어가 든 프롬프터 요점 삭제", "yellow")),
    tags("남길 것 (대조·형식·보안)",
         chip("근거 문장 번호가 실제로 있는가", "green", "check"), chip("정정 숫자가 문서에 있는가", "green", "check"),
         chip("인용문이 원문에 있는가", "green", "check"), chip("개인정보·Model Armor", "green", "shield"),
         chip("운영자 답변 숫자 확인", "green", "check"), chip("가격 통화 변환", "green", "check")),
    gap=40), notes="B(남길 것)와 C(형식 정리)는 판단이 아니라 대조라서 STT 오류에 흔들리지 않는다.")

slide("plan", "진행 방법", "바로 빼지 않고, 켜고 끈 결과로 정한다", col(
    table(["묶음", "비교에 쓰는 세트", "상태"],
          [["실시간 판정 뒤 규칙 → 모델 최종 판정", "5차 STT(두 목소리) · 5차 글자 · 4차", "측정함: 모델 쪽이 STT에서 우세"],
           ["판정 앞뒤 규칙 (전환, 합치기, 정정, 금지어, 제품 선택)", "5차 STT · 여러 제품 세트(M1)", "규칙별 켜기·끄기 개발 중"],
           ["댓글 규칙", "댓글 세트 (240개)", "규칙별 켜기·끄기 개발 중"],
           ["온보딩 규칙", "온보딩 세트", "나중에"]],
          [38, 34, 28], S),
    tags("판정 기준", chip("끄고도 탐지·오경고·잘못된 HIGH가 나빠지지 않으면 뺀다", "blue"),
         chip("끄면 나빠지는 규칙만 남기고 이유를 적는다", "blue")),
    gap=32), notes="규칙 하나당 STT 세트 비교 비용은 약 2~3천 원(추정). 비슷한 규칙은 묶어서 비교한다.")

write(str(OUT), "코드 규칙 점검")
print(OUT)
