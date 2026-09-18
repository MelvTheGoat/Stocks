import { describe, expect, it } from "vitest";
import {
  formatCount,
  formatMoney,
  formatMoneyExact,
  formatMultiple,
  formatPercent,
  formatSharePrice,
} from "@/lib/format/naira";

describe("formatMoney", () => {
  it("abbreviates NGX-scale figures", () => {
    expect(formatMoney(1_200_000_000_000, "NGN")).toBe("₦1.2trn");
    expect(formatMoney(450_000_000_000, "NGN")).toBe("₦450bn");
    expect(formatMoney(3_400_000, "NGN")).toBe("₦3.4m");
  });

  it("formats dollar figures with the dollar symbol", () => {
    expect(formatMoney(19_000_000_000, "USD")).toBe("$19bn");
  });

  it("drops trailing zeros rather than showing false precision", () => {
    expect(formatMoney(5_000_000_000, "NGN")).toBe("₦5bn");
    expect(formatMoney(5_100_000_000, "NGN")).toBe("₦5.1bn");
  });

  it("widens precision as the leading digits shrink", () => {
    expect(formatMoney(1_234_000_000_000, "NGN")).toBe("₦1.23trn");
    expect(formatMoney(12_340_000_000_000, "NGN")).toBe("₦12.3trn");
    expect(formatMoney(123_400_000_000_000, "NGN")).toBe("₦123trn");
  });

  it("keeps the sign on losses", () => {
    expect(formatMoney(-95_000_000_000, "NGN")).toBe("-₦95bn");
  });

  it("leaves sub-thousand figures unabbreviated", () => {
    expect(formatMoney(940, "NGN")).toBe("₦940");
  });

  it("rejects figures that are not real numbers", () => {
    expect(() => formatMoney(Number.NaN, "NGN")).toThrow(RangeError);
    expect(() => formatMoney(Number.POSITIVE_INFINITY, "NGN")).toThrow(RangeError);
  });
});

describe("formatMoneyExact", () => {
  it("groups the full figure for table columns", () => {
    expect(formatMoneyExact(1_234_567_890, "NGN")).toBe("₦1,234,567,890");
  });

  it("keeps the sign on negatives", () => {
    expect(formatMoneyExact(-2_500, "USD")).toBe("-$2,500");
  });
});

describe("formatSharePrice", () => {
  it("holds kobo precision instead of abbreviating", () => {
    expect(formatSharePrice(42.5, "NGN")).toBe("₦42.50");
    expect(formatSharePrice(1250, "NGN")).toBe("₦1250.00");
  });
});

describe("formatPercent and formatMultiple", () => {
  it("renders percentages to one decimal by default", () => {
    expect(formatPercent(12.34)).toBe("12.3%");
    expect(formatPercent(12.34, 2)).toBe("12.34%");
  });

  it("marks multiples with an explicit x", () => {
    expect(formatMultiple(8.42)).toBe("8.4x");
  });
});

describe("formatCount", () => {
  it("abbreviates share counts above a million", () => {
    expect(formatCount(17_040_000_000)).toBe("17bn");
    expect(formatCount(3_500_000)).toBe("3.5m");
  });

  it("groups smaller counts in full", () => {
    expect(formatCount(650_000)).toBe("650,000");
  });

  it("keeps the sign on negatives", () => {
    expect(formatCount(-2_500_000)).toBe("-2.5m");
  });
});
