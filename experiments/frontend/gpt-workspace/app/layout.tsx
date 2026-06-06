import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'MS MARCO Passage Search',
  description: 'Local Next.js search UI backed by the Anserini REST API.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
