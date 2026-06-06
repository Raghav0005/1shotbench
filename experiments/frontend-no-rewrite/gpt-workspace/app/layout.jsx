import './globals.css';

export const metadata = {
  title: 'MS MARCO Passage Search',
  description: 'Local MS MARCO passage search backed by Anserini REST API',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
