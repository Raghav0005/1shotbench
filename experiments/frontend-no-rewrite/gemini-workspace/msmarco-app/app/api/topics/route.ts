import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

let cachedTopics: { [key: string]: { title: string } } | null = null;
let topicKeys: string[] = [];

export async function GET() {
  try {
    if (!cachedTopics) {
      const filePath = path.join(process.cwd(), 'public', 'topics.json');
      const fileData = fs.readFileSync(filePath, 'utf8');
      cachedTopics = JSON.parse(fileData);
      topicKeys = Object.keys(cachedTopics!);
    }

    // Pick 5 random keys
    const samples = [];
    for (let i = 0; i < 5; i++) {
      const randomKey = topicKeys[Math.floor(Math.random() * topicKeys.length)];
      samples.push({
        id: randomKey,
        title: cachedTopics![randomKey].title,
      });
    }

    return NextResponse.json(samples);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
