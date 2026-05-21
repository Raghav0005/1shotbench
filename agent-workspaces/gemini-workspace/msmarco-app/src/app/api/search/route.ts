import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('query');
  
  if (!query) {
    return NextResponse.json({ error: 'Query is required' }, { status: 400 });
  }

  const backendUrl = process.env.ANSERINI_BACKEND_URL || 'http://localhost:8080';
  const targetUrl = `${backendUrl}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query)}&hits=10`;

  try {
    const res = await fetch(targetUrl);
    if (!res.ok) {
      return NextResponse.json({ error: 'Backend returned an error' }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error('Proxy error:', err);
    return NextResponse.json({ error: 'Failed to fetch from backend' }, { status: 500 });
  }
}
