import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "free-float",
  title: "Free float",
  question: "What is free float and why does it matter to me as a small buyer?",
  short:
    "Free float is the portion of a company's shares actually available to trade in the market, once you exclude the blocks held by founders, parent companies, governments and other long-term holders who are not selling. A company can be enormous and still have very few shares genuinely in circulation.",
  body: [
    "A low free float has two consequences that matter to someone buying small amounts. The price moves more on less trading, because a modest order is large relative to the shares available. And selling can be harder than buying: when few shares change hands on an ordinary day, converting a holding back into cash may mean accepting a lower price or waiting.",
    "Free float also determines how much influence outside shareholders have. Where a single holder controls most of the shares, the outcome of any vote at a general meeting is settled before it is held, and the protections that come with being a shareholder are formal rather than practical.",
    "Index inclusion usually depends on free float rather than total market cap, because an index fund can only buy shares that are available. This is why a very large company with a small float may carry less index weight than a smaller company with most of its shares in circulation.",
    "Free float is not fixed. It rises when a major holder sells down or the company issues new shares to the public, and falls when a major holder buys more or the company buys back its own shares.",
  ],
  nigerianContext:
    "The Nigerian Exchange sets minimum free float requirements for its listing boards and publishes the companies that fall below them, so whether a given company is compliant is a matter of public record on the NGX website rather than something to infer. Several of the largest companies on the exchange have majority holders — founding families, foreign parent companies, or the federal government — holding well above half the issued shares, which is why the daily traded volume of a large NGX company can be small relative to its market capitalisation.",
  commonMisreading:
    "Assuming that a large market cap means a share is easy to buy and sell. Size and liquidity are separate properties. The figure to check before buying is how many shares actually trade on an ordinary day, not how much the whole company is said to be worth.",
  seeAlso: ["market-cap", "ipo", "what-a-share-is"],
  lastReviewed: "2026-09-18",
};
