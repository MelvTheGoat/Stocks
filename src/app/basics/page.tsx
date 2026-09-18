import Link from "next/link";
import type { Metadata } from "next";
import { explainers } from "@/lib/basics";

export const metadata: Metadata = {
  title: "Basics",
  description:
    "Short, plain-language explainers of the concepts a first-time Nigerian investor meets.",
};

export default function BasicsIndexPage() {
  return (
    <div>
      <h1 className="font-serif text-3xl tracking-tight">The basics</h1>
      <div className="prose-measure mt-4 text-[var(--color-ink-soft)]">
        <p>
          Each of these answers one question and stands on its own. They are written
          for someone who has never read a set of company accounts, and they are in
          reading order, though you can start anywhere.
        </p>
      </div>

      <ul className="mt-10 space-y-px">
        {explainers.map((explainer) => (
          <li key={explainer.slug}>
            <Link
              href={`/basics/${explainer.slug}`}
              className="block border border-[var(--color-rule)] bg-[var(--color-panel)] px-5 py-4 hover:border-[var(--color-accent)]"
            >
              <span className="font-serif text-lg">{explainer.title}</span>
              <span className="mt-1 block text-sm text-[var(--color-ink-soft)]">
                {explainer.question}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
