import { promises as fs } from 'node:fs';
import path from 'node:path';
import { locateAnseriniJar, runCommand, ROOT } from '../src/anserini.js';

async function main() {
  const jar = await locateAnseriniJar();
  const runsDir = path.join(ROOT, 'runs');
  await fs.mkdir(runsDir, { recursive: true });
  const runPath = path.join(runsDir, 'run.cacm.bm25.txt');
  const evalPath = path.join(runsDir, 'eval.cacm.bm25.txt');
  await runCommand(['java', '-cp', jar, 'io.anserini.search.SearchCollection', '-threads', '1', '-index', 'cacm', '-topics', 'cacm', '-output', runPath, '-hits', '1000', '-bm25'], { timeoutMs: 10 * 60 * 1000 });
  const evalResult = await runCommand(['java', '-cp', jar, 'io.anserini.eval.TrecEval', '-c', '-m', 'map', '-m', 'P.30', 'cacm', runPath], { timeoutMs: 2 * 60 * 1000 });
  await fs.writeFile(evalPath, evalResult.stdout);
  if (!evalResult.stdout.includes('map') || !evalResult.stdout.includes('0.3123') || !evalResult.stdout.includes('P_30') || !evalResult.stdout.includes('0.1942')) {
    throw new Error(`CACM smoke test produced unexpected scores:\n${evalResult.stdout}`);
  }
  console.log(evalResult.stdout.trim());
  console.log(`CACM smoke test OK. Run: ${runPath}; Eval: ${evalPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
