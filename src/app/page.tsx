import Link from "next/link";
import { explainers } from "@/lib/basics";

export default function HomePage() {
  return (
    <div>
      <h1 className="font-serif text-4xl tracking-tight leading-tight">
        Read a Nigerian company&rsquo;s numbers without needing a finance degree
      </h1>

      <div className="prose-measure mt-6 text-[var(--color-ink-soft)] text-[1.05rem]">
        <p>
          Company filings are public, but they are written for people who already know
          how to read them. This site does two things about that: it explains the
          concepts in plain language, and it sets out what companies listed on the
          Nigerian Exchange have actually disclosed, with the document and date
          attached to every figure.
        </p>
        <p>
          It does not tell you what to buy. Nothing here is a recommendation, and
          questions about whether something is worth buying get pointed back to the
          relevant explainer and to a registered adviser.
        </p>
      </div>

      <div className="mt-12 grid gap-px sm:grid-cols-3">
        <Link
          href="/basics"
          className="border border-[var(--color-rule)] bg-[var(--color-panel)] px-5 py-5 hover:border-[var(--color-accent)]"
        >
          <h2 className="font-serif text-xl">Basics</h2>
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            {explainers.length} short explainers, from what a share is to how an offer
            is priced.
          </p>
        </Link>

        <Link
          href="/companies"
          className="border border-[var(--color-rule)] bg-[var(--color-panel)] px-5 py-5 hover:border-[var(--color-accent)]"
        >
          <h2 className="font-serif text-xl">Companies</h2>
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            Profiles built from filings. Every figure carries its source and its date.
          </p>
        </Link>

        <Link
          href="/ask"
          className="border border-[var(--color-rule)] bg-[var(--color-panel)] px-5 py-5 hover:border-[var(--color-accent)]"
        >
          <h2 className="font-serif text-xl">Ask</h2>
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            Questions answered from the explainers and the profiles, with citations, or
            not at all.
          </p>
        </Link>
      </div>
    </div>
  );
}
