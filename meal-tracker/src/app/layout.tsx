import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "食事ログ",
  description: "個人用の食事・栄養記録",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/favicon.svg" },
  appleWebApp: { capable: true, title: "食事ログ", statusBarStyle: "default" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#f8f8f6" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ja"><body>{children}</body></html>;
}
