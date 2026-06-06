import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const backendPort = process.env.BACKEND_PORT || '8080';
  const url = new URL(request.url);
  const query = url.searchParams.get('query') || '';
  const hits = url.searchParams.get('hits') || '10';

  const backendUrl = `http://127.0.0.1:${backendPort}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query)}&hits=${encodeURIComponent(hits)}`;

  try {
    const response = await fetch(backendUrl);
    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json({ error: `Backend error: ${response.status} ${text}` }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Proxy error: ${message}` }, { status: 500 });
  }
}
