import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/features/auth/components/login-form";
import { APP_NAME } from "@/config/app";

/**
 * The login page is the product's only meaningful SEO surface (spec §62), so
 * unlike the authenticated application it declares real metadata.
 */
export const metadata: Metadata = {
  title: "Sign in",
  description: `Sign in to ${APP_NAME} to discover, qualify and submit links to free online listing and directory sites.`,
  robots: { index: true, follow: true },
};

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-12">
      {/* `useSearchParams` in the form requires a Suspense boundary. */}
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
