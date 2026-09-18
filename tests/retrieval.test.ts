import { describe, expect, it } from "vitest";
import { Retriever, queryTerms } from "@/rag/retrieve";

const retriever = new Retriever();

describe("queryTerms", () => {
  it("drops stopwords and short fragments", () => {
    expect(queryTerms("What is the capital of Nigeria?")).toEqual([
      "capital",
      "nigeria",
    ]);
  });

  it("keeps P/E as one term, matching how the index stores it", () => {
    expect(queryTerms("What is a P/E ratio?")).toEqual(["p/e", "ratio"]);
  });

  it("splits hyphenated terms so the parts are findable", () => {
    expect(queryTerms("price-to-earnings")).toEqual(["price", "earnings"]);
  });

  it("deduplicates repeated words", () => {
    expect(queryTerms("dividend dividend yield")).toEqual(["dividend", "yield"]);
  });
});

describe("retrieval boundaries", () => {
  const offCorpus = [
    "What were the rainfall levels in Sokoto during the last harvest?",
    "How do I cook jollof rice?",
    "What is the capital of Nigeria?",
    "Who won the election?",
    "What time does the market open on Saturday?",
    "How do I open a bank account?",
  ];

  const inCorpus = [
    "What is a P/E ratio?",
    "What does free float mean?",
    "How is an IPO priced?",
    "What do the three financial statements tell me?",
    "What is a greenshoe option?",
    "What is dividend withholding tax in Nigeria?",
    "why is market cap not the same as the share price",
    "what is book building",
  ];

  it.each(offCorpus)("returns nothing for: %s", (question) => {
    expect(retriever.search(question)).toEqual([]);
  });

  it.each(inCorpus)("finds sources for: %s", (question) => {
    expect(retriever.search(question).length).toBeGreaterThan(0);
  });

  it("returns nothing for a question with no content words", () => {
    expect(retriever.search("what is it?")).toEqual([]);
  });

  it("ranks the explainer that was written to answer the question first", () => {
    const [top] = retriever.search("What does free float mean?");
    expect(top.chunk.provenance.kind).toBe("explainer");
    if (top.chunk.provenance.kind === "explainer") {
      expect(top.chunk.provenance.slug).toBe("free-float");
    }
  });
});
