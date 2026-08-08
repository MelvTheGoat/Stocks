# AI Engineer Interview — Prep Notes

Eight questions, answered. Read the "say this" bullets; the prose underneath is
there so you can go deeper when they push.

**Three rules that apply to every answer:**

1. **Name a metric.** "It worked well" is a losing answer. "Acceptance rate went
   from 41% to 68% on the golden set, p95 latency 2.3s" is a winning one. Make
   numbers up only if they're yours — never invent them, but don't be vague
   about ones you have.
2. **Name the tradeoff you accepted.** Every real system has one. Volunteering
   it signals you've shipped; hiding it signals you haven't.
3. **Distinguish "the model was wrong" from "my system was wrong."** Most
   interviewers are listening for whether you blame the model reflexively.

---

## 1. AI Project Experience

> Provide a live working link… what problem did it solve, what tools did you use,
> what did you personally implement?

**This one is yours to fill in — I can't supply a link to something you built.**
What I can give you is the structure that makes the answer land, and a fallback
if nothing of yours is currently live.

### The answer skeleton (aim for ~90 seconds, then let them dig)

| Beat | What to say | Common failure |
|---|---|---|
| **Problem** | Who was suffering, and how much. "Support reps spent ~6 min per ticket digging through a 400-page policy wiki." | Leading with the tech stack |
| **Why AI** | Why a search box or a rules engine *wasn't* enough | Sounding like AI was a solution hunting for a problem |
| **Architecture** | 4–5 sentences, end to end: ingest → chunk → index → retrieve → rerank → generate → guardrail → UI | Naming frameworks without explaining data flow |
| **What *I* built** | Be surgical and first-person. "I owned the ingestion pipeline and the eval harness; a teammate did the frontend." | Fuzzy "we" — interviewers assume the worst |
| **Result** | A number. Latency, accuracy on your eval set, hours saved, tickets deflected, users. | "People liked it" |
| **What I'd redo** | One honest thing. "Fixed-size chunking hurt me; I'd chunk on document structure now." | Claiming you'd change nothing |

### Demo hygiene (this is where people lose the interview, not on the answers)

- **Wake it up 30 minutes before.** Cold serverless starts and sleeping free-tier
  dynos have killed more interviews than bad architecture.
- **Have three queries ready:** one that shows it working, one that shows it
  citing sources, one that shows it *correctly refusing* — "I don't have
  anything on that." The refusal demo is the most impressive of the three
  because almost no candidate shows it.
- **Have a known failure ready and volunteer it.** "Watch — it degrades on
  multi-hop questions, here's why, here's what I'd do." That reads as senior.
- **Have the eval numbers open in a second tab.** If you can show a golden-set
  scorecard, you separate yourself from everyone demoing a chat box.
- **Know your cost per query.** They will ask. Have the number.

### If nothing of yours is currently deployed

Don't bluff it — say plainly: "I don't have a production system from a previous
role I can show, so I built one to demonstrate how I work." Then show it. A
small, genuinely-live, honestly-scoped app beats a vague story about a big one.

A weekend-sized project that demos well and fits this repo's subject matter:
**Q&A over SEC filings and earnings calls with mandatory citations.**

- Ingest 10-K/10-Q/8-K for ~20 tickers from EDGAR (free, no auth, real messy
  data — chunking on section headers actually matters here)
- Hybrid retrieval (BM25 + embeddings) → rerank → answer with inline citations
  linking back to the exact filing section
- **Refuses when retrieval score is below threshold** — critical, because
  finance is a domain where a confident wrong number is worse than "I don't know"
- A `/evals` page showing pass rate on a 50-question golden set you wrote by hand
- Deploy on anything with a stable URL (Vercel/Render/Fly). Keep it awake.

Two to three days of work, and it gives you real material for questions 3, 4, 7
and 8 instead of hypotheticals. **If you want, I can build this out in this repo
— say the word and I'll start.**

> ⚠️ Never claim a system is live if it isn't, and never present a demo built
> for the interview as prior production work. Getting caught on that ends the
> process; being straightforward about what it is costs you nothing.

