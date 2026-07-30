import type { Metadata } from "next";
import { Google_Sans_Code, Google_Sans_Flex } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/topnav";
import { Providers } from "./providers";

/**
 * Self-hosted at build time via next/font, so there is no render-blocking
 * request to Google and no layout shift from a late swap.
 *
 * "Google Sans Flex Headline" is not a separate family -- it is Google Sans
 * Flex at a display optical size. The family carries an `opsz` axis (6-144),
 * so shipping that axis lets one download serve both roles: globals.css
 * pins a display opsz for headings and leaves text at the reading default.
 * `wght` ships automatically for variable fonts, giving the full 1-1000 range.
 */
const googleSansFlex = Google_Sans_Flex({
  subsets: ["latin"],
  variable: "--font-google-sans-flex",
  axes: ["opsz", "wdth", "GRAD"],
  display: "swap",
});

/** Sibling monospace, for tabular/technical strings where Flex would misalign. */
const googleSansCode = Google_Sans_Code({
  subsets: ["latin"],
  variable: "--font-google-sans-code",
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Vendrai Supplier Onboarding",
  description: "Evidence-driven enterprise supplier onboarding and human approval.",
  icons: {
    icon: "/favicon.svg?v=2",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${googleSansFlex.variable} ${googleSansCode.variable}`}
      suppressHydrationWarning={true}
    >
      <body className="min-h-full font-body bg-[var(--color-bg)] text-[var(--color-ink)]" suppressHydrationWarning={true}>
        <Providers>
          <TopNav />
          <main id="main-content">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
