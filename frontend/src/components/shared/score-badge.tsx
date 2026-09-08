import { Progress } from "@/components/ui/progress";
import { scoreTone, type ScoreKind } from "@/config/status";
import { formatScore } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

const TONE_TEXT = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  muted: "text-muted-foreground",
} as const;

const TONE_BAR = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  muted: "bg-muted-foreground/40",
} as const;

interface ScoreProps {
  score: number | null | undefined;
  /** `spam` inverts the bands: high is bad. */
  kind?: ScoreKind;
  className?: string;
}

/**
 * A compact 0–100 score (spec §52).
 *
 * The same component serves quality, relevance, authority and spam so the
 * colour thresholds cannot drift between metrics. Deliberately just a number:
 * turning every metric into a chart is what spec §52 warns against.
 */
export function ScoreBadge({ score, kind = "quality", className }: ScoreProps) {
  const tone = scoreTone(kind, score);

  return (
    <span
      className={cn("tabular text-sm font-medium", TONE_TEXT[tone], className)}
      title={score === null || score === undefined ? "Not measured" : undefined}
    >
      {formatScore(score)}
    </span>
  );
}

/**
 * A score with a bar, for detail pages where there is room to show magnitude.
 */
export function ScoreBar({
  score,
  kind = "quality",
  label,
  className,
}: ScoreProps & { label?: string }) {
  const tone = scoreTone(kind, score);
  const value = score === null || score === undefined ? 0 : Math.max(0, Math.min(100, score));

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        {label ? <span className="text-muted-foreground text-xs">{label}</span> : null}
        <span className={cn("tabular text-sm font-semibold", TONE_TEXT[tone])}>
          {formatScore(score)}
        </span>
      </div>
      <Progress
        value={value}
        className="h-1.5"
        indicatorClassName={TONE_BAR[tone]}
        aria-label={label ? `${label}: ${formatScore(score)} out of 100` : undefined}
      />
    </div>
  );
}
