"""A made-up product sheet with two sizes and a bundle (issue I-6), for teammates to upload and reproduce:
docs/decks/files/sample_two_sizes.pdf. Run: uv run --no-project --with reportlab python docs/decks/build/make_sample_two_sizes.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).parent.parent / "files" / "sample_two_sizes.pdf"
OUT.parent.mkdir(exist_ok=True)
ss = getSampleStyleSheet()
P = lambda text: Paragraph(text, ss["Normal"])  # noqa: E731
story = [
    Paragraph("SAMPLE LAB Daily Scalp Shampoo: live show sell sheet (fictional product for testing)", ss["Title"]),
    Spacer(1, 8),
    P("Brand: SAMPLE LAB. Product: Daily Scalp Shampoo. Category: shampoo. Market: Singapore, prices in SGD."),
    Spacer(1, 8),
    Paragraph("Sizes and prices", ss["Heading2"]),
    Table([["Size", "Live show price", "Regular price"],
           ["200 mL bottle", "S$15.00", "S$19.00"],
           ["400 mL pump bottle", "S$24.00", "S$30.00"],
           ["Two 400 mL pump bottles (bundle)", "S$44.00", "-"]],
          style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])),
    Spacer(1, 8),
    P("Both sizes have the same formula. The bundle needs two bottles of the same size (400 mL only)."),
    Spacer(1, 8),
    Paragraph("What the host may say", ss["Heading2"]),
    P("- A mild daily shampoo that cleans the scalp without a tight feeling."),
    P("- Contains panthenol and glycerin."),
    P("- In an in-house test with 30 adults over 2 weeks, 24 said their scalp felt less dry after washing."),
    Spacer(1, 8),
    Paragraph("Cautions", ss["Heading2"]),
    P("- For external use only. Avoid contact with eyes; if it gets into the eyes, rinse with water."),
    P("- Stop using it if irritation occurs."),
]
SimpleDocTemplate(str(OUT), pagesize=A4).build(story)
print(OUT)
