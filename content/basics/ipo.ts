import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "ipo",
  title: "What an IPO is",
  question: "What happens in an IPO and how is it different from buying on the market?",
  short:
    "An initial public offering is the first time a company sells its shares to the public and lists them on an exchange. Before an IPO the shares are held privately and cannot easily be bought or sold. After it, they trade daily at whatever price buyers and sellers agree, which may be above or below the price paid at the offer.",
  body: [
    "In an IPO you buy from the company or from its existing owners at a fixed offer price, through an application rather than a live market. Everyone applying in the same category pays the same price on the same day. From the moment trading opens, that fixed price is gone and the share is worth whatever the market says at that moment.",
    "Two different things can be happening in an IPO, and the prospectus says which. In a primary offer the company issues new shares and the money raised goes to the company. In a secondary offer existing shareholders sell shares they already own, and the money goes to them. The use of proceeds section is where this is spelled out.",
    "Applications are not guaranteed to be filled. If an offer attracts more demand than there are shares, it is scaled back and you receive fewer shares than you applied for, with the balance returned. The basis of allotment, published after the offer closes, sets out how that was decided.",
    "Companies choose when to go public, and they generally choose a moment when their recent results and market conditions show them at their best. That is not improper, but it does mean the financial history in a prospectus has been presented at a time of the company's own selection.",
  ],
  nigerianContext:
    "Nigerian public offers are registered with the Securities and Exchange Commission and applications are made through registered receiving agents, with the receiving banks named in the prospectus. Allotment results and refunds for unfilled applications are handled by the registrar, also named in the prospectus. Where a listing happens by introduction rather than by offer, no new shares are sold at all: the company simply lists existing shares on the exchange, and there is no offer price and no application to make.",
  commonMisreading:
    "Expecting the price to rise when trading opens. IPOs list below their offer price often enough that it has its own name in the market, and the offer price is a negotiated figure rather than a floor the shares are held to.",
  seeAlso: ["prospectus", "book-building", "greenshoe", "free-float"],
  lastReviewed: "2026-09-18",
};