---

## 2. AI Workflow Design

> Pick a business workflow… how would you design the first prototype, and how
> would you know if it is useful?

**Pick: support ticket triage + first-draft reply.** It's a good choice out loud
because it has abundant labeled history (every past ticket and its actual
resolution *is* a training and eval set), a human already in the loop, and an
existing baseline metric to beat.

### Say this

- "I'd make it **assistive, not autonomous**, in v1 — it drafts, a human sends."
- "I'd build the **eval set before the prototype**, from historical tickets."
- "I'd define what makes me **kill** it before I start."

### The design

**Scope hard.** Not "an AI support agent." One ticket category — say billing
questions — that represents 30% of volume and has stable, documented answers.
Narrow scope is what makes v1 shippable and evaluable.

**Shape of v1:**

```
ticket → classify (category + urgency + sentiment)
      → retrieve (past resolved tickets + policy docs)
      → draft reply w/ citations
      → surface in agent's existing tool as a suggestion
      → capture: accepted / edited / discarded  ← this is the whole product
```

That last line is the point. **The telemetry is the deliverable in v1**, not the
draft quality. If you don't instrument accept/edit/reject from day one you have
no idea whether it's useful and no data to improve on.

**Three phases, gated:**

1. **Offline** — replay 200 historical tickets, compare drafts to what the human
   actually sent. Cheap, zero risk, catches the embarrassing failures.
2. **Shadow** — runs live on real tickets, output visible only to me. Confirms
   it survives real traffic distribution (typos, angry customers, multi-issue
   tickets, wrong-category tickets).
3. **Suggest** — visible to a small opt-in group of reps. Now you learn.

**How I'd know it's useful** — leading indicators first, business metrics second:

| Signal | Read |
|---|---|
| Edit distance between draft and sent reply | The single best proxy for quality |
| Acceptance rate (sent ≈ unedited) | Target something like 40%+ to be worth the tab-switch |
| Handle time vs. control group | The actual business case |
| CSAT on AI-assisted vs. not | Guards against "faster but worse" |
| Rep opt-in retention after 2 weeks | **The honest one** — reps abandon tools that waste their time, and voluntary sustained use is the least gameable signal you have |

**Kill criteria, stated upfront:** if acceptance is under ~20% after two
iterations, or CSAT drops at all, or reps stop using it voluntarily — it dies.
Saying this unprompted is a strong signal; most candidates only describe how
their project succeeds.

**Likely follow-up:** *"What if reps game the acceptance metric?"* — That's why
you pair it with CSAT and edit distance, and why you A/B against a control group
rather than reading the metric in isolation.

---

## 3. Prompting and Evaluation

> How would you test whether a prompt is producing reliable answers over time?
> What examples or edge cases?

### Say this

- "**Prompts are code.** They live in version control, they have tests, tests run
  in CI, and I don't merge a prompt change that regresses the suite."
- "I evaluate **per-slice, not in aggregate** — an 85% average can hide a
  category that's at 20%."
- "LLM-as-judge is useful, but **the judge itself needs validating** against
  human labels before I trust it."

### The harness

**Golden set: 50–200 cases**, each with input, expected behavior, and a
category tag. Hand-written at first, then grown from real production failures —
every bug becomes a permanent test case. That growth loop matters more than the
initial size.

**Three tiers of assertion, cheapest first:**

1. **Deterministic** — valid JSON, schema conformance, required citation present,
   no PII in output, refused when it should refuse, number extracted matches
   source. Free, fast, catches most regressions. Push as much as possible here.
2. **LLM-as-judge** — a rubric with explicit criteria, not "rate 1-10." Validate
   it: label 50 cases by hand, check judge agreement, and only trust the judge on
   the dimensions where it agrees. Use a different model as judge than the one
   under test where you can.
3. **Human review** — a sampled subset, on the dimensions judges are bad at
   (tone, whether an answer is *actually* actionable).

**Handling nondeterminism:** run each case 3–5 times and track pass *rate*, not
pass/fail. A prompt that passes 3/5 is a flaky prompt, and pinning temperature to
0 hides that instead of fixing it. Pin the model version explicitly — silent
provider-side model updates are a real source of "it worked last month."

