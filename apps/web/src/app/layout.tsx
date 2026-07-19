import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "NeuroX Supplier Onboarding",
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
      className="h-full antialiased"
      suppressHydrationWarning={true}
    >
      <body className="min-h-full flex h-screen overflow-hidden font-body bg-[var(--color-clay)] text-[var(--color-primary)]" suppressHydrationWarning={true}>
        <div className="flex w-full h-full">
          <Providers>
            <Sidebar />
            <main className="h-full flex-1 overflow-y-auto pb-20 md:pb-0" id="main-content">
              {children}
            </main>
          </Providers>
        </div>
      </body>
    </html>
  );
}
