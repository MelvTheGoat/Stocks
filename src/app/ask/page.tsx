import type { Metadata } from "next";

export const metadata: Metadata = { title: "Ask" };

/**
 * Placeholder until the retrieval layer lands.
 */
export default function AskPage() {
  return (
    <div>
      <h1 className="font-serif text-3xl tracking-tight">Ask</h1>
      <p className="prose-measure mt-4 text-[var(--color-ink-soft)]">
        Questions are answered from the explainers and the published profiles, with a
        citation for every claim. Where the sources do not contain an answer, you get
        told that rather than a guess.
      </p>
    </div>
  );
}
