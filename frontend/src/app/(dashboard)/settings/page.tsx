import { redirect } from "next/navigation";

/** `/settings` lands on the first section rather than showing an empty shell. */
export default function SettingsIndexPage() {
  redirect("/settings/general");
}
