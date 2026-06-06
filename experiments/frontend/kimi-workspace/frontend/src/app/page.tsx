import SearchPage from "./components/SearchPage";
import queries from "../data/queries.json";

export default function Home() {
  return <SearchPage queries={queries as string[]} />;
}
