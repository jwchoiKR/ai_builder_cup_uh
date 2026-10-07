"""10/6 deck: the architecture after D-305 (meaning judgments by models, code only checks provenance).
Run: python docs/decks/build/build_arch_llm_1006.py  (numbers only; sealed text never shown)"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\jaewoo\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403
sys.path.insert(0, str(Path(__file__).parent))
import anim  # noqa: E402,F401  (slide motion)

OUT = Path(__file__).parent.parent / "old" / "arch_llm_1006.html"
S = 24

slide("sum", "10/6 · 아키텍처 변경", "뜻은 모델이 판단하고, 코드는 대조만 한다", col(
    tags("바뀐 것",
         chip("판정 뒤 코드 삭제 규칙을 끄고, 걸린 문장은 3.8 Flash가 근거를 보고 최종 판정", "blue", "ai"),
         chip("판정 중에는 회색 '확인 중', HIGH는 확인된 뒤에만", "blue", "ai"),
         chip("5초 안에 답이 없으면 지우지 않고 '미확인 (AI 응답 지연)'", "yellow", "warn")),
    tags("그대로인 것",
         chip("코드: 근거 번호·숫자·인용이 문서에 실제로 있는지 대조", "green", "check"),
         chip("코드: 개인정보 거르기, Model Armor", "green", "shield"),
         chip("나머지 코드 규칙 15개는 켜 둔 채 하나씩 끄고 비교 중", "grey")),
    t("근거: STT를 거친 5차 세트에서 코드 검증 오경고 19.4%, 모델 검증 0.9%. STT 안내·20초 문맥 묶음은 오경고 11.1%로 나빠져 되돌림", 24, SUB),
    gap=36), notes="D-300(검증 모델), D-304(규칙별 스위치), D-306(확인 중 표시·5초·미확인), D-308(측정한 설정으로 되돌림, fd62170). D-305 전체 전환은 세 모델 합의로 되돌렸다.")

slide("live", "방송 중 · 진행자 말", "진행자 말 한 문장이 경고가 되기까지", col(
    lanes(stage("1차: 세 모델이 동시에 넓게 잡는다 → 2차: 걸린 문장만 상위 모델이 확정한다"),
          (node("person", "진행자 말", "마이크", use="WebSocket"),
           node("ai", "글자로 바꾸기", "문장마다 바로 판정", use="STT chirp_3"),
           stack(node("ai", "규정 판정", use="Flash-Lite · LOW"), node("ai", "사실 확인", "원본 문서 캐시", use="Flash-Lite · LOW"),
                 node("ai", "흐름 판정", "전환·질문 답변", use="Flash-Lite · MINIMAL")),
           node("ai", "최종 판정", "관련 문장만 보고", "유지·버림·심각도", use="3.8 Flash · LOW"),
           node("code", "출처 대조", "근거 번호·숫자", use="코드"),
           stack(node("stop", "HIGH 경고", "확인된 뒤에만"), node("screen", "배너·사실 정정"), node("wait", "미확인", "5초 안에 답 없음")))),
    tags("화면 표시", chip("1차에서 걸리면 바로 회색 '확인 중'", "grey"), chip("확인되면 경고, 아니면 지움", "green", "check"),
         chip("운영자 화면에 응답 없음 건수와 원인", "yellow", "warn")),
    gap=20),
    notes="fd62170: JUDGE_ARM=verify, VERIFY_EVIDENCE=window, VERIFY_TIMEOUT_MS=5000, 헤지 끔. 문장 합치기(3.5초), 금지어 즉시 표시, 제품 이름 매칭은 아직 켜져 있다. "
          "3.8 Flash 단독 측정(100회): 중간값 2.7초, 95% 8.7초, 504 5건.")

slide("other", "방송 전과 댓글", "온보딩과 댓글도 같은 원칙을 따른다", col(
    lanes(stage("방송 전 · 온보딩"),
          (node("person", "문서 올리기", "PDF·엑셀·사진"),
           node("ai", "제품 정보 읽기", "값마다 근거 문장", use="3.8 Flash · HIGH"),
           node("person", "사람 승인"),
           node("store", "승인본 저장", use="GCS 버킷"),
           node("ai", "브리프", "STT 단어·요점", use="3.8 Flash · MEDIUM")),
          stage("방송 중 · 시청자 댓글"),
          (node("person", "시청자 댓글"),
           node("code", "개인정보 거르기", use="코드 · Model Armor"),
           node("ai", "분류·묶기", "제품·질문·인사", use="Flash-Lite · LOW"),
           node("ai", "답 만들기", use="3.8 Flash · LOW"),
           stack(node("code", "출처 대조", "인용·숫자"), node("ai", "답 검증", use="Flash-Lite")),
           stack(node("screen", "자동 게시"), node("wait", "운영자에게", "자료에 없음")))),
    legend(), gap=20),
    notes="댓글 쪽 코드 규칙(제품 지정, 묶기, 인사, 답변 검사, 거르기)은 지금 켜져 있다. 이전/새 설정 비교 측정 중.")

slide("diff", "무엇이 바뀌었나", "판정 뒤 삭제 규칙은 모델로, 나머지는 비교 후 결정", table(
    ["판단", "이전 (코드)", "지금"],
    [["인용·부정인가", "따옴표, 부정어 목록", "판정 모델이 문맥으로 (\"Someone asks\" 등)"],
     ["시험 단서가 빠졌나", "시험 단어·회사 이름 철자 비교", "최종 판정 모델"],
     ["얼마나 심각한가", "규정마다 정한 등급 그대로", "최종 판정 모델이 정함 (HIGH → MEDIUM 가능)"],
     ["문장이 끝났나", "마침표와 단어 목록으로 합치기", "그대로 (비교 측정 중)"],
     ["어느 제품 이야기인가", "제품 이름 글자 일치", "그대로 (비교 측정 중)"],
     ["제품을 넘겼나", "다음 제품 이름이 들려야 전환", "그대로 (비교 측정 중)"],
     ["정정했나", "단어 60% 겹침", "그대로 (비교 측정 중)"],
     ["댓글 제품·묶기·인사", "별칭, 정규식, 앞 5글자", "그대로 (비교 측정 중)"]],
    [24, 36, 40], S), notes="위 3줄(인용, 시험 단서, 심각도)이 판정 뒤 삭제 규칙이고 R2로 모델에 넘어갔다. 나머지는 D-304 스위치로 하나씩 비교한다.")

slide("num", "측정", "STT를 거쳐도 모델 판정은 버텼다", col(
    table(["5차 세트, 1회, 채점 v3", "탐지", "오경고", "잘못된 HIGH", "가장 약한 제품"],
          [["코드 검증 · 글자 입력", "97.2%", "0.9%", "0", "94.4%"],
           ["코드 검증 · STT 거침", "95.4%", "<b style='color:#D93025'>19.4%</b>", "<b style='color:#D93025'>5</b>", "88.9%"],
           ["모델 검증 · 글자 입력", "98.1%", "0.0%", "0", "94.4%"],
           ["모델 검증 · STT 거침", "96.3%", "<b style='color:#188038'>0.9%</b>", "<b style='color:#188038'>0</b>", "94.4%"]],
          [34, 15, 15, 17, 19], S),
    tags("주의", chip("5차는 고칠 때 참고한 세트라 증명이 아니라 진단", "yellow", "warn"),
         chip("3.8 Flash 단독 100회: 중간값 2.7초, 5초 넘음 20건, 504 5건", "yellow", "warn"),
         chip("STT는 합성 음성, 실제 목소리는 측정 전", "yellow", "warn")),
    gap=32), notes="코드 검증 = b14047f, 모델 검증 = c58712d VERIFY_EVIDENCE=window. 남자 목소리 STT에서 코드 검증 오경고 15.7%.")

ITEMS = [
    ("규칙별 비교", "남은 코드 규칙 15개를 하나씩 끄고 비교"),
    ("새 6차 세트", "처음 보는 제품으로 한 번만 돌려 판정"),
    ("최종 판정 지연", "우선 처리 요금으로 줄어드는지 측정"),
    ("STT 끊는 민감도", "STANDARD: 끊긴 줄 73 → 21개"),
    ("실제 목소리", "팀원 녹음으로 STT 손실을 다시 잰다"),
    ("재시작 대비", "방송 상태를 메모리에서 저장소로"),
]
slide("next", "남은 일", "새 세트로 증명하고, 지연과 저장을 고친다",
      f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:24px 48px">{listing(ITEMS[:3], "play", BLUE)}{listing(ITEMS[3:], "play", BLUE)}</div>',
      notes="온보딩 쪽 코드 규칙 5종은 아직 스위치가 없다. 더 빠른 최종 판정 모델(Flash-Lite, 3.5 Flash)은 STT 글자에서 정확도가 떨어졌다. "
            "여러 제품 방송에서 JUDGE_PRODUCTS=all이면 다른 품목의 규정도 모든 문장에 들어가므로 M1 세트로 확인한다.")

write(str(OUT), "판정 아키텍처")
print(OUT)
