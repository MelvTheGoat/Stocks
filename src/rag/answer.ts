import Anthropic from "@anthropic-ai/sdk";
import { citationHref, citationLabel, type Chunk } from "@/rag/chunk";
import { Retriever } from "@/rag/retrieve";
import { buildUserMessage, SYSTEM_PROMPT } from "@/rag/prompts";
import {
  ADVISER_POINTER,
  classifyQuestion,
  REFUSAL_TEXT,
  type RefusalKind,
} from "@/rag/guardrails";
import { checkContent } from "@/lib/editorial";

export type Citation = {
  /** Position in the answer text, so [1] lines up with the list. */
  index: number;
  label: string;
  href: string;
};

export type Answer = {
  /**
   * answer         - grounded in retrieved sources
   * refusal        - out of bounds by design, redirected
   * not-in-sources - in bounds, but the corpus does not cover it
   */
  kind: "answer" | "refusal" | "not-in-sources";
  text: string;
  citations: Citation[];
  /** Explainer offered alongside a refusal. */
  relatedExplainer?: { title: string; href: string };
  adviserPointer?: string;
  /** Which guardrail fired, for logging and for the UI to label the reply. */
  refusalKind?: RefusalKind;
};

const MODEL = "claude-opus-5";

function toCitations(chunks: Chunk[]): Citation[] {
  return chunks.map((chunk, i) => ({
    index: i + 1,
    label: citationLabel(chunk),
    href: citationHref(chunk),
  }));
}

/**
 * Deterministic answer built by quoting the best-matching source.
 *
 * Used when no API key is configured, and as the fallback when the model's
 * answer trips the editorial check. Quoting verified text is never wrong in
 * the way a generated sentence can be, so falling back here is safe.
 */
function extractiveAnswer(chunks: Chunk[]): Answer {
  const best = chunks[0];

  return {
    kind: "answer",
    text: `${best.text} [1]`,
    citations: toCitations(chunks.slice(0, 1)),
  };
}

function notInSources(question: string): Answer {
  return {
    kind: "not-in-sources",
    text: `I don't have anything in my sources that answers that. What I can answer from is the basics library and the published company profiles, and neither covers ${question.trim().replace(/\?+$/, "")}. Rather than guess, I'd rather tell you I don't have it.`,
    citations: [],
  };
}

function refusal(kind: RefusalKind, explainer: Chunk | undefined): Answer {
  const related =
    explainer && explainer.provenance.kind === "explainer"
      ? {
          title: explainer.provenance.title,
          href: citationHref(explainer),
        }
      : undefined;

  const bridge = related
    ? `\n\nWhat I can do is explain the idea behind the question. "${related.title}" covers it.`
    : "";

  return {
    kind: "refusal",
    refusalKind: kind,
    text: `${REFUSAL_TEXT[kind]}${bridge}`,
    citations: [],
    relatedExplainer: related,
    adviserPointer: ADVISER_POINTER,
  };
}

export type AnswerOptions = {
  retriever?: Retriever;
  client?: Anthropic;
};

/**
 * The single entry point for the Q&A layer.
 *
 * Order matters and is the whole design: classify, then retrieve, then
 * generate. A question that fails classification never reaches the corpus, and
 * a question with no retrieved sources never reaches the model.
 */
export async function answerQuestion(
  question: string,
  options: AnswerOptions = {},
): Promise<Answer> {
  const retriever = options.retriever ?? new Retriever();

  const verdict = classifyQuestion(question);
  if (!verdict.allowed) {
    // The redirect target is chosen by searching the basics library for the
    // concept behind the question, so "will Dangote's price go up" lands on
    // the explainer about what a share is rather than on a company profile.
    const explainer = retriever.bestExplainer(verdict.topicHint ?? question);
    return refusal(verdict.kind, explainer);
  }

  const retrieved = retriever.search(question);
  if (retrieved.length === 0) {
    return notInSources(question);
  }

  const chunks = retrieved.map((r) => r.chunk);

  const client = options.client ?? createClient();
  if (!client) {
    return extractiveAnswer(chunks);
  }

  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 1600,
    system: SYSTEM_PROMPT,
    thinking: { type: "adaptive" },
    // Low effort: the task is constrained synthesis over a handful of short
    // passages, not reasoning. Depth here would buy nothing and cost latency.
    output_config: { effort: "low" },
    messages: [{ role: "user", content: buildUserMessage(question, chunks) }],
  });

  if (response.stop_reason === "refusal") {
    return notInSources(question);
  }

  const text = response.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("\n")
    .trim();

  if (!text) {
    return extractiveAnswer(chunks);
  }

  // Belt and braces: the prompt forbids recommendation language, and this
  // checks that it complied. A violation falls back to quoting the source
  // rather than shipping the sentence.
  const violations = checkContent("answer", text, "profile");
  if (violations.length > 0) {
    return extractiveAnswer(chunks);
  }

  return { kind: "answer", text, citations: toCitations(chunks) };
}

function createClient(): Anthropic | undefined {
  return process.env.ANTHROPIC_API_KEY ? new Anthropic() : undefined;
}
