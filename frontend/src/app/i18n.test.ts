import { describe, expect, it } from "vitest";

import { translate } from "./i18n";

describe("UI text (D-494: English only)", () => {
  it("fills a template's values and leaves unknown ones as written", () => {
    expect(translate("{n} unanswered questions", { n: 3 })).toBe("3 unanswered questions");
    expect(translate("Shown in {s} s", {})).toBe("Shown in {s} s");
    expect(translate("Not in the table")).toBe("Not in the table");
  });
});
