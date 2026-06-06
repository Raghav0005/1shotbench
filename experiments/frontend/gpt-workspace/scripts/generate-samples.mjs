import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

function findLocalFatjar() {
  const jar = readdirSync(process.cwd())
    .filter((entry) => /^anserini-.+-fatjar\.jar$/.test(entry))
    .sort()
    .at(-1);
  return jar ? resolve(jar) : undefined;
}

const jar = process.env.ANSERINI_JAR ? resolve(process.env.ANSERINI_JAR) : findLocalFatjar();
const topicSet = process.env.ANSERINI_TOPICS ?? 'msmarco-v1-passage-dev';
const output = resolve('src/data/msmarco-passage-dev-queries.json');

if (!jar || !existsSync(jar)) {
  console.error('Anserini fatjar not found. Set ANSERINI_JAR or place an anserini-*-fatjar.jar in this directory.');
  process.exit(1);
}

const result = spawnSync('java', ['-cp', jar, 'io.anserini.cli.TopicsRegistry', '--get', topicSet], {
  encoding: 'utf8',
  maxBuffer: 20 * 1024 * 1024,
});

if (result.status !== 0) {
  console.error(result.stderr || result.stdout);
  process.exit(result.status ?? 1);
}

const topics = JSON.parse(result.stdout);
const queries = Object.entries(topics)
  .map(([id, value]) => ({ id, query: value?.title }))
  .filter((entry) => entry.query)
  .sort((a, b) => Number(a.id) - Number(b.id));

mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(queries, null, 2)}\n`);
console.log(`Wrote ${queries.length} ${topicSet} queries to ${output}`);
