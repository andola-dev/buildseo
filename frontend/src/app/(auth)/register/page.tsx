import type { Metadata } from "next";

import { APP_NAME } from "@/config/app";
import { RegisterForm } from "@/features/auth/components/register-form";

export const metadata: Metadata = {
  title: "Create your workspace",
  description: `Create a ${APP_NAME} workspace and start discovering free listing and directory link opportunities.`,
  robots: { index: true, follow: true },
};

export default function RegisterPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12">
      <RegisterForm />
    </main>
  );
}
