import MiniSearch from "minisearch";
import { indexedText, type Chunk } from "@/rag/chunk";
import { buildCorpus } from "@/rag/corpus";

/**
 * Retrieval over the chunk corpus.
 *
 * BM25 rather than embeddings, deliberately. The corpus is small, the
 * vocabulary is narrow and largely shared between question and source, and a
 * lexical index means the whole thing runs with no API key and no build step
 * anyone has to remember. It also makes "why did it return this" answerable,
 * which matters when the product's promise is that it never improvises.
 */

export type Retrieved = {
  chunk: Chunk;
  score: number;
};

/**
 * Words carrying no topic signal. Dropped from both the index and the query,
 * because a raw BM25 score is not comparable between one question and the
 * next: a long question full of common words accumulates score across every
 * chunk that happens to contain them. "How do I cook jollof rice?" outscored
 * several genuine matches before these came out.
 */
const STOPWORDS = new Set([
  "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as",
  "at", "be", "been", "before", "being", "between", "both", "but", "by", "can",
  "could", "did", "do", "does", "doing", "done", "during", "each", "for",
  "from", "get", "had", "has", "have", "how", "i", "if", "in", "into", "is",
  "it", "its", "just", "know", "last", "like", "make", "many", "me", "mean",
  "means", "more", "most", "much", "my", "no", "not", "now", "of", "on", "one",
  "only", "or", "other", "our", "out", "over", "own", "should", "so", "some",
  "such", "tell", "than", "that", "the", "their", "them", "then", "there",
  "these", "they", "this", "those", "through", "to", "under", "up", "use",
  "very", "was", "we", "well", "were", "what", "when", "where", "which",
  "while", "who", "why", "will", "with", "would", "you", "your",
]);

/**
 * Index and query must be tokenised identically, or coverage is measured
 * against a denominator the index never had a chance to match. "P/E" was the
 * case that surfaced this: the query kept it as one term while the index split
 * it into two one-letter fragments and discarded both, so a question about the
 * P/E ratio could never reach full coverage. One tokenizer, used by both.
 *
 * Slashes are kept inside a token so "p/e" survives. Hyphens are not, so
 * "price-to-earnings" is findable by someone searching for earnings.
 */
function tokenize(text: string): string[] {
  return text.toLowerCase().split(/[^a-z0-9/]+/).filter(Boolean);
}

function normaliseTerm(term: string): string | null {
  const cleaned = term.replace(/^\/+|\/+$/g, "");
  if (cleaned.length < 3) return null;
  if (STOPWORDS.has(cleaned)) return null;
  return cleaned;
}

/**
 * Fraction of a question's content words that must appear in a chunk for it to
 * count as an answer rather than a coincidence.
 *
 * Short questions are held to a stricter rule: with only two or three content
 * words there is no room for a partial match to mean anything, so all of them
 * have to land. "Who won the election?" matched one word out of two and came
 * back with an IPO paragraph before this was tightened. Longer questions fall
 * back to the fraction, because a reader who writes a sentence should not be
 * punished for the words that happen not to be in the corpus.
 */
export const MIN_TERM_COVERAGE = 0.6;
const EXACT_MATCH_MAX_TERMS = 3;

function requiredCoverage(termCount: number): number {
  return termCount <= EXACT_MATCH_MAX_TERMS ? 1 : MIN_TERM_COVERAGE;
}

/** Content terms in a question, deduplicated, in the form the index stores. */
export function queryTerms(question: string): string[] {
  const terms = tokenize(question)
    .map(normaliseTerm)
    .filter((term): term is string => term !== null);

  return [...new Set(terms)];
}

function createIndex(corpus: Chunk[]): MiniSearch<Chunk> {
  const index = new MiniSearch<Chunk>({
    fields: ["text"],
    storeFields: ["id"],
    idField: "id",
    extractField: (chunk, field) =>
      field === "text" ? indexedText(chunk) : String(chunk[field as keyof Chunk] ?? ""),
    tokenize,
    processTerm: normaliseTerm,
    searchOptions: {
      boost: { text: 1 },
      // Prefix matching is off. It was the main source of false confidence:
      // it let short common fragments match a dozen unrelated chunks.
      fuzzy: 0.1,
    },
  });

  index.addAll(corpus);
  return index;
}

/**
 * Words that signal the reader wants the detail behind the headline. Tier 2
 * content stays out of retrieval unless one of these appears, so an ordinary
 * question gets the plain-language answer rather than a debt schedule.
 */
const DETAIL_SIGNALS = [
  /\bexact(ly)?\b/i,
  /\bbreak ?down\b/i,
  /\bdetail(ed|s)?\b/i,
  /\bmargins?\b/i,
  /\bmultiples?\b/i,
  /\bdebt (structure|schedule|maturity|profile)\b/i,
  /\brelated[- ]part(y|ies)\b/i,
  /\bline items?\b/i,
  /\bfull (table|figures|accounts|numbers)\b/i,
  /\bsegment(al|s)?\b/i,
  /\bper share\b/i,
  /\bhow much precisely\b/i,
  /\byear[- ]on[- ]year\b/i,
  /\bquarter(ly)?\b/i,
];

export function wantsDetail(question: string): boolean {
  return DETAIL_SIGNALS.some((pattern) => pattern.test(question));
}

export class Retriever {
  private readonly corpus: Chunk[];
  private readonly byId: Map<string, Chunk>;
  private readonly index: MiniSearch<Chunk>;

  constructor(corpus: Chunk[] = buildCorpus()) {
    this.corpus = corpus;
    this.byId = new Map(corpus.map((chunk) => [chunk.id, chunk]));
    this.index = createIndex(corpus);
  }

  /**
   * Returns chunks that clear the coverage bar, highest scoring first. An
   * empty result is a meaningful answer in itself: it is what makes the Q&A
   * layer say it does not know instead of reaching for the nearest paragraph.
   *
   * Tier 2 chunks are filtered out unless the question asks for detail. The
   * filter runs after scoring so a detail question competes on merit rather
   * than being handed a different index.
   */
  search(question: string, limit = 6): Retrieved[] {
    const includeTier2 = wantsDetail(question);
    const asked = queryTerms(question);

    // A question with no content words at all ("what is it?") cannot be
    // matched on coverage, and is not worth guessing at.
    if (asked.length === 0) return [];
    const floor = requiredCoverage(asked.length);

    return this.index
      .search(question)
      .map((result) => ({
        chunk: this.byId.get(String(result.id)),
        score: result.score,
        coverage: result.terms.length / asked.length,
      }))
      .filter((r): r is Retrieved & { coverage: number } => r.chunk !== undefined)
      .filter((r) => r.coverage >= floor)
      .filter((r) => includeTier2 || r.chunk.tier === 1)
      .slice(0, limit)
      .map(({ chunk, score }) => ({ chunk, score }));
  }

  /**
   * Best-matching explainer for a question, used to choose which explainer a
   * refused question is redirected to. Restricted to the basics library: a
   * reader asking whether to buy is sent to a concept, never to a company.
   */
  bestExplainer(question: string): Chunk | undefined {
    return this.index
      .search(question)
      .map((result) => this.byId.get(String(result.id)))
      .find((chunk) => chunk?.provenance.kind === "explainer");
  }

  size(): number {
    return this.corpus.length;
  }
}
