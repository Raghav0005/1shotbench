import { NextResponse } from "next/server";
import { execSync } from "child_process";
import crypto from "crypto";

// Cache the queries for the lifetime of the server process
let cachedQueries: Array<{ id: string; query: string }> | null = null;

function shuffleArray<T>(array: T[]): T[] {
  const shuffled = [...array];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

export async function GET() {
  try {
    // Return cached queries if available
    if (cachedQueries) {
      return NextResponse.json(shuffleArray([...cachedQueries]).slice(0, 5));
    }

    const version = process.env.ANSERINI_VERSION || "2.1.1";
    const jarPath =
      process.env.ANSERINI_JAR || `../../anserini-${version}-fatjar.jar`;

    // Try to get real queries from Anserini TopicsRegistry
    const cmd = `java -cp "${jarPath}" io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev`;
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
    const parsed = JSON.parse(output);

    cachedQueries = Object.entries(parsed).map(([id, val]: [string, any]) => ({
      id: crypto.randomUUID(),
      query: val.title || val.query || String(val),
    }));

    return NextResponse.json(shuffleArray([...cachedQueries]).slice(0, 5));
  } catch (error) {
    console.error("Failed to fetch sample queries:", error);

    // Return hardcoded fallback queries
    const fallbackQueries = [
      { id: "1", query: "what is a lobster roll" },
      { id: "2", query: "how do I make pancakes from scratch" },
      { id: "3", query: "benefits of drinking green tea" },
      { id: "4", query: "who invented the printing press" },
      { id: "5", query: "difference between virus and bacteria" },
      { id: "6", query: "how to tie a Windsor knot" },
      { id: "7", query: "best places to visit in Paris" },
      { id: "8", query: "what causes migraines" },
      { id: "9", query: "history of the internet" },
      { id: "10", query: "how does photosynthesis work" },
    ];

    return NextResponse.json(shuffleArray(fallbackQueries).slice(0, 5));
  }
}