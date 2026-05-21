import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MS MARCO Passage Search',
  description: 'Search MS MARCO passages with Anserini REST API',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