**Over time** specifically: CI on every prompt change, scheduled runs against a
pinned version to catch provider drift, dashboards of production quality signals
(thumbs-down rate, escalation rate, retry rate) sliced by cohort, and a weekly
triage of the worst production traces into the golden set.

### Edge cases to name (rattle several off — breadth is the signal)

- **Empty / missing context** — nothing was retrieved. Does it say so or invent?
- **Contradictory sources** — two docs disagree. Should surface the conflict.
- **Out of scope** — "what's the weather" to a billing bot.
- **Correct answer is "I don't know"** — the most under-tested category, and the
  one that separates people who've shipped from people who haven't.
- **Prompt injection via retrieved content** — a doc containing "ignore previous
  instructions." Especially important when you ingest user-uploaded or web data.
- **Adversarial / jailbreak** attempts.
- **PII in the input** — does it echo it back, log it?
- **Very long input** — near context limit; watch middle-of-context loss.
- **Ambiguous reference** — "cancel it" with two candidate subscriptions.
- **Numeric and unit traps** — percentages vs basis points, currency, fiscal vs
  calendar year. LLMs are confidently bad here.
- **Temporal staleness** — "what's the current rate" when the doc is from 2023.
- **Near-duplicate distractors** — retrieval returns the *similar but wrong* doc
  (old policy version). Nasty and common.
- **Tone extremes** — furious customer, legal threat.
- **Multilingual / code-switching**, if relevant.
- **Formatting**: emoji, markdown, HTML injection in the input.

---

## 4. Retrieval / Context

> When would you use retrieval or embeddings instead of putting everything in the
> prompt? What risks?

### Say this

- "Default to the simplest thing: **if the corpus fits in context and is stable,
  put it in context and cache it.** RAG is real infrastructure — index, chunking
  strategy, re-embedding jobs, freshness — and you should only pay for it when
  something forces you to."
- "The forcing functions are: **size, churn, permissions, cost, and attribution.**"

### The decision

**Just use context when:** the corpus is small and stable (roughly under
~50–100k tokens), every request needs all of it, and there are no per-user
access rules. Prompt caching makes this cheap and fast — a cached system prompt
costs a fraction of the uncached read and cuts latency substantially.

**Use retrieval when any of these is true:**

- **Size** — the corpus exceeds the window, or would be absurd to send per call
- **Churn** — content updates constantly and you need freshness without rebuilds
- **Permissions** — different users may see different documents; retrieval is
  where you enforce that filter, and it *must* be a hard metadata filter, not a
  hope
- **Cost/latency** — you're sending 100k tokens to answer from 2k of them
- **Attribution** — you need "here's the source" as a product feature, and
  retrieval gives you the citation for free
- **Precision** — a smaller, sharper context often beats a huge one; more
  irrelevant text measurably degrades answers

**And say this, because it's the part people miss:** embeddings alone are a weak
retriever. Production shape is **hybrid — BM25 + vector, fused, then a
cross-encoder reranker over the top ~50 down to ~5**. Pure semantic search fails
badly on exact identifiers, error codes, product SKUs, and names, which is
exactly what users search for.

### Risks to watch

**Retrieval-side:**
- **Silent recall failure** — the retriever misses, the generator answers anyway
  and sounds fine. The single most dangerous RAG failure mode. Mitigation:
  measure recall@k *separately* from answer quality, and abstain below a score
  threshold.
- **Chunking destroys meaning** — splitting a table from its header, a clause
  from its condition. Chunk on document structure, overlap, keep parent context.
- **Stale index** — source updated, index didn't. Needs monitoring, not faith.
- **Near-duplicate versions** — v2 and v3 of a policy both retrievable; the model
  cites the outdated one. Version metadata and recency filters.
- **Embedding model swaps require full re-indexing** — vectors aren't portable
  across models. Budget for it; it bites people mid-project.
- **Multi-hop questions** — single-shot retrieval structurally can't answer
  "how does X compare to Y under condition Z." Needs query decomposition.

