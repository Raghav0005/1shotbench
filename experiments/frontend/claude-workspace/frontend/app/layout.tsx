import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MS MARCO Passage Search",
  description:
    "Search the MS MARCO passage corpus via Anserini's REST API, with random sample queries drawn from the dev set.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
