import { Metadata } from "next";
import SearchPage from "./SearchPage";
import sampleQueries from "@/data/sample-queries.json";

export const metadata: Metadata = {
  title: "MS MARCO Passage Search",
  description: "Search the MS MARCO passage corpus using Anserini",
};

// Pick 5 random sample queries on each server render
function getRandomSamples() {
  const shuffled = [...sampleQueries].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, 5);
}

export default function Home() {
  const samples = getRandomSamples();
  return <SearchPage sampleQueries={samples} />;
}
