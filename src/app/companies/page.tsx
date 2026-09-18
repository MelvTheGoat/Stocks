import type { Metadata } from "next";

export const metadata: Metadata = { title: "Companies" };

/**
 * Placeholder until the profile schema lands. Replaced by the profile index.
 */
export default function CompaniesIndexPage() {
  return (
    <div>
      <h1 className="font-serif text-3xl tracking-tight">Companies</h1>
      <p className="prose-measure mt-4 text-[var(--color-ink-soft)]">
        No profiles have been published yet. A profile appears here only once every
        numeric field in it has been checked against the source filing by a person.
      </p>
    </div>
  );
}
