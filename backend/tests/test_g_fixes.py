"""D-294: the false-alert fixes G1-G7 (pools 2 and 3 on the frozen e7bc727), on made-up lines across categories (a
supplement, a children's product, a fragrance, a haircare product, a kettle, a nail coating). Each fix must drop its
false alerts and keep every true one."""
from __future__ import annotations


from .test_q_fixes import _validate, _with_law_rules  # noqa: F401

FACT = [  # (fix, category, line, stated, correct, quote, field, false alert today)
    ("G1", "children", "Someone said 'you can share the brush'. Please don't, never share it.",
     "you can share the brush", "Do not share the toothbrush", "Do not share the toothbrush", "usage", True),
    ("G1", "supplement", "A viewer wrote 'take it on an empty stomach'. No, never take it without food.",
     "take it on an empty stomach", "Take after meals, not on an empty stomach",
     "Take after meals, not on an empty stomach", "usage", True),
    ("G1", "haircare", "Someone asks 'can I use it on wet hair?' Don't, never use it on wet hair.",
     "use it on wet hair", "Apply to dry hair only; do not use on wet hair",
     "Apply to dry hair only; do not use on wet hair", "usage", True),
    ("G1", "children", "Someone said 'you can share the brush'. Yes, you can share it.",
     "you can share the brush", "Do not share the toothbrush", "Do not share the toothbrush", "usage", False),
    ("G1", "kettle", "Someone asked 'can I leave it on the stove?' No worries, you can leave it there.",
     "leave it on the stove", "Never place the kettle on a stove", "Never place the kettle on a stove", "usage",
     False),
    ("G1", "fragrance", "Spray it on silk, don't hold back.", "Spray it on silk", "Do not spray on silk or leather",
     "Do not spray on silk or leather", "usage", False),  # no quote: the host's own instruction
    ("G2", "children", "It's 4.5 mL, not 45 mL.", "45 mL", "4.5 mL", "Volume: 4.5 mL", "volume", True),
    ("G2", "supplement", "Each tablet has 500 mg rather than 50 mg.", "50 mg", "500 mg", "Vitamin C 500 mg per tablet",
     "ingredient_amount", True),
    ("G2", "fragrance", "It's S$98 today, not S$89.", "S$89", "S$98.00", "Live broadcast price: S$98.00", "price", True),
    ("G2", "kettle", "It's not 1.7 litres, it's 1.5 litres.", "1.5 litres", "1.7 litres", "Capacity: 1.7 litres",
     "volume", False),
    ("G2", "haircare", "It's 45 mL, not 4.5 mL.", "45 mL", "4.5 mL", "Volume: 4.5 mL", "volume", False),
    ("G3", "fragrance", "An S$44 order qualifies, since it's above S$40.", "S$44", "S$40",
     "Free gift with orders above S$40", "promo", True),
    ("G3", "supplement", "Orders of S$60 get free delivery because the minimum is S$50.", "S$60", "S$50",
     "Free delivery: minimum spend S$50", "promo", True),
    ("G3", "kettle", "Spend S$120, which is over S$100, and the descaler is free.", "S$120", "S$100",
     "Free descaler with orders over S$100", "promo", True),
    ("G3", "haircare", "An S$36 order qualifies since it's above S$40.", "S$36", "S$40",
     "Free gift with orders above S$40", "promo", False),
    ("G3", "children", "An S$44 order doesn't qualify, it's above S$40.", "S$44", "S$40",
     "Free gift with orders above S$40", "promo", False),
    ("G6", "nail coating", "Apply uh too thin colour coats.", "too thin coats", "2 thin coats", "Apply 2 thin coats",
     "usage", True),
    ("G6", "supplement", "Take it for times a day with water.", "for times a day", "4 times a day",
     "Take 4 times a day", "usage", True),
    ("G6", "children", "Brush to minutes, morning and night.", "to minutes", "2 minutes", "Brush for 2 minutes",
     "usage", True),
    ("G6", "nail coating", "Apply a thin coat to nails.", "a thin coat", "2 thin coats", "Apply 2 thin coats",
     "usage", False),
    ("G6", "kettle", "Boil it for two minutes.", "two minutes", "3 minutes", "Boil for 3 minutes", "usage", False),
]


