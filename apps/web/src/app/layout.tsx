import type { Metadata } from "next";
import { Calistoga, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/topnav";
import { Providers } from "./providers";

/**
 * Self-hosted at build time via next/font, so there is no render-blocking
 * request to Google and no layout shift from a late swap. Exposed as CSS
 * variables that globals.css maps onto --font-display / --font-body / --font-mono.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const calistoga = Calistoga({
  subsets: ["latin"],
  variable: "--font-calistoga",
  weight: "400",
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
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
      className={`h-full antialiased ${inter.variable} ${calistoga.variable} ${jetbrainsMono.variable}`}
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
