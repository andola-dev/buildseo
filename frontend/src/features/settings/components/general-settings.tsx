"use client";

import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/forms/field";
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, STORAGE_KEYS } from "@/config/app";
import { useSidebar } from "@/components/layout/sidebar-context";
import { readLocalNumber, writeLocal } from "@/lib/utils/storage";
import { useEffect, useState } from "react";

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

/**
 * Interface preferences (spec §31).
 *
 * These are per-browser display choices, so they are stored locally rather than
 * sent to the backend — there is no user-preferences endpoint, and inventing
 * one is not the frontend's call. This is also the one place where optimistic
 * updates are unambiguously safe (spec §55): nothing server-side changes.
 */
export function GeneralSettings() {
  const { theme, setTheme } = useTheme();
  const { collapsed, setCollapsed } = useSidebar();

  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // Read after mount so server and first client render agree.
  useEffect(() => {
    setPageSize(readLocalNumber(STORAGE_KEYS.tablePageSize, DEFAULT_PAGE_SIZE));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">General</h2>
        <p className="text-muted-foreground text-sm">
          How this application looks and behaves in your browser. These preferences are
          stored on this device only.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 pt-0">
          <Field id="theme" label="Theme">
            <RadioGroup
              value={theme ?? "system"}
              onValueChange={setTheme}
              className="grid gap-2 sm:grid-cols-3"
            >
              {THEMES.map((option) => {
                const Icon = option.icon;
                return (
                  <Label
                    key={option.value}
                    htmlFor={`theme-${option.value}`}
                    className="hover:bg-accent/40 flex cursor-pointer items-center gap-2.5 rounded-lg border p-3 font-normal"
                  >
                    <RadioGroupItem id={`theme-${option.value}`} value={option.value} />
                    <Icon className="text-muted-foreground size-4" aria-hidden />
                    <span className="text-sm">{option.label}</span>
                  </Label>
                );
              })}
            </RadioGroup>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Layout</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 pt-0">
          <div className="flex items-center justify-between gap-4">
            <div>
              <Label htmlFor="collapse-sidebar">Collapse the sidebar by default</Label>
              <p className="text-muted-foreground mt-1 text-xs">
                Shows icons only, with labels on hover. Toggle any time with Ctrl+B.
              </p>
            </div>
            <Switch
              id="collapse-sidebar"
              checked={collapsed}
              onCheckedChange={setCollapsed}
            />
          </div>

          <Field
            id="page-size"
            label="Default rows per page"
            hint="Applies to new table views. Each table remembers its own size in the URL."
          >
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                const next = Number.parseInt(value, 10);
                setPageSize(next);
                writeLocal(STORAGE_KEYS.tablePageSize, String(next));
              }}
            >
              <SelectTrigger id="page-size" className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size} rows
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>
    </div>
  );
}
