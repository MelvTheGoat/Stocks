/**
 * Money formatting for NGX figures.
 *
 * Nigerian filings quote in naira, but oil and gas issuers often report in
 * dollars, and some report both. Every formatter here takes the currency
 * explicitly so a figure can never be rendered in the wrong unit by default.
 */

export type Currency = "NGN" | "USD";

const SYMBOL: Record<Currency, string> = {
  NGN: "₦",
  USD: "$",
};

/**
 * Scale thresholds, largest first. NGX market caps run into trillions of
 * naira, so trn has to be here or every large cap renders as a wall of digits.
 */
const SCALES = [
  { limit: 1e12, suffix: "trn" },
  { limit: 1e9, suffix: "bn" },
  { limit: 1e6, suffix: "m" },
  { limit: 1e3, suffix: "k" },
] as const;

/**
 * Significant digits shown in abbreviated form. Two decimals on a trillion is
 * false precision; the expanded figure is available in Tier 2 for anyone who
 * needs the exact number.
 */
function abbreviateDigits(scaled: number): string {
  if (scaled >= 100) return scaled.toFixed(0);
  if (scaled >= 10) return scaled.toFixed(1);
  return scaled.toFixed(2);
}

/** Strips a trailing ".0" / ".00" so 5.00bn reads as 5bn. */
function trimZeros(s: string): string {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/**
 * Compact form for prose and headline numbers: ₦1.2trn, $19bn, ₦450m.
 */
export function formatMoney(amount: number, currency: Currency): string {
  if (!Number.isFinite(amount)) {
    throw new RangeError(`cannot format non-finite amount: ${amount}`);
  }

  const symbol = SYMBOL[currency];
  const sign = amount < 0 ? "-" : "";
  const magnitude = Math.abs(amount);

  for (const { limit, suffix } of SCALES) {
    if (magnitude >= limit) {
      const digits = trimZeros(abbreviateDigits(magnitude / limit));
      return `${sign}${symbol}${digits}${suffix}`;
    }
  }

  return `${sign}${symbol}${trimZeros(magnitude.toFixed(2))}`;
}

/**
 * Full form for tables, where columns are compared against each other and
 * rounding to two significant digits would hide real differences.
 */
export function formatMoneyExact(amount: number, currency: Currency): string {
  if (!Number.isFinite(amount)) {
    throw new RangeError(`cannot format non-finite amount: ${amount}`);
  }

  const symbol = SYMBOL[currency];
  const sign = amount < 0 ? "-" : "";
  const body = Math.abs(amount).toLocaleString("en-NG", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });

  return `${sign}${symbol}${body}`;
}

/**
 * Share prices are quoted in kobo precision and are small enough that
 * abbreviating them would be actively wrong.
 */
export function formatSharePrice(amount: number, currency: Currency): string {
  if (!Number.isFinite(amount)) {
    throw new RangeError(`cannot format non-finite amount: ${amount}`);
  }

  return `${SYMBOL[currency]}${amount.toFixed(2)}`;
}

export function formatPercent(value: number, decimals = 1): string {
  if (!Number.isFinite(value)) {
    throw new RangeError(`cannot format non-finite percentage: ${value}`);
  }

  return `${value.toFixed(decimals)}%`;
}

/**
 * Multiples such as P/E and EV/EBITDA. Rendered with an explicit x so a bare
 * number is never mistaken for a price.
 */
export function formatMultiple(value: number): string {
  if (!Number.isFinite(value)) {
    throw new RangeError(`cannot format non-finite multiple: ${value}`);
  }

  return `${value.toFixed(1)}x`;
}

/** Share and barrel counts: no currency symbol, grouped for readability. */
export function formatCount(value: number): string {
  if (!Number.isFinite(value)) {
    throw new RangeError(`cannot format non-finite count: ${value}`);
  }

  const sign = value < 0 ? "-" : "";
  const magnitude = Math.abs(value);

  for (const { limit, suffix } of SCALES) {
    if (suffix === "k") break;
    if (magnitude >= limit) {
      return `${sign}${trimZeros(abbreviateDigits(magnitude / limit))}${suffix}`;
    }
  }

  return value.toLocaleString("en-NG");
}
