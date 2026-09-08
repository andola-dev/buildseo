import { redirect } from "next/navigation";

/** The application entry point is the dashboard; the layout guards access. */
export default function RootPage() {
  redirect("/dashboard");
}
