"""Brand and category in the context judge's inputs, as-is vs to-be (D-448b, 10/10). google-slide-deck design.
Source: the dev session's probe (probe448_table.md, raw probe448*_raw.json in its scratchpad): Gemini 3.5 Flash-Lite,
thinking MINIMAL, seed 7, 5 runs per line and arm, made-up two-product shows. Run: python docs/decks/build/build_category_1010.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "google-slide-deck"))
from deck import *  # noqa: E402,F403

OUT = Path(__file__).parent.parent / "category_1010.html"


def ok(x):
    return f"<span style='color:{GRN}'>{x}</span>"


def bad(x):
    return f"<span style='color:{RED}'>{x}</span>"


slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("제품 종류 추가 · As-is / To-be · 10/10", "blue")}
<h1 style="font-size:84px; font-weight:500; line-height:1.15">이름에 종류가 없는 제품도<br>"다음은 앰플" 한마디로 넘어간다</h1>
<p style="font-size:38px; color:{SUB}; line-height:1.45">상품 전환 0/5 → 4/4, 다른 판정은 그대로</p></div>''',
      notes="D-448b. 제품 JSON의 category와 brand를 문맥 판정 AI(프롬프터 체크, 상품 전환, 질문 대기 담당)의 입력에 넣었다.")

slide("what", "무엇을 바꿨나", "판정 AI가 보는 제품 정보에 브랜드와 종류를 넣었다", table(
    ["", "As-is (전)", "To-be (후)"], [
        ["지금 상품", "제품명만<br>Hydra Calm Cream", "제품명 + 브랜드 + 종류<br>Hydra Calm Cream · Lunelle · face cream"],
        ["다음 상품 (런시트)", "제품명만<br>종류 칸은 비어 있음", "제품명 + 종류<br>Deep Glow · serum ampoule"],
        ["프롬프트 문장", "변화 없음", "변화 없음 (전환 규칙이 원래 종류 칸을 읽음)"]],
    [22, 36, 42], 25),
    notes="종류는 다른 팀의 제품 JSON(approved.json)에 새로 생긴 category 값이다. 종류 칸은 예전 온보딩이 지워진 뒤 계속 비어 있었다.")

slide("run2", "효과가 드러난 경우", "이름에 종류 단어가 없을 때 \"the ampoule\"은 종류 정보가 있어야 전환됐다", col(
    table(["진행자 말", "기대", "As-is", "To-be"], [
        ['"Next, let me show you the ampoule."', "다음 상품으로 전환", bad("0/5"), ok("4/4")],
        ['"다음은 앰플 보여드릴게요."', "전환", ok("5/5"), ok("5/5")],
        ['"Okay, next up, the serum."', "전환", ok("5/5"), ok("5/5")],
        ['"Next, let me show you the Deep Glow."', "전환 (이름)", ok("5/5"), ok("5/5")],
        ['"Someone asked about the ampoule, we\'ll get to it soon."', "전환 안 함", ok("5/5"), ok("5/5")],
        ['"This cream works well with an ampoule."', "전환 안 함", ok("5/5"), ok("5/5")],
        ['"Next, let me show you the toner."', "전환 안 함", ok("5/5"), ok("4/4")]],
        [46, 22, 16, 16], 23),
    t("다음 제품 이름은 \"Deep Glow\", 종류는 \"serum ampoule\". 한국어 문장과 serum은 전에도 맞혔다. To-be의 4/4는 5번 중 1번이 시간 초과로 빠진 결과다.", 24, SUB), gap=14),
    notes="As-is가 0/5인 이유(모델 설명): '다음 순서가 아닌 앰플을 말했다'. 한국어 문장과 serum은 As-is도 맞혔다.")

slide("run1", "이미 잘 되던 경우", "이름에 종류 단어가 있으면 전과 후가 같다", table(
    ["묶음", "문장 수", "As-is", "To-be"], [
        ["종류·이름으로 전환", "4", "모두 5/5", "모두 5/5"],
        ["전환하면 안 되는 말", "3", "모두 5/5", "모두 5/5"],
        ['"이거", "이 제품"으로 포인트 체크', "3", "모두 5/5", "모두 5/5"],
        ["기존 상품 전환·질문 대기", "6", "모두 5/5", "모두 5/5 (1번은 429로 빠져 4/4)"]],
    [42, 14, 22, 22], 25),
    notes="다음 제품 이름이 'Deep Glow Serum Ampoule'처럼 종류 단어를 포함하면 As-is도 이미 맞힌다. 새 입력이 기존 판정을 망가뜨리지 않았다는 확인이다.")

slide("cost", "속도와 한계", "16문장 시험은 속도가 같았고, 7문장 시험에서만 느렸다", col(
    table(["측정", "As-is", "To-be"], [
        ["응답 평균 / p95 (16문장)", "1.50초 / 1.84초", "1.47초 / 1.68초"],
        ["응답 평균 / p95 (7문장, 이름에 종류 없음)", "1.56초 / 2.14초", "1.86초 / 3.57초 (시간 초과 2번)"]],
        [44, 28, 28], 25),
    tags("한계", chip("만든 제품 2쌍, 문장당 5번", "grey"), chip("시간 초과 2번은 네트워크로 보이나 다시 확인 필요", "yellow", "warn"),
         chip("Gemini Flash-Lite · MINIMAL · seed 7", "grey")), gap=24),
    notes="두 번째 실행의 시간 초과는 입력 증가(몇 단어)로 설명되지 않아 일시적인 혼잡으로 본다. 배포 후 실제 방송에서 다시 본다.")

write(OUT, "제품 종류 추가 As-is/To-be")
print("wrote", OUT)
