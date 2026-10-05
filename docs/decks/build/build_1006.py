"""10/6 team update deck (google-slide-deck design). Run: python build_1006.py"""
import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\User.DESKTOP-G5S2APU\.claude\skills\google-slide-deck")
from deck import *  # noqa: E402,F403

HERE = Path(__file__).parent
SP = Path(r"C:\Users\USER~1.DES\AppData\Local\Temp\claude\D--code-test-study-ai-builder-cup-git-ai-builder-cup-uh\7068adcf-dd3b-464c-98e0-a81602ce10db\scratchpad")  # local eval outputs (arms/); not in the repo
OUT = HERE.parent / "team_update_1006.html"
ARMS = SP / "arms"


def img(path, maxh=640):
    b = base64.b64encode(Path(path).read_bytes()).decode()
    return (f'<img src="data:image/png;base64,{b}" alt="" style="display:block; max-width:100%; max-height:{maxh}px; '
            f'border:2px solid {LINE}; border-radius:16px; margin:0 auto">')


def stat(value, label, base, color, bg):
    return (f'<div style="flex:1; background:{bg}; border-radius:24px; padding:40px 36px; display:flex; '
            f'flex-direction:column; gap:14px">'
            f'<p style="font-size:30px; font-weight:500; color:{INK}">{label}</p>'
            f'<p style="font-size:88px; font-weight:700; color:{color}; line-height:1.05">{value}</p>'
            f'<p style="font-size:24px; color:{SUB}">{base}</p></div>')


def ok(text):
    return f"<span style='color:{GRN}'>{text}</span>"


def bad(text):
    return f"<span style='color:{RED}'>{text}</span>"


# ---------- arm results (read from the eval outputs) ----------
def first(path, pat):
    try:
        m = re.search(pat, Path(path).read_text(encoding="utf-8"))
        return m.groups() if m else None
    except FileNotFoundError:
        return None


def arm_row(arm):
    d = ARMS / arm
    if not (d / "comment-flow.md").exists():
        return None
    s4 = first(d / "sealed4.md", r"detection ([\d.]+)%.*?wrong HIGH (\d+).*?false alerts ([\d.]+)%")
    s3 = first(d / "sealed3.md", r"detection ([\d.]+)%.*?false alerts ([\d.]+)%")
    tu = first(d / "tune.md", r"detection ([\d.]+)%.*?false alerts ([\d.]+)%")
    fp = mp = 0
    for v in ("verbal-public", "verbal-holdout", "verbal-hidden2"):
        f = first(d / f"{v}.md", r"False posts: (\d+)")
        m = first(d / f"{v}.md", r"Missed posts: (\d+)")
        fp += int(f[0]) if f else 0
        mp += int(m[0]) if m else 0
    dr = first(d / "drafts-sealed.md", r"bad drafts posted (\d+).*?good drafts blocked (\d+)/(\d+)")
    cf = first(d / "comment-flow.md", r"\*\*(PASS|FAIL)\*\*.*?route ([\d.]+)%")
    calls = 0
    for u in ("sealed4", "sealed3", "tune"):
        try:
            calls += json.loads((d / f"usage-{u}.json").read_text(encoding="utf-8"))["total"]["calls"]
        except (FileNotFoundError, KeyError):
            pass
    return {"s4": s4, "s3": s3, "tu": tu, "fp": fp, "mp": mp, "dr": dr, "cf": cf, "calls": calls}


ARM_NAMES = {
    "A": "A · 지금 그대로",
    "B": "B · 뜻 판단을 AI로",
    "C": "C · B + 키워드 감지 뺌",
    "D": "D · 전부 프롬프트에 (형 제안)",
    "E": "E · 규정을 Vertex AI Search로",
    "F2": "F2 · 파일을 미리 프롬프트에",
    "F1": "F1 · 파일을 AI가 도구로 읽음",
}


