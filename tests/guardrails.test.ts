import { describe, expect, it } from "vitest";
import { classifyQuestion } from "@/rag/guardrails";
import { answerQuestion } from "@/rag/answer";
import { Retriever, wantsDetail } from "@/rag/retrieve";

/**
 * A client that fails loudly if it is ever called. Every test in the refusal
 * and not-in-sources blocks passes this in: the point is not only that the
 * answer is right, but that no model call happened at all.
 */
const forbiddenClient = {
  messages: {
    create: () => {
      throw new Error("the model was called for a question that should not reach it");
    },
  },
} as never;

const retriever = new Retriever();

describe("questions that must never be answered", () => {
  const adviceQuestions = [
    "Should I buy Dangote Refinery shares?",
    "should i invest in NGX stocks",
    "Is it worth buying MTN Nigeria?",
    "What should I buy with 500k?",
    "Can you recommend a stock for me?",
    "Which stock should I pick?",
    "What are the best shares on the NGX?",
    "What do you think of Zenith Bank?",
  ];

  const predictionQuestions = [
    "Will the price go up next year?",
    "will dangote shares rise after the offer",
    "What is the price target for GTCO?",
    "How much will it be worth in 2027?",
    "Will they pay a dividend next year?",
    "What returns can I expect?",
  ];

  const suitabilityQuestions = [
    "Is Dangote Refinery a good investment?",
    "Are NGX banks undervalued right now?",
    "Is Seplat cheap at this price?",
    "Is this a safe investment for my savings?",
  ];

  it.each(adviceQuestions)("refuses advice: %s", (question) => {
    const verdict = classifyQuestion(question);
    expect(verdict.allowed).toBe(false);
    if (!verdict.allowed) expect(verdict.kind).toBe("advice");
  });

  it.each(predictionQuestions)("refuses prediction: %s", (question) => {
    const verdict = classifyQuestion(question);
    expect(verdict.allowed).toBe(false);
    if (!verdict.allowed) expect(verdict.kind).toBe("prediction");
  });

  it.each(suitabilityQuestions)("refuses suitability: %s", (question) => {
    const verdict = classifyQuestion(question);
    expect(verdict.allowed).toBe(false);
    if (!verdict.allowed) expect(verdict.kind).toBe("suitability");
  });

  it("refuses before the model is ever reached", async () => {
    const answer = await answerQuestion("Should I buy Dangote Refinery shares?", {
      retriever,
      client: forbiddenClient,
    });

    expect(answer.kind).toBe("refusal");
    expect(answer.citations).toEqual([]);
  });

  it("redirects to an explainer and to a registered adviser", async () => {
    const answer = await answerQuestion("Should I buy Dangote Refinery shares?", {
      retriever,
      client: forbiddenClient,
    });

    expect(answer.relatedExplainer?.href).toMatch(/^\/basics\//);
    expect(answer.adviserPointer).toContain("Securities and Exchange Commission");
  });

  it("sends a price question to a concept, never to a company", async () => {
    const answer = await answerQuestion("Will the share price go up?", {
      retriever,
      client: forbiddenClient,
    });

    expect(answer.refusalKind).toBe("prediction");
    expect(answer.relatedExplainer?.href).toMatch(/^\/basics\//);
  });

  it("uses the same wording every time it refuses the same way", async () => {
    const [first, second] = await Promise.all([
      answerQuestion("Should I buy MTN?", { retriever, client: forbiddenClient }),
      answerQuestion("Should I buy Zenith Bank?", { retriever, client: forbiddenClient }),
    ]);

    // The redirect target may differ; the refusal itself must not.
    expect(first.text.split("\n\n")[0]).toBe(second.text.split("\n\n")[0]);
  });
});

describe("questions that should get through", () => {
  const allowed = [
    "What is a P/E ratio?",
    "What does free float mean?",
    "How is an IPO priced?",
    "What do the three financial statements tell me?",
    "What is a greenshoe option?",
    "What is dividend withholding tax in Nigeria?",
  ];

  it.each(allowed)("allows: %s", (question) => {
    expect(classifyQuestion(question).allowed).toBe(true);
  });

  it("answers a concept question from the basics library", async () => {
    const answer = await answerQuestion("What is a P/E ratio?", { retriever });

    expect(answer.kind).toBe("answer");
    expect(answer.citations.length).toBeGreaterThan(0);
    expect(answer.citations[0].href).toMatch(/^\/basics\//);
  });
});

describe("questions the corpus does not cover", () => {
  it("says so rather than improvising", async () => {
    const answer = await answerQuestion(
      "What were the rainfall levels in Sokoto during the last harvest?",
      { retriever, client: forbiddenClient },
    );

    expect(answer.kind).toBe("not-in-sources");
    expect(answer.citations).toEqual([]);
  });
});

describe("tier defaulting", () => {
  it("treats an ordinary question as a tier 1 question", () => {
    expect(wantsDetail("What does this company do?")).toBe(false);
    expect(wantsDetail("Is the dividend disclosed?")).toBe(false);
  });

  it("recognises a request for detail", () => {
    expect(wantsDetail("What is the debt maturity profile?")).toBe(true);
    expect(wantsDetail("Give me the margin breakdown")).toBe(true);
    expect(wantsDetail("What were the related-party transactions?")).toBe(true);
  });
});
