"""Issues found in the sealed pool 8 measurement (10/11), one slide per issue, each confirmed with the user before it is added.
google-slide-deck design. Examples are made up (the sealed lines stay outside the repo); counts are from docs/ISSUES.md I-6..I-10.
Run: python docs/decks/build/build_issues_1011.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "issues_1011.html"

slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("봉인 세트 8 · 10/11 · 배포 버전 30f4852", "blue")}
<h1 style="font-size:84px; font-weight:500; line-height:1.15">새 제품 6개로 재 보니<br>규정 위반은 다 잡고, 오경보가 많았다</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">탐지 95.8% · 오경보 5.1% · 잘못된 빨강 7개 · 경고 p95 2.7초</p></div>''',
      notes="화장품 4개(ASEAN 화장품 광고 지침), 건강기능식품 2개(싱가포르 HSA 목록), 진행자 문장 504개, TTS 음성 Zira를 Chirp 3로 받아 적은 문장. "
            "대표값은 두 사람 동시 발화, 스트레스 문장, 프롬프터 밖 문장을 뺀 수치. 통과선 4개 중 오경보(1% 미만)와 잘못된 빨강(0)을 넘지 못했다.")

slide("i6", "이슈 1 · 오경보 4개", "크기가 여러 개인 제품도 프롬프터에는 가격이 하나만 들어간다", col(
    rowx(
        fx(box(t("제품 문서 (예시 PDF)", 26, SUB, 700),
            table(["", "방송가", "정가"], [["200 mL", "S$15", "S$19"], ["400 mL", "S$24", "S$30"], ["400 mL ×2", "S$44", ""]],
                  [44, 28, 28], 24), gap=12)),
        fx(box(t("프롬프터 (실제 온보딩 결과)", 26, SUB, 700),
            table(["", "방송가", "정가"], [["크기 없음", "S$15", "S$19"]], [44, 28, 28], 24),
            t("400 mL와 2병 가격은 없음<br>저장 칸이 가격 하나뿐 (ProductInfo)", 24, RED, 500), gap=12)), gap=32),
    flows((says("진행자", "The big 400 mL bottle is 24 dollars live today.", "(큰 병은 오늘 24달러예요. 맞는 가격)"),
           ai("프롬프터에는 S$15뿐", "다른 크기인지 모름"),
           result("주황 경고 1.4초<br><span style='font-size:24px'>\"S$15.00\" 맞는 말인데 틀렸다고 표시</span>", "red"))),
    tags("직접 해 보기", chip("<a href='files/sample_two_sizes.pdf' download style='color:inherit'>예시 PDF 받기</a>", "blue"),
         chip("올리기 → 승인 → 방송 시작", "grey"), chip("위 문장 말하기", "grey"),
         chip("검토 중인 방향: 크기별 가격을 프롬프터에", "yellow", "warn")), gap=22),
    notes="10/11 재현: docs/decks/files/sample_two_sizes.pdf(가상 제품)를 평가용 버킷에 실제 온보딩 경로로 올렸다. 읽기 결과 정가 19.00, 방송가 15.00 하나만 저장, "
          "포인트에도 크기별 가격 없음. 판정은 배포 설정(30f4852)으로 세 문장: 400 mL 24달러(맞음) -> 주황 경고 S$15.00, 1.4초; 200 mL 15달러 -> 경고 없음; "
          "400 mL 2병 44달러 -> 경고 없음(프롬프터에 없어서 확인 불가). 봉인 세트에서는 두 크기와 묶음가가 있는 샴푸, 30·60캡슐과 정기배송이 있는 영양제에서 생겼고, "
          "영양제는 AI가 가격을 비워(값을 못 고르면 비움, 그러면 방송 시작 불가) 사람이 승인 단계에서 정가 하나를 넣었다. 코드: backend/app/api/products.py ProductInfo, backend/app/onboarding/product_show.py. "
          "온보딩은 다른 팀 담당. 사용자 방향(10/11): 크기별 가격을 프롬프터에 넣는 쪽으로 검토.")

write(OUT, "봉인 세트 8 이슈")
print("wrote", OUT)
