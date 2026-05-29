/**
 * Sample queries from the MS MARCO passage dev query set.
 *
 * These are loaded statically so the frontend can show them immediately.
 * Regenerate with:
 *   java -cp "$ANSERINI_JAR" io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev
 *
 * To update: run scripts/fetch-sample-queries.sh and paste the output here,
 * or replace with the JSON output from TopicsRegistry --get.
 */
const SAMPLE_QUERIES: string[] = [
  "what is a lobster roll",
  "how to make a grilled cheese sandwich",
  "what is the capital of france",
  "how long does it take to boil an egg",
  "what is the population of new york city",
  "how to cook a steak medium rare",
  "what is the definition of photosynthesis",
  "how does a car engine work",
  "what are the symptoms of the flu",
  "how to change a tire",
  "what is machine learning",
  "how to bake chocolate chip cookies",
  "what is the speed of light",
  "how to write a resume",
  "what is the meaning of life",
  "how to train a dog",
  "what is bitcoin",
  "how to get rid of acne",
  "what is climate change",
  "how to start a business",
  "what is the tallest mountain in the world",
  "how to lose weight fast",
  "what causes earthquakes",
  "how to tie a tie",
  "what is dna",
  "how to make french toast",
  "what is the difference between affect and effect",
  "how to grow tomatoes",
  "what is blockchain technology",
  "how to take a screenshot on mac",
  "what is the best way to learn a new language",
  "how to brew coffee",
  "what is artificial intelligence",
  "how to meditate",
  "what are the planets in our solar system",
  "how to fix a leaky faucet",
  "what is global warming",
  "how to do a push up",
  "what is the periodic table",
  "how to make pasta",
  "what is renewable energy",
  "how to improve memory",
  "what is the water cycle",
  "how to write a cover letter",
  "what is inflation",
  "how to remove a splinter",
  "what causes lightning",
  "how to make a paper airplane",
  "what is the human genome",
  "how to cook rice",
];

/**
 * Return `count` randomly selected sample queries.
 * Shuffles a copy so the original array is not mutated.
 */
export function getRandomSampleQueries(count: number = 5): string[] {
  const shuffled = [...SAMPLE_QUERIES].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

export { SAMPLE_QUERIES };
