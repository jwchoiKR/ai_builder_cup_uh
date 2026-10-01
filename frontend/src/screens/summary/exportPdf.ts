import type { SummaryData } from "./types";

/** The PDF report's title, also the default file name of "Save as PDF". */
export function reportTitle(data: SummaryData): string {
  const date = data.stats.started_at ? new Date(data.stats.started_at).toISOString().slice(0, 10) : "";
  return `${data.stats.title} - broadcast summary${date ? ` ${date}` : ""}`;
}

/** D-097: the summary as a PDF report through the browser's print dialog ("Save as PDF"). The
 * page has a print layout (summary.module.css); the document title becomes the file name. */
export function printSummary(data: SummaryData, win: Window = window): string {
  const title = reportTitle(data);
  const previous = win.document.title;
  win.document.title = title;
  const restore = () => {
    win.document.title = previous;
    win.removeEventListener("afterprint", restore);
  };
  win.addEventListener("afterprint", restore);
  win.print();
  return title;
}
