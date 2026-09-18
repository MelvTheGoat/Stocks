/**
 * Editorial guard against recommendation language.
 *
 * The product explains and discloses. It does not advise. That boundary is
 * easy to state and easy to erode one adjective at a time, so it is enforced
 * mechanically over every string that reaches a reader, in both the basics
 * library and the company profiles.
 */

/**
 * Where a rule applies.
 *
 * "everywhere" covers recommendations and predictions. There is no context in
 * which this product tells a reader what to do or what a price will do.
 *
 * "profile" additionally bans valuation adjectives, but only in company
 * profiles. The distinction is deliberate: the danger is the product calling a
 * particular company cheap, not the basics library explaining that "cheap" is
 * a word without meaning until you know what it is measured against. Teaching
 * a reader to distrust a term requires naming it.
 */
type RuleScope = "everywhere" | "profile";

type BannedPhrase = {
  /** Matched case-insensitively against content text. */
  pattern: RegExp;
  /** Shown to whoever wrote the offending copy. */
  reason: string;
  scope: RuleScope;
};

const BANNED: BannedPhrase[] = [
  { pattern: /\battractive(ly)?\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bunder-?valued\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bover-?valued\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bcheap(er|ly)?\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bexpensive\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bbargain\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bcompelling\b/i, reason: "valuation judgement", scope: "profile" },
  { pattern: /\bone to watch\b/i, reason: "recommendation", scope: "everywhere" },
  { pattern: /\bstrong buy\b/i, reason: "recommendation", scope: "everywhere" },
  {
    pattern: /\b(should|must) (buy|sell|invest)\b/i,
    reason: "recommendation",
    scope: "everywhere",
  },
  {
    pattern: /\bwe (recommend|advise|suggest)\b/i,
    reason: "recommendation",
    scope: "everywhere",
  },
  { pattern: /\bgood investment\b/i, reason: "recommendation", scope: "everywhere" },
  {
    pattern: /\bbest (stock|share|pick)s?\b/i,
    reason: "recommendation",
    scope: "everywhere",
  },
  { pattern: /\btop pick\b/i, reason: "recommendation", scope: "everywhere" },
  { pattern: /\bpoised (to|for)\b/i, reason: "forward-looking claim", scope: "everywhere" },
  {
    pattern: /\bset to (rise|soar|surge|grow)\b/i,
    reason: "forward-looking claim",
    scope: "everywhere",
  },
  {
    pattern: /\bwill (outperform|rally|rise|climb)\b/i,
    reason: "forward-looking claim",
    scope: "everywhere",
  },
  {
    pattern: /\bguaranteed returns?\b/i,
    reason: "forward-looking claim",
    scope: "everywhere",
  },
  {
    pattern: /\bhigh(-| )?potential\b/i,
    reason: "forward-looking claim",
    scope: "everywhere",
  },
];

export type EditorialViolation = {
  /** Dotted path to the offending field, e.g. "pe-ratio.body[2]". */
  field: string;
  phrase: string;
  reason: string;
  /** Enough surrounding text to find the sentence. */
  excerpt: string;
};

function excerptAround(text: string, index: number, length: number): string {
  const start = Math.max(0, index - 40);
  const end = Math.min(text.length, index + length + 40);
  return `${start > 0 ? "..." : ""}${text.slice(start, end)}${end < text.length ? "..." : ""}`;
}

/**
 * Which body of content is being checked. Profiles carry the stricter rules
 * because they describe one named company.
 */
export type ContentKind = "basics" | "profile";

/** Checks one string. Exported for unit tests and for the profile verifier. */
export function checkText(
  field: string,
  text: string,
  kind: ContentKind = "profile",
): EditorialViolation[] {
  const violations: EditorialViolation[] = [];

  for (const { pattern, reason, scope } of BANNED) {
    if (scope === "profile" && kind !== "profile") continue;

    const match = pattern.exec(text);
    if (match) {
      violations.push({
        field,
        phrase: match[0],
        reason,
        excerpt: excerptAround(text, match.index, match[0].length),
      });
    }
  }

  return violations;
}

/**
 * Walks any nested content object and checks every string it contains, so a
 * new schema field is covered without anyone remembering to add it here.
 */
export function checkContent(
  prefix: string,
  value: unknown,
  kind: ContentKind = "profile",
): EditorialViolation[] {
  if (typeof value === "string") {
    return checkText(prefix, value, kind);
  }

  if (Array.isArray(value)) {
    return value.flatMap((item, i) => checkContent(`${prefix}[${i}]`, item, kind));
  }

  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) =>
      checkContent(prefix ? `${prefix}.${key}` : key, item, kind),
    );
  }

  return [];
}

export function formatViolations(violations: EditorialViolation[]): string {
  return violations
    .map(
      (v) =>
        `  ${v.field}: "${v.phrase}" (${v.reason})\n      ${v.excerpt.replace(/\s+/g, " ")}`,
    )
    .join("\n");
}
