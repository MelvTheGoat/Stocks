"use client";

import { useState } from "react";
import Link from "next/link";
import type { Answer } from "@/rag/answer";

const EXAMPLES = [
  "What is a P/E ratio?",
  "What does free float mean?",
  "How is an IPO priced?",
  "What is a greenshoe option?",
];

export function AskForm() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function ask(asked: string) {
    if (!asked.trim() || pending) return;

    setPending(true);
    setError(null);
    setAnswer(null);

    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: asked }),
      });

      const payload = await response.json();
      if (!response.ok) {
        setError(payload.error ?? "that didn't work");
        return;
      }

      setAnswer(payload as Answer);
    } catch {
      setError("couldn't reach the server");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about a concept or a published figure"
          maxLength={500}
          aria-label="Your question"
          className="flex-1 border border-[var(--color-rule)] bg-[var(--color-panel)] px-4 py-3 outline-none focus:border-[var(--color-accent)]"
        />
        <button
          type="submit"
          disabled={pending || !question.trim()}
          className="border border-[var(--color-accent)] bg-[var(--color-accent)] px-6 py-3 text-[var(--color-page)] disabled:opacity-40"
        >
          {pending ? "Looking" : "Ask"}
        </button>
      </form>

      <div className="mt-4 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setQuestion(example);
              void ask(example);
            }}
            className="border border-[var(--color-rule)] px-3 py-1.5 text-sm text-[var(--color-ink-soft)] hover:border-[var(--color-accent)]"
          >
            {example}
          </button>
        ))}
      </div>

      {error ? (
        <p className="mt-8 border-l-2 border-[var(--color-flag)] bg-[var(--color-flag-soft)] px-5 py-4">
          {error}
        </p>
      ) : null}

      {answer ? <AnswerPanel answer={answer} /> : null}
    </div>
  );
}

function AnswerPanel({ answer }: { answer: Answer }) {
  const isRefusal = answer.kind === "refusal";

  return (
    <section
      className={`mt-8 border-l-2 px-5 py-5 ${
        isRefusal
          ? "border-[var(--color-flag)] bg-[var(--color-flag-soft)]"
          : "border-[var(--color-accent)] bg-[var(--color-panel)]"
      }`}
    >
      <div className="prose-measure">
        {answer.text.split("\n\n").map((paragraph) => (
          <p key={paragraph.slice(0, 40)}>{paragraph}</p>
        ))}
      </div>

      {answer.relatedExplainer ? (
        <p className="mt-4">
          <Link
            href={answer.relatedExplainer.href}
            className="text-[var(--color-accent)] underline"
          >
            Read: {answer.relatedExplainer.title}
          </Link>
        </p>
      ) : null}

      {answer.adviserPointer ? (
        <p className="prose-measure mt-4 text-sm text-[var(--color-ink-soft)]">
          {answer.adviserPointer}
        </p>
      ) : null}

      {answer.citations.length > 0 ? (
        <div className="mt-6 border-t border-[var(--color-rule)] pt-4">
          <h2 className="text-sm uppercase tracking-wide text-[var(--color-ink-faint)]">
            Sources
          </h2>
          <ol className="mt-2 space-y-1 text-sm">
            {answer.citations.map((citation) => (
              <li key={citation.index}>
                <span className="text-[var(--color-ink-faint)]">[{citation.index}]</span>{" "}
                <Link
                  href={citation.href}
                  className="text-[var(--color-accent)] hover:underline"
                >
                  {citation.label}
                </Link>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
