import type { Metadata } from "next";
import { AskForm } from "@/components/AskForm";

export const metadata: Metadata = {
  title: "Ask",
  description:
    "Questions answered from the basics library and the published company profiles, with a citation for every claim.",
};

export default function AskPage() {
  return (
    <div>
      <h1 className="font-serif text-3xl tracking-tight">Ask</h1>

      <div className="prose-measure mt-4 text-[var(--color-ink-soft)]">
        <p>
          Answers come from the explainers and the published profiles, and nothing
          else. Every claim carries a citation you can follow. Where the sources
          don&rsquo;t cover something, you get told that rather than a guess.
        </p>
        <p>
          Questions about whether to buy, whether something is a good investment, or
          where a price is heading are not answered here. Those get pointed at the
          explainer behind the question and at a registered adviser.
        </p>
      </div>

      <div className="mt-10">
        <AskForm />
      </div>
    </div>
  );
}