G4 = [  # (category, result, qualifier, line, span, kept with G4)
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "Each tablet has zinc at 2 percent.", "zinc at 2 percent", False),
    ("haircare", "Reduces breakage by 60%", "tested by Brightwell Labs, 20 adults", "The serum is 60 percent argan oil.",
     "60 percent argan oil", False),
    ("children", "Removes 90% of plaque in 4 weeks", "clinical study by Ardent Dental Institute, 40 children",
     "The paste is 4 percent xylitol.", "4 percent xylitol", False),
    ("fragrance", "Lasts 8 hours on skin", "tested by Kestrel Labs", "It lasts 8 hours on skin.",
     "lasts 8 hours on skin", True),
    ("kitchen_appliance", "Boils 1 litre in 3 minutes", "tested by Larkmoor Test Centre", "It boils a litre in 3 minutes.",
     "boils a litre in 3 minutes", True),
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "Absorbed two times faster!", "Absorbed two times faster", True),
    ("skincare", "Water-resistant for 80 minutes", "tested by Kestrel Labs", "It's water-resistant for eighty minutes.",
     "water-resistant for eighty minutes", True),
]
# D-295: headline results said bare (no number, no result or evidence word): D-116 drops them today, because the
# qualifier's words count against the match; with G4 they keep their alert by the result's own words
HEADLINE = [
    ("children", "Tear-free formula", "tested by Ardent Dental Institute", "This wash is tear-free.", "tear-free"),
    ("children", "No tears, gentle cleansing", "tested by Ardent Dental Institute", "Gentle cleansing without tears.",
     "Gentle cleansing without tears"),
    ("haircare", "Frizz-free in humid weather", "independent lab test by Velmora Hair Research Centre, 30 adults",
     "Frizz-free even in humid weather.", "Frizz-free even in humid weather"),
]


def _validate_after(catalog, prev, line, violations, fixes):
    """`_validate` with a previous final (a line split by speech-to-text)."""
    from app.agents import utterance_judge

    real = utterance_judge.build_judge_values

    def with_prev(*a, **k):
        values = real(*a, **k)
        values["last_two_final_transcripts_json"] = [prev]
        return values

    utterance_judge.build_judge_values = with_prev
    try:
        return _validate(catalog, line, violations, fixes)
    finally:
        utterance_judge.build_judge_values = real


G5 = [  # (category, result say, line, names the tester with G5)
    ("nail coating", "Quorvane Coating Test Laboratory: chip-free for 7 days", "Quorvane found it chip-free for 7 days.",
     True),
    ("supplement", "Absorbed 2x faster (Institute of Nutrient Science, 30 adults)",
     "The Institute of Nutrient Science found 2x faster absorption.", True),
    ("haircare", "Reduces breakage by 60% (Velmora Hair Research, 20 adults)", "Velmora's research shows 60% less breakage.",
     True),
    ("children", "Removes 90% of plaque in 4 weeks (in our in-house test, 40 children)",
     "It removes 90% of plaque in 4 weeks.", False),
    ("kettle", "Boils 1 litre in 3 minutes (tested by Larkmoor Test Centre)", "It boils a litre in 3 minutes.", False),
    ("nail coating", "Coating stays chip-free 7 days (tested by Coating Science Labs)",
     "The coating stays chip-free 7 days.", False),  # "coating" is the result's own word, not the tester's name
]


V = "ASEAN-2D-VULNERABLE"
G7 = [  # (category, line, kept with G7)
    ("children", "Let the child brush alone, no adult supervision needed.", False),
    ("children", "Kids can brush on their own.", False),
    ("children", "Safe for babies.", True),
    ("children", "Perfect for kids with eczema.", True),
    ("skincare", "Pregnant women can use it on their own.", True),
    ("supplement", "Seniors can take it alone, no side effects.", True),
]

