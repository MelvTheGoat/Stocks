import { describe, expect, it } from "vitest";
import { explainers, getExplainer, requireExplainer } from "@/lib/basics";
import { checkContent, checkText } from "@/lib/editorial";

describe("the basics library", () => {
  it("loads and validates every explainer", () => {
    expect(explainers.length).toBeGreaterThan(0);
    for (const explainer of explainers) {
      expect(explainer.slug).toMatch(/^[a-z0-9-]+$/);
      expect(explainer.body.length).toBeGreaterThan(0);
    }
  });

  it("covers the concepts a first-time investor is promised", () => {
    const slugs = explainers.map((e) => e.slug);
    for (const required of [
      "the-three-financial-statements",
      "pe-ratio",
      "dividend-yield",
      "market-cap",
      "prospectus",
      "ipo",
      "book-building",
      "greenshoe",
      "free-float",
    ]) {
      expect(slugs).toContain(required);
    }
  });

  it("resolves every see-also link", () => {
    const slugs = new Set(explainers.map((e) => e.slug));
    for (const explainer of explainers) {
      for (const related of explainer.seeAlso) {
        expect(slugs.has(related)).toBe(true);
      }
    }
  });

  it("carries a review date on every explainer", () => {
    for (const explainer of explainers) {
      expect(explainer.lastReviewed).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("looks up by slug and throws on an unknown one", () => {
    expect(getExplainer("pe-ratio")?.title).toBe("Price-to-earnings ratio");
    expect(getExplainer("not-a-real-slug")).toBeUndefined();
    expect(() => requireExplainer("not-a-real-slug")).toThrow();
  });
});

describe("the editorial guard", () => {
  it("catches recommendation language anywhere", () => {
    expect(checkText("t", "This one is a top pick.", "basics")).toHaveLength(1);
    expect(checkText("t", "We recommend holding.", "profile")).toHaveLength(1);
    expect(checkText("t", "The shares will rally on results.", "basics")).toHaveLength(1);
  });

  it("bans valuation adjectives in profiles but allows them when teaching", () => {
    expect(checkText("t", "The shares look cheap at this level.", "profile")).toHaveLength(1);
    expect(checkText("t", "A low P/E does not mean a share is cheap.", "basics")).toHaveLength(0);
  });

  it("reports the field path through nested content", () => {
    const violations = checkContent(
      "profile",
      { sections: [{ tier1: "A genuine bargain at this price." }] },
      "profile",
    );
    expect(violations[0]?.field).toBe("profile.sections[0].tier1");
  });

  it("passes the shipped basics library", () => {
    expect(explainers.flatMap((e) => checkContent(e.slug, e, "basics"))).toEqual([]);
  });
});