def arm_table():
    rows = []
    base_calls = None
    for arm, name in ARM_NAMES.items():
        r = arm_row(arm)
        if not r:
            rows.append([name, f"<span style='color:{SUB}'>측정 전</span>", "", "", "", ""])
            continue
        det = r["s4"][0] + "%" if r["s4"] else "-"
        det = ok(det) if r["s4"] and float(r["s4"][0]) >= 99 else bad(det)
        fa = (r["s4"][2] + "%") if r["s4"] else "-"
        old = f"{r['s3'][0]}% / {r['tu'][0]}%" if r["s3"] and r["tu"] else "-"
        verbal = ok("0 / 0") if r["fp"] == 0 and r["mp"] == 0 else (bad(f"{r['fp']} / {r['mp']}"))
        flow = ok("통과") if r["cf"] and r["cf"][0] == "PASS" else bad(f"경로 {r['cf'][1]}%" if r["cf"] else "-")
        base_calls = base_calls or r["calls"]
        cost = f"{r['calls'] / base_calls:.2f}배" if base_calls else "-"
        rows.append([name, det, fa, old, verbal, flow + f" · 호출 {cost}"])
    return table(["후보", "새 봉인 세트 탐지", "오경고", "이전 세트 탐지 (봉인/조정)", "말로 한 답 게시 (틀림/놓침)",
                  "댓글 흐름 · 판정 호출 수"], rows, [22, 13, 9, 18, 17, 21], 23)


# ---- 1 cover
slide("cover", "", "", f'''<div style="flex:1; display:flex; flex-direction:column; justify-content:center; gap:36px">
{chip("AI Builder Cup 2026 · 팀 공유 · 10/6", "blue")}
<h1 style="font-size:96px; font-weight:500; line-height:1.15">라이브 진행자 어시스턴트</h1>
<p style="font-size:42px; color:{SUB}; line-height:1.45">10/5 공유 이후 바뀐 것: 클라우드 결과, 사용자 결정,<br>화면 개선, 그리고 설계 후보 비교</p></div>''')

# ---- 2 headline numbers
slide("numbers", "클라우드 결과", "새 버전에서 심은 실수를 모두 잡았다", col(
    rowx(stat("18/18", "심은 실수 3초 안 경고", "봉인 방송 3개 · 00007은 14/18 (실측)", GRN, GRNBG),
         stat("-76%", "운영자가 할 일", "22건 / AI 끔 93건 · 00007은 -62% (실측)", GRN, GRNBG),
         stat("2.50초", "사실 경고 화면 표시 p95", "100줄 · 00007은 3.29초 (실측)", BLUE, BLUEBG), gap=28),
    t("Cloud Run 00008 (코드 0d5565a) · 같은 대본 3개를 AI 켬/끔으로 비교 · 잘못된 게시 0, 안전 문장에 빨간 경고 0", 24, SUB),
    gap=28), notes="docs/eval/proof-plan.md '10/5 오후 합성 방송 4차'. p95는 100번 중 95번이 이 시간 안에 끝난다는 뜻.")

# ---- 3 timeout misses
slide("timeout", "남은 문제", "AI가 늦게 답하면 경고가 조용히 사라졌다", col(
    flows(
        t("놓친 경우 (00008 지연 시험 2줄)", 28, RED, 700),
        (says("진행자", "\"It contains 5% panthenol<br>and 4% niacinamide.\"", "(크림에는 나이아신아마이드가 없음)"),
         ai("사실 확인 AI가<br>6초 동안 답 없음", "", "red"), result("경고 없음", "red")),
        divider(),
        t("고친 방법 (D-184)", 28, GRN, 700),
        (says("코드", "1.5초 안에 답이 없으면"), ai("같은 요청을 한 번 더 보냄", "먼저 온 답을 씀"),
         result("경고 유지<br><span style='font-size:24px'>호출 25~30% 증가</span>", "green")), gap=16)),
    notes="다른 1줄은 미백 주장(bleaches out melanin)을 규정 AI가 놓친 것. 미백 규칙 표현을 보강했다(D-185). 클라우드 재측정은 다음 배포 뒤.")

# ---- 4 operator rule
slide("rule", "사용자 결정", "제품 정보에 답이 있으면 게시, 없으면 운영자", col(
    flows(
        t("제품 정보에 답이 있음", 28, GRN, 700),
        (says("시청자", "\"세트 얼마예요?\""), ai("문서에서 S$62 확인"), result("채팅에 바로 게시", "green")),
        divider(),
        t("제품 정보에 답이 없음", 28, "#B06000", 700),
        (says("시청자", "\"말레이시아 배송 돼요?\""), ai("문서에 없음"),
         result("운영자에게<br><span style='font-size:24px'>1인 방송은 개수만 표시</span>", "yellow")), gap=16),
    tags("같이 정한 것", chip("제품이 바뀌면 질문 목록 새로 고침", "grey"), chip("빨간 경고는 정정 전까지 크게 유지", "grey"),
         chip("말레이시아 데모 가격 (RM)", "grey")), gap=28),
    notes="D-177 빨간 경고, D-178 운영자 경로, D-179 RM 가격. 민감한 질문도 답이 있으면 진행자 카드, 없으면 운영자.")

