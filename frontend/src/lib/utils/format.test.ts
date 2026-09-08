import { describe, expect, it } from "vitest";

import {
  displayDomain,
  EM_DASH,
  formatCompactNumber,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatScore,
  initials,
  truncate,
  userDisplayName,
} from "@/lib/utils/format";

describe("nullable formatting", () => {
  /**
   * Most metric fields on the API are nullable until the backend has measured
   * them, so every formatter has to render "not measured" rather than "0" —
   * which would read as a real, bad value.
   */
  it("renders an em dash rather than zero for a missing value", () => {
    expect(formatNumber(null)).toBe(EM_DASH);
    expect(formatCompactNumber(undefined)).toBe(EM_DASH);
    expect(formatScore(null)).toBe(EM_DASH);
    expect(formatPercent(null)).toBe(EM_DASH);
    expect(formatCurrency(null)).toBe(EM_DASH);
    expect(formatCurrency("")).toBe(EM_DASH);
    expect(displayDomain(null)).toBe(EM_DASH);
    expect(truncate(null)).toBe(EM_DASH);
  });

  it("still renders a genuine zero", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatScore(0)).toBe("0");
  });
});

describe("formatScore", () => {
  it("rounds to a whole number", () => {
    expect(formatScore(86.4)).toBe("86");
    expect(formatScore(86.5)).toBe("87");
  });
});

describe("formatCompactNumber", () => {
  it("compacts large traffic figures", () => {
    expect(formatCompactNumber(12_500)).toBe("12.5K");
    expect(formatCompactNumber(950)).toBe("950");
  });
});

describe("formatCurrency", () => {
  it("parses the decimal strings the API sends for money", () => {
    expect(formatCurrency("1234.50")).toContain("1,234.50");
  });

  it("returns an em dash for an unparseable amount", () => {
    expect(formatCurrency("not-a-number")).toBe(EM_DASH);
  });
});

describe("displayDomain", () => {
  it("strips the scheme and any trailing slash", () => {
    expect(displayDomain("https://example.com/")).toBe("example.com");
    expect(displayDomain("http://sub.example.co.uk/path")).toBe("sub.example.co.uk/path");
    expect(displayDomain("example.com")).toBe("example.com");
  });
});

describe("initials", () => {
  it("uses the first and last name parts", () => {
    expect(initials("Sam Okafor")).toBe("SO");
    expect(initials("Sam")).toBe("S");
  });

  it("falls back to the email's local part, ignoring the domain", () => {
    expect(initials(null, "priya.sharma@example.com")).toBe("PS");
    expect(initials(null, "sam@example.com")).toBe("S");
  });

  it("never returns an empty string", () => {
    expect(initials(null, null)).toBe("?");
    expect(initials("   ")).toBe("?");
  });
});

describe("userDisplayName", () => {
  it("prefers full_name, then the name parts, then the email", () => {
    expect(userDisplayName({ full_name: "Sam Okafor", email: "s@e.com" })).toBe("Sam Okafor");
    expect(
      userDisplayName({ first_name: "Sam", last_name: "Okafor", email: "s@e.com" }),
    ).toBe("Sam Okafor");
    expect(userDisplayName({ email: "s@e.com" })).toBe("s@e.com");
    expect(userDisplayName(null)).toBe(EM_DASH);
  });
});

describe("truncate", () => {
  it("adds an ellipsis only when it actually truncates", () => {
    expect(truncate("short", 10)).toBe("short");
    expect(truncate("abcdefghij", 5)).toBe("abcd…");
  });
});
