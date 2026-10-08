"""D-367 (user): regulation originals are PDF only. The live compliance judge is never given an HTML, DOCX or text
original; such a source is reported as missing ("not a PDF"). Fictional law packs."""
from __future__ import annotations

import json
import logging

from .helpers import text_pdf


def _pack(root, pack: str, job: str, files: dict[str, bytes]) -> None:
    from app.onboarding.files import store

    (root / "lawpacks").mkdir(exist_ok=True)
    (root / "lawpacks" / f"{pack}.json").write_text(json.dumps({"pack_id": pack, "job_id": job}))
    for name, data in files.items():
        store(root, job, name, data)


def test_d367_a_non_pdf_original_is_never_sent_and_is_reported_missing(tmp_path, caplog):
    from app.agents.originals import _load

    _pack(tmp_path, "law_sg_h_v1", "jh", {"code.html": b"<html><body>2.1 No cure claims.</body></html>"})
    _pack(tmp_path, "law_sg_m_v1", "jm", {"rules.pdf": text_pdf("3 No safety promises."), "notes.txt": b"3 notes"})
    with caplog.at_level(logging.WARNING):
        found, missing = _load((("law_sg_h_v1", "", None), ("law_sg_m_v1", "", None)), str(tmp_path))
    assert [(d.name, d.mime) for d in found] == [("rules.pdf", "application/pdf")]  # the PDF of a mixed pack only
    assert missing == ("law_sg_h_v1 (not a PDF: code.html)", "law_sg_m_v1 (not a PDF: notes.txt)")
    assert "not a PDF, not given to the judge" in caplog.text
