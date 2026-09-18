/**
 * The boundary.
 *
 * This product explains concepts, walks through disclosed figures and surfaces
 * stated risks. It does not say whether to buy, whether something is a good
 * investment, or where a price is going. Those questions are not answered
 * badly or hedged; they are not answered at all, and the reader is sent to the
 * explainer that covers the idea behind their question and to a registered
 * adviser.
 *
 * This runs before retrieval. A question that trips a rule here never reaches
 * the corpus, so no amount of suggestive source text can talk the answer layer
 * into an opinion.
 */

export type RefusalKind = "advice" | "prediction" | "suitability";

export type GuardrailVerdict =
  | { allowed: true }
  | {
      allowed: false;
      kind: RefusalKind;
      /** The phrase that tripped the rule, for logging and for tests. */
      trigger: string;
      /**
       * Topic hint used to choose which explainer to redirect to. Falls back to
       * retrieval against the question when absent.
       */
      topicHint?: string;
    };

type Rule = {
  kind: RefusalKind;
  pattern: RegExp;
  topicHint?: string;
};

/**
 * Ordered most specific first. The first match wins, so a question that is
 * both a prediction and a request for advice is reported as whichever framing
 * the reader actually used.
 */
const RULES: Rule[] = [
  // Direct requests for a decision.
  {
    kind: "advice",
    pattern: /\bshould i (buy|sell|invest|put money|hold|get in|enter)\b/i,
  },
  { kind: "advice", pattern: /\b(is|are) it (worth|a good idea) (buying|investing|it)\b/i },
  { kind: "advice", pattern: /\bworth (buying|investing in|putting money)\b/i },
  { kind: "advice", pattern: /\bwhat should i (buy|invest|do with)\b/i },
  { kind: "advice", pattern: /\b(recommend|advise) (me|a|any|which|what)\b/i },
  { kind: "advice", pattern: /\bwhich (stock|share|company|one)s? should\b/i },
  { kind: "advice", pattern: /\b(best|top) (stock|share|company|companies|pick)s?\b/i },
  { kind: "advice", pattern: /\bwhat do you think (of|about)\b/i },

  // Requests for a verdict on quality or value.
  {
    kind: "suitability",
    pattern: /\bis .{1,40}\ba (good|bad|safe|solid|sound) (investment|buy|stock|share)\b/i,
  },
  {
    kind: "suitability",
    pattern: /\b(is|are) .{1,40}\b(under|over)-?valued\b/i,
    topicHint: "price-to-earnings ratio valuation",
  },
  {
    kind: "suitability",
    pattern: /\b(is|are) .{1,40}\b(cheap|expensive|a bargain)\b/i,
    topicHint: "price-to-earnings ratio valuation",
  },
  { kind: "suitability", pattern: /\bis .{1,40}\bsafe\b/i },
  { kind: "suitability", pattern: /\bgood (investment|buy)\b/i },

  // Requests for a forecast.
  {
    kind: "prediction",
    pattern: /\bwill .{0,40}\b(prices?|shares?|stocks?|units?|it|they|we)\b.{0,20}\b(go up|go down|rise|fall|increase|drop|crash|recover|double|rebound|climb)\b/i,
    topicHint: "what a share is price movement",
  },
  {
    kind: "prediction",
    pattern: /\b(will|can) .{0,40}\b(pay|maintain|increase|cut) (a |the |its )?dividend\b/i,
    topicHint: "dividend yield",
  },
  {
    kind: "prediction",
    pattern: /\bprice (target|forecast|prediction|projection)\b/i,
    topicHint: "what a share is price movement",
  },
  {
    kind: "prediction",
    pattern: /\b(how much|where) will .{0,40}\b(be worth|the price|it go)\b/i,
    topicHint: "what a share is price movement",
  },
  {
    kind: "prediction",
    pattern: /\b(forecast|predict|projection) (the |for |of )?(price|share|stock|return)\b/i,
    topicHint: "what a share is price movement",
  },
  {
    kind: "prediction",
    pattern: /\b(what|how much) (returns?|profit) (will|can) i (expect|make|get)\b/i,
  },
  { kind: "prediction", pattern: /\bgoing to (moon|crash|skyrocket|tank)\b/i },
];

export function classifyQuestion(question: string): GuardrailVerdict {
  const normalised = question.replace(/\s+/g, " ").trim();

  for (const rule of RULES) {
    const match = rule.pattern.exec(normalised);
    if (match) {
      return {
        allowed: false,
        kind: rule.kind,
        trigger: match[0],
        topicHint: rule.topicHint,
      };
    }
  }

  return { allowed: true };
}

/**
 * The redirect text. One wording per kind, used every time, because a boundary
 * that is phrased differently each time reads as negotiable.
 */
export const REFUSAL_TEXT: Record<RefusalKind, string> = {
  advice:
    "I can't tell you what to buy or sell. That decision depends on your own circumstances — what else you own, what you need the money for, and when you need it — and none of that is something this site knows about you.",
  suitability:
    "I can't judge whether a company is a good or bad investment. What I can do is show you what the company has disclosed and what it has said could go wrong, and explain the concepts you would use to form your own view.",
  prediction:
    "I can't tell you where a price is going. Nobody can, and a site that reports disclosed figures is in a worse position to guess than most. What the filings record is what has already happened.",
};

export const ADVISER_POINTER =
  "For advice on your own situation, speak to an investment adviser registered with the Securities and Exchange Commission of Nigeria. The SEC maintains a public register of licensed operators, which is worth checking before you hand anyone money.";
