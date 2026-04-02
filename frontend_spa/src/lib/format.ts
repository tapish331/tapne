export function formatDateLabel(value: unknown): string {
  const date = asDate(value);
  if (!date) {
    return "Dates announced soon";
  }
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateRange(startValue: unknown, endValue: unknown): string {
  const start = asDate(startValue);
  const end = asDate(endValue);
  if (!start && !end) {
    return "Dates announced soon";
  }
  if (start && end) {
    return `${start.toLocaleDateString("en-IN", { day: "numeric", month: "short" })} – ${end.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
  }
  return formatDateLabel(start ?? end);
}

export function formatCurrency(value: unknown, currency = "INR"): string {
  const amount = toNumber(value);
  if (amount === null) {
    return "Price on request";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export function splitDelimitedText(value: string): string[] {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinDelimitedText(values: unknown): string {
  if (!Array.isArray(values)) {
    return "";
  }
  return values.map((value) => String(value ?? "").trim()).filter(Boolean).join("\n");
}

function asDate(value: unknown): Date | null {
  if (!value) {
    return null;
  }
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