**Generation-side:**
- **Lost in the middle** — content in the center of a long context gets ignored.
  Put the highest-ranked chunks at the edges.
- **Indirect prompt injection** — retrieved documents are untrusted input. If a
  doc can contain instructions and your model has tools, you have a real security
  problem, not a quality problem.
- **Cross-tenant leakage** — the worst possible bug in a RAG system, and it's an
  access-control bug that lives in your metadata filter.
- **Fluent citation of nothing** — the model cites a chunk that doesn't support
  the claim. Verify the claim actually appears in the cited span.

---

## 5. Model Comparison

> If two models give different answers for the same task, how would you decide
> which one is better?

### Say this

- "**Different isn't wrong.** First question: is one actually incorrect, or are
  they both acceptable and I don't have a spec? Disagreement often means my task
  definition is underspecified, and that's my bug, not the model's."
- "One disagreement is an anecdote. I decide on a **dataset**, not a duel."
- "And 'better' isn't only quality — it's quality **per dollar per second**
  against the failure cost of the specific product."

### How I'd actually decide

**1. Establish ground truth.** Write down what a correct answer is for this task.
If I can't, that's the finding — and it's usually the real one.

**2. Scale up from one example.** Run both on the full golden set, n=3–5 per case
for variance. Blind pairwise comparison where correctness is subjective, graded
rubric where it isn't. Check whether the gap survives noise before believing it —
a 3-point difference on 50 cases is nothing.

**3. Slice the results.** Aggregate scores hide the useful answer. Usually you
find Model A wins on long-context synthesis and Model B on structured extraction.
That's more valuable than a winner, because it tells you how to route.

**4. Score the non-quality axes** — this is where the decision usually gets made:

| Axis | Why it decides things |
|---|---|
| Cost per 1k requests | At volume, a 3x cost difference outweighs a 2% quality edge |
| p50 / p95 latency | p95 is what users feel |
| Structured output reliability | A model that emits invalid JSON 1% of the time is a 1% outage |
| Tool-calling accuracy | Agentic tasks live or die here |
| Instruction adherence | Does it respect "answer only from context"? |
| Refusal calibration | Over-refusal is as expensive as under-refusal |
| Context window | Hard constraint or not |
| Operational | Rate limits, region availability, deprecation cadence, data retention terms |

**5. Weight by failure cost.** A drafting assistant with a human reviewer should
optimize cost and speed. A system that acts autonomously on financial data should
pay a lot for accuracy. Same benchmark, different winner.

**6. The answer is often "both."** Route: cheap/fast model by default, escalate
to the stronger one on low confidence, high-stakes categories, or disagreement.
Mentioning routing shows you think about production economics, not leaderboards.

**Likely follow-up:** *"What if you have no ground truth at all?"* — Then use
pairwise human preference on a sample, plus proxy signals (does it cite? is it
consistent across reruns? does it hold up under a verification pass?), and be
explicit that it's a preference decision, not a correctness one.

---

## 6. Cost Control

> How would you prevent runaway AI or GPU usage while still allowing useful
> experimentation and testing?

### Say this

- "**Guardrails, not gatekeepers.** If spending requires my approval, I become the
  bottleneck and people stop experimenting. I'd rather give every engineer a
  budget they can burn freely inside, with hard caps that fail closed."
- "The metric I actually manage is **cost per successful task**, not total spend.
  Total spend going up while cost-per-task goes down is a system that's working."

### Controls, in the order I'd add them

**Structural (day one):**
- Separate API keys and separate billing accounts per environment and per team —
  you cannot control what you cannot attribute
- Hard spend caps at the provider level on every dev key, set to fail closed
- Tag every request with feature / environment / user so spend is queryable by
  dimension

**Per-request:**
- `max_tokens` on every call — an unbounded generation loop is the classic
  runaway
- Timeouts, and **retry with backoff plus a retry ceiling** (naive retry loops
  are a top cause of surprise bills)
- Loop/step limits and a token budget on any agentic flow, terminating hard when
  exceeded

