import { rawExplainers } from "@content/basics";
import { parseExplainer, type Explainer } from "@/schema/basics";
import { checkContent, formatViolations } from "@/lib/editorial";

/**
 * Loads, validates and indexes the basics library once per process.
 *
 * Validation happens at module load rather than in a separate script so that a
 * malformed explainer fails the build and the dev server alike, instead of
 * rendering a half-broken page.
 */
function loadExplainers(): Explainer[] {
  const explainers = rawExplainers.map(parseExplainer);

  const slugs = new Set<string>();
  for (const explainer of explainers) {
    if (slugs.has(explainer.slug)) {
      throw new Error(`duplicate explainer slug: ${explainer.slug}`);
    }
    slugs.add(explainer.slug);
  }

  for (const explainer of explainers) {
    for (const related of explainer.seeAlso) {
      if (!slugs.has(related)) {
        throw new Error(
          `explainer ${explainer.slug} links to unknown slug: ${related}`,
        );
      }
      if (related === explainer.slug) {
        throw new Error(`explainer ${explainer.slug} links to itself`);
      }
    }
  }

  const violations = explainers.flatMap((explainer) =>
    checkContent(explainer.slug, explainer, "basics"),
  );
  if (violations.length > 0) {
    throw new Error(
      `recommendation language in the basics library:\n${formatViolations(violations)}`,
    );
  }

  return explainers;
}

export const explainers: Explainer[] = loadExplainers();

const bySlug = new Map(explainers.map((e) => [e.slug, e]));

export function getExplainer(slug: string): Explainer | undefined {
  return bySlug.get(slug);
}

export function requireExplainer(slug: string): Explainer {
  const explainer = bySlug.get(slug);
  if (!explainer) {
    throw new Error(`no explainer with slug: ${slug}`);
  }
  return explainer;
}

export function explainerSlugs(): string[] {
  return explainers.map((e) => e.slug);
}
