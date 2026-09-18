import type { Explainer } from "@/schema/basics";

export const explainer: Explainer = {
  slug: "the-three-financial-statements",
  title: "The three financial statements",
  question: "What do the three financial statements actually tell me?",
  short:
    "Every set of company accounts contains three statements, and each answers a different question. The income statement asks whether the company made a profit over a period. The balance sheet asks what it owns and owes on one particular day. The cash flow statement asks how much money actually moved. A company can look healthy on one and be in trouble on another, which is why all three exist.",
  body: [
    "The income statement, sometimes called the profit and loss account, covers a stretch of time: a quarter, a half year, a year. It starts with revenue, subtracts the costs of producing what was sold, subtracts overheads, interest and tax, and ends with profit after tax. It is a record of performance over a period, not a snapshot.",
    "The balance sheet is a snapshot of a single day, usually the last day of the reporting period. It lists assets on one side, liabilities on the other, and the difference between them is equity: what would in principle belong to shareholders. It tells you nothing about the days either side of it, which is why a company can dress a balance sheet date without technically lying.",
    "The cash flow statement tracks money in and money out, split three ways: cash from operations, cash spent on or raised from investments, and cash raised from or repaid to lenders and shareholders. Profit is an accounting judgement. Cash is not, which makes this statement the hardest of the three to flatter.",
    "The three connect. Profit from the income statement adds to equity on the balance sheet. Cash from the cash flow statement changes the cash line on the balance sheet. When a company reports rising profits while operating cash flow falls, the gap between those two statements is where the question lives.",
  ],
  nigerianContext:
    "Companies listed on the Nigerian Exchange report under IFRS and file audited annual accounts plus unaudited quarterly results. The audited annual report is the stronger document: quarterly figures are not audited, and restatements between a quarterly release and the eventual audited annual figure are common enough that any figure taken from a quarterly result should be read as provisional.",
  commonMisreading:
    "Treating profit and cash as the same thing. A company records revenue when it makes a sale, not when it is paid. A Nigerian company selling on ninety-day credit terms during a period of high inflation can report a real accounting profit while its bank balance falls every month. The cash flow statement is where that shows up.",
  seeAlso: ["pe-ratio", "what-a-share-is", "prospectus"],
  lastReviewed: "2026-09-18",
};
