import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "what-a-share-is",
  title: "What a share is",
  question: "What am I actually buying when I buy a share?",
  short:
    "A share is a slice of ownership in a company. If a company has issued one billion shares and you own a thousand of them, you own a millionth of that company: a millionth of what it earns, and a millionth of what is left if it is ever wound up and its debts are paid.",
  body: [
    "Owning a share does not give you a claim on the company's buildings, refineries or cash. It gives you a claim on the company as a whole, which is a different and weaker thing. You cannot turn up at a factory and ask for your millionth of it.",
    "What ownership does give you is two specific rights. The first is a share of profits the company chooses to pay out, called a dividend. The second is a vote at the annual general meeting, usually one vote per share, which in practice matters only if you own a great many shares or vote alongside people who do.",
    "Shareholders are last in line. Employees are paid, suppliers are paid, lenders are paid, and whatever remains belongs to shareholders. In a good year that residual is large. In a bad year it is nothing, and in a liquidation it is very often nothing at all.",
    "The price of a share moves for two reasons that are easy to confuse: because the company's prospects have changed, or because other buyers and sellers have changed their minds. Nothing about owning a share entitles you to a higher price later.",
  ],
  nigerianContext:
    "Shares on the Nigerian Exchange are held electronically through the Central Securities Clearing System, and you buy them through a stockbroker licensed by the Securities and Exchange Commission. Your ownership is recorded in a CSCS account tied to your name, not held by the broker on your behalf, which is why the CSCS statement rather than the broker's app is the authoritative record of what you own.",
  commonMisreading:
    "That a share price falling below what you paid is a temporary condition that will correct itself. There is no mechanism that returns a share to its old price. A company whose earnings have permanently fallen is worth permanently less, and the earlier price is not a level the market owes you.",
  seeAlso: ["market-cap", "dividend-yield", "the-three-financial-statements"],
  lastReviewed: "2026-09-18",
};
