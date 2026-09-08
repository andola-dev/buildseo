import { describe, expect, it } from "vitest";

import { scoreTone, statusVariant } from "@/config/status";
import {
  CAMPAIGN_STATUSES,
  PUBLISHER_STATUSES,
  SUBMISSION_STATUSES,
} from "@/config/enums";

describe("statusVariant", () => {
  it("uses one consistent tone per status family", () => {
    expect(statusVariant("ACTIVE")).toBe("success");
    expect(statusVariant("VERIFIED")).toBe("success");
    expect(statusVariant("QUALIFIED")).toBe("success");

    expect(statusVariant("PENDING_APPROVAL")).toBe("warning");
    expect(statusVariant("PAUSED")).toBe("warning");

    expect(statusVariant("FAILED")).toBe("danger");
    expect(statusVariant("REJECTED")).toBe("danger");

    expect(statusVariant("DRAFT")).toBe("muted");
    expect(statusVariant("ARCHIVED")).toBe("muted");
  });

  it("assigns a tone to every status the API can return", () => {
    for (const status of [
      ...CAMPAIGN_STATUSES,
      ...PUBLISHER_STATUSES,
      ...SUBMISSION_STATUSES,
    ]) {
      // "outline" is the unrecognised fallback; no known status should hit it.
      expect(statusVariant(status), status).not.toBe("outline");
    }
  });

  it("falls back safely for an unknown or missing status", () => {
    expect(statusVariant("SOMETHING_NEW")).toBe("outline");
    expect(statusVariant(null)).toBe("muted");
    expect(statusVariant(undefined)).toBe("muted");
  });
});

describe("scoreTone", () => {
  it("treats a high score as good for quality, relevance and authority", () => {
    for (const kind of ["quality", "relevance", "authority", "opportunity"] as const) {
      expect(scoreTone(kind, 85)).toBe("success");
      expect(scoreTone(kind, 55)).toBe("warning");
      expect(scoreTone(kind, 10)).toBe("danger");
    }
  });

  it("inverts the bands for spam, where a high score is bad", () => {
    expect(scoreTone("spam", 5)).toBe("success");
    expect(scoreTone("spam", 35)).toBe("warning");
    expect(scoreTone("spam", 80)).toBe("danger");
  });

  it("returns a neutral tone for an unmeasured score", () => {
    expect(scoreTone("quality", null)).toBe("muted");
    expect(scoreTone("quality", undefined)).toBe("muted");
    expect(scoreTone("spam", Number.NaN)).toBe("muted");
  });

  it("puts the band boundaries where the thresholds say", () => {
    expect(scoreTone("quality", 70)).toBe("success");
    expect(scoreTone("quality", 69)).toBe("warning");
    expect(scoreTone("quality", 40)).toBe("warning");
    expect(scoreTone("quality", 39)).toBe("danger");
    expect(scoreTone("spam", 20)).toBe("success");
    expect(scoreTone("spam", 21)).toBe("warning");
  });
});
