import { afterEach, describe, expect, it, vi } from "vitest";

import { getLang, LANG_KEY, setLang, translate } from "./i18n";

afterEach(() => {
  vi.restoreAllMocks();
  setLang("en");
});

describe("i18n (D-109)", () => {
  it("translates labels with variables and falls back to English", () => {
    expect(translate("ko", "{n} unanswered questions", { n: 3 })).toBe("답변 못 한 질문 3개");
    expect(translate("en", "{n} unanswered questions", { n: 3 })).toBe("3 unanswered questions");
    expect(translate("ko", "Not in the table")).toBe("Not in the table");
  });

  it("remembers the language and ignores storage errors", () => {
    setLang("ko");
    expect(window.localStorage.getItem(LANG_KEY)).toBe("ko");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setLang("en");
    expect(getLang()).toBe("en");
  });
});
