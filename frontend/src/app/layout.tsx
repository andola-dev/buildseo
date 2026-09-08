import type { Metadata, Viewport } from "next";

import { Providers } from "@/components/layout/providers";
import { APP_DESCRIPTION, APP_NAME } from "@/config/app";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: APP_NAME,
    template: `%s · ${APP_NAME}`,
  },
  description: APP_DESCRIPTION,
  applicationName: APP_NAME,
  // The authenticated application is not an SEO surface, and tenant data must
  // never be indexed (spec §62). Public marketing pages, if any are added
  // later, override this per route.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
