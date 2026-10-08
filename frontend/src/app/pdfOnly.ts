// D-367/368 (user): every document upload accepts PDF files only.
import { translate, type Translate } from "./i18n";

export const PDF_ACCEPT = ".pdf,application/pdf";

const EN: Translate = (en, vars) => translate("en", en, vars);

/** The picked files when all are PDFs; otherwise none, and the message naming the others. */
export function pdfOnly(picked: File[], t: Translate = EN): { files: File[]; error: string | null } {
  const other = picked.filter((f) => !f.name.toLowerCase().endsWith(".pdf"));
  return other.length
    ? { files: [], error: t("PDF files only. Not a PDF: {names}", { names: other.map((f) => f.name).join(", ") }) }
    : { files: picked, error: null };
}
