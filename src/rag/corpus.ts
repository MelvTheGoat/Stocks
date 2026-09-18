import { explainers } from "@/lib/basics";
import type { Explainer } from "@/schema/basics";
import { chunkId, type Chunk } from "@/rag/chunk";

/**
 * Builds the retrieval corpus.
 *
 * Explainers chunk field by field rather than paragraph by paragraph, because
 * the fields already carry meaning: "short" is the plain answer, "body[n]" is
 * elaboration, "commonMisreading" is the trap. Retrieval can then prefer the
 * field that matches the shape of the question.
 *
 * Company profiles join the same corpus once published, carrying their tier
 * and their source document with them.
 */

function explainerChunks(explainer: Explainer): Chunk[] {
  const chunks: Chunk[] = [];

  const add = (field: string, text: string) => {
    const provenance = {
      kind: "explainer" as const,
      slug: explainer.slug,
      title: explainer.title,
      field,
    };

    chunks.push({
      id: chunkId(provenance),
      // The question is prepended so retrieval matches a reader's phrasing
      // against the phrasing the explainer was written to answer.
      text: field === "short" ? `${explainer.question} ${text}` : text,
      tier: 1,
      provenance,
    });
  };

  add("short", explainer.short);
  explainer.body.forEach((paragraph, i) => add(`body[${i}]`, paragraph));
  if (explainer.nigerianContext) add("nigerianContext", explainer.nigerianContext);
  if (explainer.commonMisreading) add("commonMisreading", explainer.commonMisreading);

  return chunks;
}

/**
 * The full corpus. Profile chunks are appended by the profile loader once the
 * schema lands; explainers are the standing half.
 */
export function buildCorpus(profileChunks: Chunk[] = []): Chunk[] {
  return [...explainers.flatMap(explainerChunks), ...profileChunks];
}
