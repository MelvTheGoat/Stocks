import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { explainerSlugs, getExplainer } from "@/lib/basics";

type Params = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return explainerSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const explainer = getExplainer(slug);
  if (!explainer) return {};

  return { title: explainer.title, description: explainer.question };
}

export default async function ExplainerPage({ params }: Params) {
  const { slug } = await params;
  const explainer = getExplainer(slug);
  if (!explainer) notFound();

  return (
    <article>
      <Link href="/basics" className="text-sm text-[var(--color-ink-faint)] hover:underline">
        Basics
      </Link>

      <h1 className="mt-3 font-serif text-3xl tracking-tight">{explainer.title}</h1>
      <p className="mt-2 text-[var(--color-ink-faint)]">{explainer.question}</p>

      {/* The one-paragraph answer, set apart because most readers need only this. */}
      <div className="prose-measure mt-8 border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-5 py-4">
        <p className="text-[1.05rem]">{explainer.short}</p>
      </div>

      <div className="prose-measure mt-8">
        {explainer.body.map((paragraph) => (
          <p key={paragraph.slice(0, 48)}>{paragraph}</p>
        ))}
      </div>

      {explainer.nigerianContext ? (
        <section className="prose-measure mt-10 border border-[var(--color-rule)] bg-[var(--color-panel)] px-5 py-5">
          <h2 className="font-serif text-xl">On the NGX specifically</h2>
          <p className="mt-3">{explainer.nigerianContext}</p>
        </section>
      ) : null}

      {explainer.commonMisreading ? (
        <section className="prose-measure mt-6 border-l-2 border-[var(--color-flag)] bg-[var(--color-flag-soft)] px-5 py-4">
          <h2 className="font-serif text-xl">The common misreading</h2>
          <p className="mt-3">{explainer.commonMisreading}</p>
        </section>
      ) : null}

      {explainer.seeAlso.length > 0 ? (
        <nav className="mt-10 border-t border-[var(--color-rule)] pt-5">
          <h2 className="text-sm uppercase tracking-wide text-[var(--color-ink-faint)]">
            Related
          </h2>
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
            {explainer.seeAlso.map((related) => (
              <li key={related}>
                <Link
                  href={`/basics/${related}`}
                  className="text-[var(--color-accent)] hover:underline"
                >
                  {getExplainer(related)?.title ?? related}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}

      <p className="mt-10 text-sm text-[var(--color-ink-faint)]">
        Last reviewed {explainer.lastReviewed}.
      </p>
    </article>
  );
}