**Efficiency (this is where the real money is):**
- **Prompt caching** for stable system prompts and shared context — typically the
  single largest win
- **Model tiering**: small model by default, escalate only when needed
- **Batch APIs** for anything offline — roughly half price for non-urgent work
- **Caching**: exact-match first, semantic cache if the traffic supports it
- Trim retrieved context — rerank down to 5 chunks instead of stuffing 20

**GPU specifically:**
- Auto-shutdown on idle, and TTL tags on every instance so nothing lives forever
  by accident — the classic burn is a notebook GPU left running over a long
  weekend
- Spot/preemptible for training and batch work, on-demand only for serving
- Right-size before scaling out; measure utilization, and treat a 15%-utilized
  A100 as a bug
- Scale-to-zero for dev endpoints

**Visibility:**
- A dashboard everyone can see, broken down by feature and team
- Alerts at 50/80/100% of budget, routed to the team that spent it, plus an
  anomaly alert on sudden rate changes (catches a bad deploy in minutes, not at
  month end)
- Cost per request surfaced in dev tooling so engineers feel it while building

**And protect experimentation explicitly:** a standing per-engineer monthly
budget, no approval needed; a shared experiment pool for bigger runs; sandbox
keys that physically cannot hit production-scale volume. The failure mode I'm
avoiding is a team that stops trying things because spending is politically
expensive — that costs far more than the GPU.

---

## 7. Production Readiness

> What would need to be true before you would let an AI feature be used by real
> customers?

### Say this

- "The bar isn't 'it's accurate enough.' It's **'when it's wrong — and it will
  be — is the damage bounded and recoverable?'** I design for the wrong answer,
  not the right one."

### The checklist

**Quality**
- Eval suite exists, thresholds agreed *in advance*, and it passes — including on
  the worst-performing slice, not just the average
- Tested on realistic traffic, not curated demo inputs
- Red-teamed: injection, jailbreak, PII extraction, abuse
- Failure modes are enumerated and each has a stated mitigation

**Containment — the important part**
- **Scope is narrow and enforced** — the feature can't wander into advice it
  shouldn't give
- **Human in the loop wherever an error is expensive or irreversible.** Anything
  that moves money, sends external communications, or deletes data needs a human
  or a hard confirmation
- Blast radius is bounded: no unbounded tool permissions, no write access it
  doesn't strictly need
- **The system can say "I don't know"** and route to a human, and that path is
  tested

**Safety & compliance**
- Input and output filtering appropriate to the domain
- PII handling: redaction where needed, retention policy defined, provider data
  terms reviewed (training opt-out where required), DPA in place
- **It's disclosed to users that they're interacting with AI** — increasingly a
  legal requirement, and always the right call
- Domain rules honored (financial/medical/legal disclaimers as applicable)

**Operations**
- **Full trace logging** — prompt, retrieved context, tool calls, model version,
  params, output — enough to reproduce any single interaction. Without this you
  cannot debug production, and question 8 becomes unanswerable
- **Feature flag with instant kill switch**, tested, not assumed
- Staged rollout: internal → 1% → 10% → 100%, with rollback criteria written
  before launch
- Alerting on quality proxies (thumbs-down, escalation, retry, refusal rate) and
  on latency and cost, not just 500s
- Rate limits and per-user quotas — abuse and cost protection
- Fallback behavior when the provider is down or slow (degrade gracefully, don't
  hang)
- Model version pinned; a plan for provider deprecations
- A runbook, and someone on call who knows what to do

**Product/UX**
- Citations or sources shown where the user needs to verify
- Uncertainty is visible rather than hidden behind confident phrasing
- An obvious escape hatch to a human
- A feedback mechanism that lands somewhere a person reads

**Business**
- Cost per user modeled at projected volume, and it's sustainable
- Support team briefed on what it does and how it fails
- Success and rollback criteria agreed with stakeholders, in writing

**Strong closing line:** "Not every item is a blocker for every feature — the
weight depends on stakes. An internal draft-generator can ship with far less than
something that talks to customers about their money. What I won't ship without,
regardless: trace logging, a kill switch, and an evaluated failure mode."

