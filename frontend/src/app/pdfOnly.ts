// D-367/368 (user): every document upload accepts PDF files only.
export const PDF_ACCEPT = ".pdf,application/pdf";

/** The picked files when all are PDFs; otherwise none, and the message naming the others. */
export function pdfOnly(picked: File[]): { files: File[]; error: string | null } {
  const other = picked.filter((f) => !f.name.toLowerCase().endsWith(".pdf"));
  return other.length
    ? { files: [], error: `PDF files only. Not a PDF: ${other.map((f) => f.name).join(", ")}` }
    : { files: picked, error: null };
}
