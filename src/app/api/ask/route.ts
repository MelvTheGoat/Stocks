import { NextResponse } from "next/server";
import { answerQuestion } from "@/rag/answer";
import { Retriever } from "@/rag/retrieve";

/**
 * Built once per server process. The corpus is static between deploys, so
 * rebuilding the index per request would be pure waste.
 */
let retriever: Retriever | undefined;

function getRetriever(): Retriever {
  retriever ??= new Retriever();
  return retriever;
}

const MAX_QUESTION_LENGTH = 500;

export async function POST(request: Request) {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "expected a JSON body" }, { status: 400 });
  }

  const question =
    body && typeof body === "object" && "question" in body
      ? String((body as { question: unknown }).question)
      : "";

  if (!question.trim()) {
    return NextResponse.json({ error: "no question given" }, { status: 400 });
  }

  if (question.length > MAX_QUESTION_LENGTH) {
    return NextResponse.json(
      { error: `questions are limited to ${MAX_QUESTION_LENGTH} characters` },
      { status: 400 },
    );
  }

  try {
    const answer = await answerQuestion(question, { retriever: getRetriever() });
    return NextResponse.json(answer);
  } catch (error) {
    // The reader gets told the request failed, not what the sources say. An
    // error is never an excuse to fall back to an ungrounded answer.
    console.error("answering failed", error);
    return NextResponse.json(
      { error: "something went wrong answering that. Please try again." },
      { status: 500 },
    );
  }
}
