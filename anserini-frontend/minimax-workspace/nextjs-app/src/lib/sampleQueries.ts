export interface SampleQuery {
  id: string;
  query: string;
}

let cachedQueries: SampleQuery[] | null = null;

export async function fetchSampleQueries(count = 5): Promise<SampleQuery[]> {
  if (cachedQueries) {
    return shuffleArray([...cachedQueries]).slice(0, count);
  }

  const version = process.env.ANSERINI_VERSION || "2.1.1";
  const jarPath = process.env.ANSERINI_JAR || `../anserini-${version}-fatjar.jar`;

  // We'll embed a default set of sample queries in case the JAR call fails
  const defaultQueries: SampleQuery[] = [
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
    { id: "11", query: "tips for job interview" },
    { id: "12", query: "difference between allergies and cold" },
    { id: "13", query: "how to cook brown rice" },
    { id: "14", query: "why do we dream" },
    { id: "15", query: "what is artificial intelligence" },
  ];

  try {
    // Try to use the TopicsRegistry CLI to get real MS MARCO queries
    const { execSync } = await import("child_process");
    const cmd = `java -cp "${jarPath}" io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev`;
    const output = execSync(cmd, { encoding: "utf-8", timeout: 30000 });
    const parsed = JSON.parse(output);

    cachedQueries = Object.entries(parsed).map(([id, val]: [string, any]) => ({
      id,
      query: val.title || val.query || String(val),
    }));

    if (cachedQueries.length > 0) {
      return shuffleArray([...cachedQueries]).slice(0, count);
    }
  } catch (error) {
    console.warn("Failed to fetch MS MARCO topics, using defaults:", error);
  }

  // Fallback to default queries if JAR call fails
  cachedQueries = defaultQueries;
  return shuffleArray([...cachedQueries]).slice(0, count);
}

function shuffleArray<T>(array: T[]): T[] {
  const shuffled = [...array];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}