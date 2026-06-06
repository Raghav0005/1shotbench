import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

let cachedQueries;

async function loadQueries() {
  if (!cachedQueries) {
    const filePath = path.join(process.cwd(), 'data', 'msmarco-v1-passage-dev-queries.json');
    cachedQueries = JSON.parse(await readFile(filePath, 'utf8'));
  }
  return cachedQueries;
}

function randomSamples(items, count) {
  const pool = [...items];
  const limit = Math.min(count, pool.length);
  const selected = [];

  for (let i = 0; i < limit; i += 1) {
    const index = Math.floor(Math.random() * pool.length);
    selected.push(pool[index]);
    pool.splice(index, 1);
  }

  return selected;
}

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const countParam = Number(searchParams.get('count') || '8');
  const count = Number.isFinite(countParam) ? Math.min(Math.max(Math.floor(countParam), 1), 20) : 8;
  const queries = await loadQueries();

  return NextResponse.json({ queries: randomSamples(queries, count) });
}