---

## 8. Debugging AI Behavior

> If an AI assistant gives a confident but wrong answer, how would you investigate
> and reduce recurrence?

### Say this

- "First: **confidence and correctness are unrelated in these systems.** Fluent
  tone is not a signal of grounding, so 'it sounded sure' isn't a clue — it's the
  default."
- "Second: **most 'model' errors aren't the model.** In my experience the bug is
  upstream — retrieval brought the wrong document, the source data was stale, the
  tool returned something unexpected, or the prompt was ambiguous. I isolate the
  layer before I touch the prompt."

### Investigation

**1. Reproduce from the trace.** Pull the full record: exact input, retrieved
chunks, tool calls and results, model + version + params, raw output. If I can't
reproduce it, my logging is the first bug to fix.

**2. Bisect the pipeline with ablations** — this is the core technique and worth
saying explicitly:

| Test | If it now answers correctly | Conclusion |
|---|---|---|
| Hand it the *correct* source document | Yes | **Retrieval failed** — the generator was fine |
| Hand it the correct doc | No | **Generation/prompt failed** — it had the answer and blew it |
| Check whether the correct doc is in the index at all | Missing | **Ingestion/freshness bug** |
| Re-run the same input 5 times | Sometimes right | **Instability** — prompt is underspecified or temperature too high |
| Re-run on a stronger model | Now right | Capability limit — candidate for routing/escalation |
| Check source-of-truth data | Source is wrong | **The model was faithful to bad data** — fix the data |

**3. Classify the root cause.** Roughly: retrieval miss, stale or wrong source
data, chunking split the answer, ambiguous prompt/spec, tool returned bad output,
genuine model capability limit, or injection. The fix is completely different for
each, which is why classification comes before fixing.

**4. Check whether it's a class, not an instance.** Query production traces for
similar inputs. One user's complaint is usually the visible edge of a slice
that's failing quietly.

### Reducing recurrence

**Always, every time:** the failing case goes into the golden set, plus 3–5
variants of it. That's non-negotiable — it's how a bug becomes permanently fixed
instead of temporarily fixed. Say this out loud; it's the answer they're
listening for.

**Then fix at the right layer, cheapest first:**

1. **Data** — correct the source, fix freshness. Free and permanent.
2. **Retrieval** — better chunking, hybrid search, reranking, recency filters,
   dedupe stale versions.
3. **Prompt** — make grounding explicit ("answer only from provided context; if
   it isn't there, say so"), require citations, add the failure case as a
   few-shot example.
4. **Verification** — a second pass checking the answer against the retrieved
   context; or constrained/structured output so it can't free-associate.
5. **Model** — route this category to a stronger model. Costs money, so it's not
   first.
6. **Fine-tuning** — last, and only with real volume and a stable target.

**Structural fixes that reduce the whole class of confident-wrong:**

- **Abstention threshold** — if retrieval confidence is low, refuse instead of
  answering. Directly attacks confident-wrong.
- **Mandatory citations, verified** — check the cited span actually supports the
  claim.
- **UX that surfaces uncertainty** — sources visible, hedging preserved rather
  than polished away, easy path to a human.
- **Monitoring on the specific slice** so you see the regression next time before
  a customer does.

**Close with the honest bit:** "I can't drive this to zero — some rate of
confident errors is inherent to the technology today. So alongside fixing
individual causes, I design the product so a wrong answer is *cheap*: the user
can verify it, the system can't act irreversibly on it, and there's a fast path
to a human."

---

## Questions to ask them

Having these ready matters more than people think — they signal what you'd be
like on the team.

- What does your current eval setup look like? Is there a golden set, or is
  quality assessed by review?
- What's the failure cost of a wrong answer in this product? Who's harmed?
- Is there a human in the loop today, and is the plan to remove them?
- How do you handle prompt changes — are they versioned and tested, or edited in
  a dashboard?
- What's the split between building new AI features and hardening the ones
  already shipped?
- Where does the AI budget sit, and does an engineer need approval to run
  experiments?
