import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "market-cap",
  title: "Market capitalisation",
  question: "What does market cap mean and why is it not the price?",
  short:
    "Market capitalisation is the share price multiplied by the number of shares in issue. It is what the market currently says the whole company is worth. A company whose shares cost fifty naira is not cheaper than one whose shares cost five thousand naira, because the two companies have issued different numbers of shares.",
  body: [
    "The price of a single share on its own tells you nothing about size or value. A company can turn a five-thousand-naira share into ten five-hundred-naira shares overnight through a stock split, and nothing about the business has changed. Market cap is the number that survives that operation unchanged.",
    "Market cap is a market opinion, not a measured fact. It is the price that the most recent buyers and sellers happened to agree on, multiplied across every share in issue, including the vast majority that were not part of that trade. In a thinly traded stock, a small number of shares changing hands can move the stated value of the entire company.",
    "Market cap is also not what it would cost to buy the company. An acquirer has to persuade holders to sell, which usually means paying above the market price, and takes on the company's debt as well. The figure that adjusts for both is enterprise value.",
    "Companies are commonly grouped as large, mid and small cap. These are conventions, not definitions, and the naira thresholds shift with inflation and with the index provider doing the grouping.",
  ],
  nigerianContext:
    "The Nigerian Exchange publishes market capitalisation for individual companies and for the market as a whole, but the headline all-share figure counts every listed share, including those held by a parent company or the government and never traded. For several of the largest NGX companies, the shares actually available to buy are a small fraction of the market cap, so the headline figure overstates how much of that company the public can own.",
  commonMisreading:
    "Comparing two companies by share price. A five-naira share is not cheap and a two-thousand-naira share is not expensive. Until you know how many shares exist, the price of one of them is a number without a denominator.",
  seeAlso: ["free-float", "pe-ratio", "what-a-share-is"],
  lastReviewed: "2026-09-18",
};
