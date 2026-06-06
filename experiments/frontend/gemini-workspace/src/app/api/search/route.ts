import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('query');
  const hits = searchParams.get('hits') || '10';

  if (!query) {
    return NextResponse.json({ error: 'Query is required' }, { status: 400 });
  }

  const backendPort = process.env.BACKEND_PORT || '8080';
  const backendHost = process.env.BACKEND_HOST || 'localhost';
  const backendUrl = `http://${backendHost}:${backendPort}/v1/msmarco-v1-passage/search?query=${encodeURIComponent(query)}&hits=${encodeURIComponent(hits)}`;

  try {
    const res = await fetch(backendUrl);
    
    if (!res.ok) {
      return NextResponse.json({ error: 'Backend error' }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error('Error fetching from backend:', err);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 502 });
  }
}
