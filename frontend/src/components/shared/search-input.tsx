"use client";

import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SEARCH_DEBOUNCE_MS } from "@/config/app";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn } from "@/lib/utils/cn";

interface SearchInputProps {
  /** Current committed value, normally read from the URL. */
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  "aria-label"?: string;
}

/**
 * Debounced search box (spec §53).
 *
 * The field is locally controlled so typing stays responsive, and the debounced
 * value is pushed up — one request per pause rather than one per keystroke.
 * An external change (a cleared filter, a back navigation) is adopted.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
  "aria-label": ariaLabel,
}: SearchInputProps) {
  const [draft, setDraft] = useState(value);
  const debounced = useDebouncedValue(draft, SEARCH_DEBOUNCE_MS);

  // Adopt external changes (back/forward, "clear filters") without clobbering
  // what the user is currently typing.
  useEffect(() => {
    setDraft((current) => (current === value ? current : value));
  }, [value]);

  useEffect(() => {
    if (debounced !== value) onChange(debounced);
    // `onChange` is intentionally excluded: callers commonly pass an inline
    // arrow, and including it would fire on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  return (
    <div className={cn("relative", className)}>
      <Search
        className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
        aria-hidden
      />
      <Input
        type="search"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        className="pl-8 pr-8"
      />
      {draft ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => setDraft("")}
          className="absolute top-1/2 right-1 size-7 -translate-y-1/2"
        >
          <X className="size-3.5" aria-hidden />
          <span className="sr-only">Clear search</span>
        </Button>
      ) : null}
    </div>
  );
}
