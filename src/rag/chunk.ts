/**
 * A chunk is the unit of retrieval and the unit of citation. Nothing reaches a
 * reader through the Q&A layer without being a chunk, which is what makes
 * "every claim carries a citation" enforceable rather than aspirational.
 */

/** Which tier of a profile a chunk came from. Explainers are always tier 1. */
export type Tier = 1 | 2;

export type ChunkProvenance =
  | {
      kind: "explainer";
      /** Explainer slug, used to build the citation link. */
      slug: string;
      title: string;
      /** Which field of the explainer, e.g. "short" or "body[2]". */
      field: string;
    }
  | {
      kind: "profile";
      /** NGX ticker, used to build the citation link. */
      ticker: string;
      company: string;
      /** Profile section number from the schema, e.g. 4. */
      section: number;
      sectionTitle: string;
      field: string;
      /**
       * The filing this text reports from, and its as-of date. Present on any
       * chunk carrying a figure, so a cited number can always be traced back.
       */
      sourceDocument?: string;
      asOf?: string;
    };

export type Chunk = {
  /** Stable across rebuilds so citations in logs stay meaningful. */
  id: string;
  text: string;
  tier: Tier;
  provenance: ChunkProvenance;
};

/** Human-readable citation label, e.g. "Dangote Refinery, section 4". */
export function citationLabel(chunk: Chunk): string {
  const p = chunk.provenance;

  if (p.kind === "explainer") {
    return p.title;
  }

  const base = `${p.company}, ${p.sectionTitle}`;
  if (p.sourceDocument && p.asOf) {
    return `${base} (${p.sourceDocument}, as of ${p.asOf})`;
  }
  return base;
}

/** In-app link for a citation. */
export function citationHref(chunk: Chunk): string {
  const p = chunk.provenance;
  return p.kind === "explainer"
    ? `/basics/${p.slug}`
    : `/companies/${p.ticker.toLowerCase()}`;
}

export function chunkId(provenance: ChunkProvenance): string {
  return provenance.kind === "explainer"
    ? `explainer:${provenance.slug}:${provenance.field}`
    : `profile:${provenance.ticker}:${provenance.section}:${provenance.field}`;
}
