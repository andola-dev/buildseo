import { describe, expect, it } from "vitest";

import {
  AI_PROVIDERS,
  CAMPAIGN_STATUSES,
  CLIENT_WEBSITE_STATUSES,
  DISCOVERY_RUN_STATUSES,
  IN_FLIGHT_STATUSES,
  isTerminalRunStatus,
  JOB_STATUSES,
  MVP_PRICING_TYPE,
  OPPORTUNITY_TYPES,
  PUBLISHER_STATUSES,
  SUBMISSION_STATUSES,
} from "@/config/enums";
import {
  CAMPAIGN_STATUS_LABELS,
  humanizeEnum,
  labelFor,
  OPPORTUNITY_STATUS_LABELS,
  PUBLISHER_STATUS_LABELS,
  SUBMISSION_STATUS_LABELS,
} from "@/config/labels";

describe("enum coverage", () => {
  /**
   * `allOf` already enforces exhaustiveness at compile time. These assertions
   * guard the runtime shape — a mis-sorted or duplicated entry.
   */
  it("has no duplicates", () => {
    const lists = [
      CAMPAIGN_STATUSES,
      CLIENT_WEBSITE_STATUSES,
      PUBLISHER_STATUSES,
      SUBMISSION_STATUSES,
      OPPORTUNITY_TYPES,
      AI_PROVIDERS,
    ];

    for (const list of lists) {
      expect(new Set(list).size).toBe(list.length);
    }
  });

  it("labels every value of every status enum shown in the UI", () => {
    for (const status of CAMPAIGN_STATUSES) {
      expect(CAMPAIGN_STATUS_LABELS[status]).toBeTruthy();
    }
    for (const status of PUBLISHER_STATUSES) {
      expect(PUBLISHER_STATUS_LABELS[status]).toBeTruthy();
    }
    for (const status of SUBMISSION_STATUSES) {
      expect(SUBMISSION_STATUS_LABELS[status]).toBeTruthy();
    }
  });

  it("offers only free listing types, matching the MVP scope", () => {
    expect(MVP_PRICING_TYPE).toBe("FREE");
    for (const type of OPPORTUNITY_TYPES) {
      expect(type.startsWith("FREE_")).toBe(true);
    }
  });

  it("labels every opportunity status", () => {
    for (const status of ["DISCOVERED", "QUALIFIED", "PUBLISHED"] as const) {
      expect(OPPORTUNITY_STATUS_LABELS[status]).toBeTruthy();
    }
  });
});

describe("job and discovery run statuses", () => {
  it("treats only PENDING and RUNNING as in flight", () => {
    expect(IN_FLIGHT_STATUSES).toEqual(["PENDING", "RUNNING"]);

    expect(isTerminalRunStatus("PENDING")).toBe(false);
    expect(isTerminalRunStatus("RUNNING")).toBe(false);
    expect(isTerminalRunStatus("COMPLETED")).toBe(true);
    expect(isTerminalRunStatus("FAILED")).toBe(true);
    expect(isTerminalRunStatus("CANCELLED")).toBe(true);
  });

  it("mirrors the backend's status sets", () => {
    expect([...DISCOVERY_RUN_STATUSES]).toEqual([
      "PENDING",
      "RUNNING",
      "COMPLETED",
      "FAILED",
    ]);
    expect([...JOB_STATUSES]).toEqual([
      "PENDING",
      "RUNNING",
      "SUCCEEDED",
      "FAILED",
      "CANCELLED",
    ]);
  });
});

describe("humanizeEnum", () => {
  it("turns a backend enum value into sentence case", () => {
    expect(humanizeEnum("PENDING_APPROVAL")).toBe("Pending approval");
    expect(humanizeEnum("VERIFIED")).toBe("Verified");
    expect(humanizeEnum("client_website")).toBe("Client website");
  });

  it("renders an em dash for a missing value", () => {
    expect(humanizeEnum(null)).toBe("—");
    expect(humanizeEnum(undefined)).toBe("—");
    expect(humanizeEnum("")).toBe("—");
  });
});

describe("labelFor", () => {
  it("prefers the map, and humanises an unknown value rather than showing raw enum text", () => {
    expect(labelFor(CAMPAIGN_STATUS_LABELS, "ACTIVE")).toBe("Active");
    expect(labelFor(CAMPAIGN_STATUS_LABELS, "SOME_NEW_STATUS")).toBe("Some new status");
    expect(labelFor(CAMPAIGN_STATUS_LABELS, null)).toBe("—");
  });
});
