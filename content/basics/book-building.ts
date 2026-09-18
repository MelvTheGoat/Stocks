import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "book-building",
  title: "Book building",
  question: "What does book building mean in an offer?",
  short:
    "Book building is how the price of an offer gets decided. Instead of fixing a price in advance, the issuing house invites institutional investors to say how many shares they would take and at what price. Those bids build a book of demand, and the final offer price is set from what that book shows.",
  body: [
    "The alternative is a fixed price offer, where the company names a price up front and investors take it or leave it. Book building exists because a fixed price set weeks before the offer is a guess, and a wrong guess either leaves the company short of money or leaves the offer undersubscribed.",
    "The offer usually opens with a price range rather than a single number. The book runs for a set period, bids accumulate, and the final price is struck within that range, sometimes at the top, sometimes below it. A price struck at the bottom of the range is itself information about the demand the book attracted.",
    "Retail applicants are generally not part of the book. They apply at the price the book produced, or within the range at a price they specify, depending on how the offer is structured. The institutional bidding that set the price happened before, and its details are not usually published in full.",
    "Allocation in a book built offer is discretionary. The issuer and its advisers decide which bids to fill, and they may favour investors expected to hold rather than sell immediately. Being willing to pay the price does not entitle a bidder to shares.",
  ],
  nigerianContext:
    "Book building is permitted under Securities and Exchange Commission rules for Nigerian public offers, and where it is used the prospectus sets out the price range, the bidding period and the basis on which the final price will be determined. The Commission's rules govern how the process runs, and the prospectus is where an individual investor finds which method their particular offer is using.",
  commonMisreading:
    "Assuming that bidding at the top of the range secures an allocation. The book is a demand-gathering exercise with discretionary allocation, not an auction where the highest bidders are automatically filled.",
  seeAlso: ["ipo", "prospectus", "greenshoe"],
  lastReviewed: "2026-09-18",
};
