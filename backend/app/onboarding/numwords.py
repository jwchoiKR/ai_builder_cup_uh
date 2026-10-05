"""Numbers written as words, read in code (D-243). Some documents spell amounts out: Korean sino numerals
("이만 구천 원", "백이십 그램", "영 점 오"), English ("twenty-nine thousand"), Malay ("dua puluh sembilan ribu"),
Chinese ("二万九千"), and mixed forms ("2만 9천", "29k", "1.5만"). The onboarding evidence check computes every value a
quote states, so a number the model read is kept only when the quote says it, in digits or in words.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# ---- English and Malay: word sequences ------------------------------------------------------------------------------
_EN_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                      "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_EN_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_EN_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_MS_ONES = {"kosong": 0, "sifar": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7,
            "lapan": 8, "sembilan": 9, "sepuluh": 10, "sebelas": 11, "seratus": 100, "seribu": 1000, "sejuta": 1_000_000}
_MS_SCALES = {"belas": "teen", "puluh": 10, "ratus": 100, "ribu": 1000, "juta": 1_000_000}
_DECIMAL_WORDS = {"point", "perpuluhan", "titik"}


def _word_sequences(text: str) -> list[Decimal]:
    """English and Malay number phrases ("twenty-nine thousand", "dua puluh sembilan ribu", "zero point five")."""
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    out: list[Decimal] = []
    i = 0
    while i < len(tokens):
        total, cur, used, j = 0, 0, False, i
        decimals = ""
        while j < len(tokens):
            w = tokens[j]
            if w in _EN_ONES or (w in _MS_ONES and _MS_ONES[w] < 100):
                cur += _EN_ONES.get(w, _MS_ONES.get(w, 0))
            elif w in _EN_TENS:
                cur += _EN_TENS[w]
            elif w in _MS_ONES:  # seratus, seribu, sejuta
                v = _MS_ONES[w]
                if v >= 1000:
                    total += max(cur, 1) * v if cur else v
                    cur = 0
                else:
                    cur += v
            elif w == "belas" and used:
                cur += 10
            elif w in ("puluh",) and used:
                cur = (cur % 10 or 1) * 10 + (cur - cur % 10)
            elif w in ("ratus", "hundred") and used:
                cur = max(cur, 1) * 100
            elif w in ("ribu", "thousand", "juta", "million") and used:
                scale = 1000 if w in ("ribu", "thousand") else 1_000_000
                total += max(cur, 1) * scale
                cur = 0
            elif w == "and" and used:
                pass
            elif w in _DECIMAL_WORDS and used:
                k = j + 1
                while k < len(tokens) and (tokens[k] in _EN_ONES or (tokens[k] in _MS_ONES and _MS_ONES[tokens[k]] < 10)):
                    decimals += str(_EN_ONES.get(tokens[k], _MS_ONES.get(tokens[k], 0)))
                    k += 1
                j = k
                break
            else:
                break
            used = True
            j += 1
        if used:
            value = Decimal(total + cur) + (Decimal(f"0.{decimals}") if decimals else 0)
            out.append(value)
            i = j
        else:
            i += 1
    return out


# ---- Korean (sino) and Chinese --------------------------------------------------------------------------------------
_CJK_DIGITS = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9,
               "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
               "九": 9}
_CJK_SMALL = {"십": 10, "백": 100, "천": 1000, "十": 10, "百": 100, "千": 1000}
_CJK_LARGE = {"만": 10_000, "억": 100_000_000, "万": 10_000, "萬": 10_000, "亿": 100_000_000, "億": 100_000_000}
_CJK_POINT = {"점", "点", "點"}
_CJK = re.compile(r"[0-9.,영공일이삼사오육칠팔구십백천만억零〇一二两兩三四五六七八九十百千万萬亿億점点點\s]+")


def _cjk_value(span: str) -> Decimal | None:
    """One Korean/Chinese numeral, digits allowed inside ("2만 9천", "1.5만", "이만 구천", "二万九千", "영 점 오")."""
    s = re.sub(r"\s+", "", span).replace(",", "")
    if not s or not any(ch in _CJK_DIGITS or ch in _CJK_SMALL or ch in _CJK_LARGE or ch in _CJK_POINT for ch in s):
        return None
    if len(s) == 1 and s in _CJK_DIGITS:
        return None  # one digit syllable alone is usually a word ("이 제품", "사용"), not a number
    if any(p in s for p in _CJK_POINT):
        head, tail = re.split("|".join(_CJK_POINT), s, maxsplit=1)
        whole = _cjk_value(head) if head else Decimal(0)
        frac = "".join(str(_CJK_DIGITS[ch]) if ch in _CJK_DIGITS else ch for ch in tail if ch in _CJK_DIGITS or ch.isdigit())
        return None if whole is None or not frac else whole + Decimal(f"0.{frac}")
    total, section, num = Decimal(0), Decimal(0), None
    i = 0
    while i < len(s):
        ch = s[i]
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            num = Decimal(m.group())
            i += len(m.group())
            continue
        if ch in _CJK_DIGITS:
            num = Decimal(_CJK_DIGITS[ch])
        elif ch in _CJK_SMALL:
            section += (num if num is not None else 1) * _CJK_SMALL[ch]
            num = None
        elif ch in _CJK_LARGE:
            total += (section + (num or 0) or 1) * _CJK_LARGE[ch]
            section, num = Decimal(0), None
        else:
            return None
        i += 1
    return total + section + (num or 0)


_DIGITS = re.compile(r"\d[\d,]*(?:\.\d+)?\s*[kK]\b|\d[\d,]*(?:\.\d+)?")


def numbers_in_text(text: str, comma_decimal: bool = False) -> set[Decimal]:
    """Every number a text states, as a value: digits ("29,000", "29k"), English and Malay words, Korean and Chinese
    numerals (alone or mixed with digits)."""
    out: set[Decimal] = set()
    for m in _DIGITS.finditer(text):
        raw = m.group().strip()
        k = raw[-1] in "kK"
        raw = raw.rstrip("kK").strip()
        if comma_decimal:
            raw = raw.replace(".", "").replace(",", ".")
        elif "," in raw and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
            continue
        try:
            v = Decimal(raw.replace(",", "") if not comma_decimal else raw)
        except InvalidOperation:
            continue
        out.add(v * 1000 if k else v)
    for m in _CJK.finditer(text):
        v = _cjk_value(m.group())
        if v is not None:
            out.add(v)
    out.update(_word_sequences(text))
    return out


def plain(v: Decimal) -> str:
    s = format(v.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s
