import { z } from "zod";

/**
 * The basics library: plain-language explainers for a reader with no finance
 * background. These are one half of the RAG corpus. The other half is the
 * verified company profiles.
 *
 * Explainers are deliberately structured rather than free prose. Each field
 * answers a different kind of question, so retrieval can return the paragraph
 * that actually answers what was asked instead of a whole page.
 */

export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "dates must be ISO yyyy-mm-dd");

export const explainerSchema = z.object({
  /** URL segment, also the citation key used by the RAG layer. */
  slug: z.string().regex(/^[a-z0-9-]+$/),

  /** Short noun phrase: "Price-to-earnings ratio". */
  title: z.string().min(3),

  /**
   * The plain question a first-time investor would actually type. Retrieval
   * matches against this heavily, so it is phrased the way a reader speaks,
   * not the way a textbook indexes.
   */
  question: z.string().min(10),

  /**
   * One-paragraph answer in plain language. This is what the RAG layer quotes
   * by default, and what a reader sees before expanding anything.
   */
  short: z.string().min(40),

  /** Body paragraphs, each self-contained enough to be retrieved alone. */
  body: z.array(z.string().min(40)).min(1),

  /**
   * How the concept behaves on the NGX specifically, where it differs from
   * the US-centric explanations a reader will find everywhere else.
   */
  nigerianContext: z.string().min(40).optional(),

  /**
   * The mistake this concept invites. Kept separate from the body because it
   * is the part most worth surfacing when a reader asks a loaded question.
   */
  commonMisreading: z.string().min(40).optional(),

  /** Slugs of related explainers. Validated as a set at load time. */
  seeAlso: z.array(z.string().regex(/^[a-z0-9-]+$/)).default([]),

  /** When a human last read this through. Explainers go stale too. */
  lastReviewed: isoDate,
});

export type Explainer = z.infer<typeof explainerSchema>;

/**
 * Validates one explainer and returns it typed, or throws with the slug in the
 * message so a bad content file is obvious from the build log.
 */
export function parseExplainer(input: unknown): Explainer {
  const result = explainerSchema.safeParse(input);
  if (!result.success) {
    const slug =
      input && typeof input === "object" && "slug" in input
        ? String((input as { slug: unknown }).slug)
        : "<unknown slug>";
    throw new Error(
      `invalid explainer ${slug}: ${JSON.stringify(result.error.issues, null, 2)}`,
    );
  }
  return result.data;
}
