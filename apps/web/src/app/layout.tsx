import type { Metadata } from "next";
import { Plus_Jakarta_Sans, DM_Sans } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Vendrai: Vendor-to-Pay Exception System",
  description: "Enterprise multi-agent exception handling dashboard.",
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
      className={`${plusJakartaSans.variable} ${dmSans.variable} h-full antialiased`}
      suppressHydrationWarning={true}
    >
      <body className="min-h-full flex h-screen overflow-hidden font-body bg-[var(--color-clay)] text-[var(--color-primary)]" suppressHydrationWarning={true}>
        <div className="flex w-full h-full">
          <Sidebar />
          <main className="flex-1 h-full overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