# ---- 5 hub
slide("hub", "화면", "홈 화면을 방송 순서대로 다시 짰다", col(
    img(HERE.parent / "img" / "hub.png", 600),
    tags("모든 화면 공통", chip("왼쪽 위 로고 = 홈으로", "grey"), chip("테마·언어 설정 하나로 통일", "grey"),
         chip("방송 중 나가기는 한 번 확인", "grey")), gap=24),
    notes="D-183 홈 링크, D-180 테마 하나, Hub v2 (ea43bd2~72b4212). 한국어 화면도 같은 배치.")

# ---- 6 host split
slide("split", "화면", "진행자가 패널 크기를 직접 조절한다", col(
    img(HERE.parent / "img" / "host-split.png", 600),
    tags("규칙", chip("패널은 25% 밑으로 안 줄어듦", "grey"), chip("AI PD 문장은 절대 잘리지 않음", "grey"),
         chip("더블클릭이면 원래 크기", "grey")), gap=24),
    notes="D-181 경계선 2개, D-182 문장 잘림 수정. 크기는 브라우저에 저장된다.")

# ---- 7 STT
slide("stt", "음성 인식", "잘못 알아듣는 단어는 두 종류다", col(
    flows(
        t("제품 단어: 제품마다 다름 · 이미 자동", 28, GRN, 700),
        (says("진행자", "\"panthenol\""), ai("제품 문서에서 용어집 자동 생성", "운영자가 확인"), result("음성 인식 힌트로 들어감", "green")),
        divider(),
        t("위험 표현: 언어마다 고정 · 새로 추가 (D-186)", 28, "#B06000", 700),
        (says("진행자", "\"it really whitens your face\""), ai("\"widens\"로 받아 적음", "", "red"),
         result("위험 단어 94개를<br>힌트에 추가해 비교 예정", "yellow")), gap=16),
    t("힌트를 세게 주면 말하지 않은 단어가 들릴 수 있다. 힌트 끔 / 제품 단어만 / 제품+위험 단어 세 가지로 잰 뒤 정한다.", 24, SUB), gap=24),
    notes="위험 단어는 data/lang/en.json의 즉시 감지 키워드를 그대로 쓴다. 기본값은 꺼짐.")

# ---- 8 principle
slide("principle", "설계 원칙", "뜻은 AI가 판단하고, 코드는 실행만 통제한다", f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px 40px">'
      + col(t("AI로 옮길 것 (뜻 판단)", 30, BLUE, 700),
            listing([("정정했는지", "단어 60% 겹침 대신 AI가 판단"), ("말한 숫자 해석", "\"twenty-one\" 파서 대신 AI가 숫자로"),
                     ("구매·감사 댓글", "키워드 대신 댓글 분류 AI가"), ("답변 의미 검사", "영어 어근 비교 대신 검증 AI가")], "ai", BLUE), gap=16)
      + col(t("코드에 남길 것 (실행 통제)", 30, SUB, 700),
            listing([("시간 제한·재시도", "AI가 늦으면 다시 묻기"), ("공개 게시 직전 확인", "가격·숫자가 문서와 같은지, 중복 게시"),
                     ("방송 상태·질문 경로", "제품 전환, 누구에게 보낼지"), ("스팸·개인정보", "AI에 보내기 전 차단")], "rules", SUB), gap=16)
      + "</div>",
      notes="codex·agy·Sonnet 합의 (docs/PLANNING.md 10/5 룰베이스 재검토). 근거: D-117, D-123, D-174의 코드 판단 실패.")

# ---- 9 rules layers
slide("layers", "규정", "규정은 세 층으로 나누고, 제품 카테고리로 고른다", col(
    chain4(step4(1, "shield", BLUE, BLUEBG, "법 규정", "나라 × 카테고리 · 서비스가 제공"),
           step4(2, "rules", BLUE, BLUEBG, "플랫폼 규정", "TikTok Shop 등 · 운영자가 켜고 끔"),
           step4(3, "book", SUB, "#F1F3F4", "브랜드 규정", "운영자가 올림 · AI가 정리 · 방송 전 확인"),
           step4(4, "ai", BLUE, BLUEBG, "판정 AI", "방송 중 제품의 규정만 받음")),
    tags("원칙", chip("브랜드는 더 엄격하게만", "grey"), chip("법이 금지한 말은 허용 못 함", "grey"),
         chip("지금 sg.json에 섞인 BRAND 규칙 5개를 분리", "yellow", "warn")), gap=32),
    notes="Q2: 제품 정보에 카테고리를 넣는다. Q3: 사용자가 법을 쓰지 않게 하는 것이 서비스의 가치.")

