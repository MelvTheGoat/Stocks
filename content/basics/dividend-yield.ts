import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "dividend-yield",
  title: "Dividend yield",
  question: "What is dividend yield and is a high yield a good sign?",
  short:
    "Dividend yield is the dividend paid over a year divided by the share price, expressed as a percentage. A share costing one hundred naira that paid eight naira in dividends has a yield of eight per cent. It describes what the company paid in the past against what the share costs today, and it carries no promise about what will be paid next.",
  body: [
    "Dividends are declared at the company's discretion, usually recommended by the board and approved by shareholders at the annual general meeting. They are not obligations. A company that has paid a dividend every year for a decade can pay nothing next year without breaching anything, and companies under pressure frequently do exactly that.",
    "The yield moves whenever the price moves, even if the dividend never changes. A share that halves in price doubles its yield. This is why unusually high yields cluster around companies whose share prices have recently fallen a long way: the yield is high because the price is low, and the price is low because other holders expect the dividend to be cut.",
    "To pay a dividend a company needs both distributable reserves and cash. These are different tests and a company can pass one and fail the other. A company borrowing to maintain a dividend it cannot fund from operations is visible in the cash flow statement, where dividends paid exceed cash generated from operations.",
    "Two dates matter for receiving a payment. The qualification date, after which a buyer does not receive the declared dividend, and the payment date, when the money actually arrives. Buying a share the day before payment does not entitle you to that dividend.",
  ],
  nigerianContext:
    "Dividends from Nigerian companies are subject to withholding tax deducted before the money reaches you, so the cash received is less than the declared amount. The rate is set in tax legislation and has changed before, so the current rate should be checked against the Federal Inland Revenue Service rather than assumed. Unclaimed dividends are a long-standing issue on the NGX, with substantial sums sitting undelivered because holders' bank and CSCS records were never updated; registrars publish unclaimed dividend lists, and an e-dividend mandate is how a holder ensures payment arrives.",
  commonMisreading:
    "Treating a high yield as income you can count on. The yield is calculated from a dividend already paid. It is a historical fact presented as a rate, and the rate quietly assumes a repeat that nobody has committed to.",
  seeAlso: ["pe-ratio", "the-three-financial-statements", "what-a-share-is"],
  lastReviewed: "2026-09-18",
};
