import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "greenshoe",
  title: "Greenshoe option",
  question: "What is a greenshoe or over-allotment option in an offer?",
  short:
    "A greenshoe option, also called an over-allotment option, lets the institution running an offer sell more shares than originally advertised if demand is strong. It is a stabilisation mechanism: it gives the stabilising agent a way to support the share price in the first days of trading without taking on unlimited risk.",
  body: [
    "The mechanics are less strange than the name. The stabilising agent sells more shares than exist in the offer, leaving it short. If the price falls after listing, it buys shares in the market to cover that short, and those purchases support the price. If the price rises, buying in the market would be expensive, so it exercises the greenshoe instead and takes the extra shares from the company at the offer price.",
    "Either way the agent closes its position. The difference is who supplies the shares: the market when the price is weak, the company when the price is strong. This is why the mechanism supports the price on the downside without the agent gambling on the outcome.",
    "The option is limited in size and in time. The prospectus states the maximum number of additional shares and the window during which the option may be exercised, typically measured in weeks from listing rather than months.",
    "Price support during that window is deliberate and disclosed. It is worth knowing that early trading in an offer with an active greenshoe may not reflect ordinary supply and demand, and that the support ends when the window does.",
  ],
  nigerianContext:
    "Where a Nigerian offer includes an over-allotment option, its size and exercise period are disclosed in the prospectus registered with the Securities and Exchange Commission, along with the identity of the stabilising agent. The mechanism appears mainly in larger institutional offers rather than in small listings.",
  commonMisreading:
    "Reading a steady price in the first weeks after listing as evidence that the market has settled on a value. Where a greenshoe is active, that steadiness may be the stabilising agent doing its job, and the honest test of the price comes after the option expires.",
  seeAlso: ["ipo", "book-building", "prospectus"],
  lastReviewed: "2026-09-18",
};