# ---- 10 arms
slide("arms", "설계 후보 비교", "후보를 전부 만들어 같은 시험으로 고른다", col(
    arm_table(),
    t("새 봉인 세트 90줄 (GPT 작성, Sonnet 블라인드 정답과 90/90 일치) × 3회 · 합격선: 탐지 99% 이상, 오경고 4.2% 이하, 잘못 게시 0, 놓친 게시 0", 22, SUB),
    gap=20), notes="arms/<후보>/*.md. 판정 호출 수는 진행자 말 판정 세트 3개 합계를 A 대비로 나눈 값.")

# ---- 11 search tuning
slide("search", "Vertex AI Search", "옵션 두 개로 규정 검색이 정확해졌다", col(
    table(["설정", "맞는 규칙 찾음", "보통 속도", "가장 느림"], [
        ["기본값 (결과 3개)", bad("6/9"), "0.36초", "1.10초"],
        ["<b>결과 5~10개 + 관련도 기준 최저</b>", ok("9/9"), "0.19~0.22초", "0.25~0.34초"],
        ["위 설정 + 검색어 확장·오타 교정", "9/9", "0.20초", "0.67초"]], [46, 18, 18, 18], 28),
    t("기본값은 관련도가 낮다고 본 결과를 버려서 \"It cures eczema\" 검색이 0건이었다. 한국 PC에서 10문장 측정 (실측).", 24, SUB),
    gap=24), notes="relevanceThreshold LOWEST, pageSize 8, market 필터, 연결 재사용. 후보 E에 적용.")

# ---- 12 team roles
slide("roles", "역할 분담", "셋이 겹치지 않게 나눈다", col(
    grid3(
        tile("person", BLUE, BLUEBG, "개발 리드", "설계 결정, 개발 AI 지휘, 병합, 배포 승인",
             "예: 후보 비교 결과로 기본 구조 확정"),
        tile("mic", SUB, "#F1F3F4", "진행자 테스트", "직접 방송하며 실수를 섞어 말하고, 경고·시간·사용성을 기록",
             "예: 억양·속도·잡음을 바꿔 녹음"),
        tile("check", SUB, "#F1F3F4", "워크플로·성능 검증", "봉인 세트 작성, 후보 비교·클라우드 시험, 결과 기록",
             "예: 녹음을 재생 시험으로 다시 잼"), h=None),
    tags("규칙", chip("봉인 세트는 검증 담당만 본다", "grey"), chip("진행자 대본과 봉인 세트는 겹치지 않게", "grey"),
         chip("개발 AI 지시는 개발 리드 한 창구로", "grey")), gap=32),
    notes="진행자 테스트에서 이상한 일 → 녹음·메모 → 검증 담당이 재생 사례로 확인 → 개발 리드 → 개발 세션.")

# ---- 13 handoff flow
slide("handoff", "역할 분담", "문제는 녹음에서 숫자로, 숫자에서 수정으로 간다", col(
    flows(
        (says("진행자 테스트", "\"It cures eczema lah\"", "경고가 안 떴다고 메모"), ai("검증 담당이 녹음을<br>재생 시험으로 다시 잼", "3회 반복"),
         result("놓침 확인<br><span style='font-size:24px'>개발 리드에게</span>", "red")),
        (says("개발 리드", "개발 AI에 수정 지시"), ai("같은 녹음·봉인 세트로<br>다시 잼"), result("통과하면 배포", "green")), gap=16)),
    notes="녹음이 쌓이면 실제 목소리 시험 세트가 된다.")

# ---- 14 next
slide("next", "다음", "남은 일", table(["할 일", "상태"], [
    ["설계 후보 D·E·F 비교 마무리", "<span style='color:#B06000'>진행 중</span> · 결과로 기본 구조 확정"],
    ["오늘 고친 코드 클라우드 배포 (D-177~190)", "<span style='color:#B06000'>승인 대기</span>"],
    ["음성 인식 힌트 3가지 비교", "<span style='color:#B06000'>배포 뒤</span>"],
    ["규정 3층 분리 · 제품 카테고리", f"{bad('남음')} · 설계 합의 완료"],
    ["사람 진행자 녹음으로 시험", f"{bad('남음')} · 합성 음성의 한계"]], [50, 50], 28),
    notes="docs/PLANNING.md, docs/eval/proof-plan.md")

write(OUT, "라이브 진행자 어시스턴트 10/6")
print("wrote", OUT)
