import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "pe-ratio",
  title: "Price-to-earnings ratio",
  question: "What is a P/E ratio and what does a high or low one mean?",
  short:
    "The price-to-earnings ratio divides the share price by the company's earnings per share. If a share costs sixty naira and the company earned six naira per share last year, the P/E is ten: you are paying ten naira for each naira of annual profit. It is a measure of what the market is willing to pay for earnings, not a measure of whether that price is right.",
  body: [
    "A high P/E means the market expects earnings to grow. A low P/E means it does not, or that it doubts the earnings will repeat. Neither reading is inherently good or bad, and the ratio cannot tell you which of the two situations you are looking at. That requires reading the business.",
    "The ratio breaks in specific, common circumstances. A company with no profit has no P/E at all, because you cannot divide by zero or by a loss. A company with an unusually good year has a temporarily flattering P/E, and the ratio climbs back once earnings return to their normal level. A company that sold a subsidiary books a one-off gain that inflates earnings and deflates the ratio, with nothing about its ordinary trading having changed.",
    "Trailing P/E uses the last reported twelve months of earnings, which are known. Forward P/E uses a forecast, which is not. When a source quotes a P/E without saying which it is, it is usually trailing, but the two can differ enormously for a company in the middle of a change.",
    "Comparisons only mean anything within an industry. Banks, cement producers and telecoms operators carry structurally different ratios for structural reasons, and a cross-industry P/E comparison mostly measures the difference between the industries.",
  ],
  nigerianContext:
    "Nigerian earnings figures are reported in naira and are not adjusted for inflation. During a period of high inflation, revenue and profit can rise in naira terms while the company sells the same volume of goods, which pushes reported earnings up and the P/E down without any improvement in the underlying business. Companies with dollar-denominated debt also book large foreign exchange losses when the naira moves, which can turn a profitable year into a reported loss and remove the ratio entirely.",
  commonMisreading:
    "Reading a low P/E as a bargain. A low ratio very often means the market has concluded that last year's earnings will not repeat, and the market is sometimes right. The ratio records an opinion about the future; it does not verify it.",
  seeAlso: ["the-three-financial-statements", "market-cap", "dividend-yield"],
  lastReviewed: "2026-09-18",
};
