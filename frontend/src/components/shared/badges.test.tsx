import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ScoreBadge, ScoreBar } from "@/components/shared/score-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { FreeListingsBadge } from "@/components/shared/free-listings-badge";
import { SUBMISSION_STATUS_LABELS } from "@/config/labels";

describe("StatusBadge", () => {
  it("uses the supplied label map", () => {
    render(
      <StatusBadge status="PENDING_APPROVAL" labels={SUBMISSION_STATUS_LABELS} />,
    );
    expect(screen.getByText("Pending approval")).toBeInTheDocument();
  });

  it("renders a raw enum value readably when no map is given", () => {
    render(<StatusBadge status="VERIFICATION_PENDING" />);
    expect(screen.getByText("VERIFICATION PENDING")).toBeInTheDocument();
  });

  it("shows 'Unknown' instead of an empty badge for a missing status", () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("gives the same status the same tone wherever it appears", () => {
    const { container: a } = render(<StatusBadge status="VERIFIED" />);
    const { container: b } = render(
      <StatusBadge status="VERIFIED" labels={SUBMISSION_STATUS_LABELS} />,
    );

    const classOf = (root: HTMLElement) =>
      root.querySelector('[data-slot="badge"]')?.className;

    expect(classOf(a)).toBe(classOf(b));
  });
});

describe("ScoreBadge", () => {
  it("rounds the score", () => {
    render(<ScoreBadge score={86.7} />);
    expect(screen.getByText("87")).toBeInTheDocument();
  });

  it("marks an unmeasured score as such rather than showing 0", () => {
    render(<ScoreBadge score={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByTitle("Not measured")).toBeInTheDocument();
  });

  it("colours spam inversely to quality at the same value", () => {
    const { container: quality } = render(<ScoreBadge score={80} kind="quality" />);
    const { container: spam } = render(<ScoreBadge score={80} kind="spam" />);

    expect(quality.firstElementChild?.className).toContain("text-success");
    expect(spam.firstElementChild?.className).toContain("text-destructive");
  });
});

describe("ScoreBar", () => {
  it("labels the bar for screen readers", () => {
    render(<ScoreBar label="Quality" score={73} kind="quality" />);

    expect(screen.getByText("Quality")).toBeInTheDocument();
    expect(screen.getByText("73")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Quality: 73 out of 100"),
    ).toBeInTheDocument();
  });

  it("clamps an out-of-range score to the track", () => {
    render(<ScoreBar label="Authority" score={140} kind="authority" />);
    const bar = screen.getByLabelText("Authority: 140 out of 100");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });
});

describe("FreeListingsBadge", () => {
  it("states the product scope in the interface", () => {
    render(<FreeListingsBadge />);
    expect(screen.getByText("Free listings only")).toBeInTheDocument();
  });
});
