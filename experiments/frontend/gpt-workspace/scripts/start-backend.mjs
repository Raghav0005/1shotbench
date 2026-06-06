import { spawn } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

function findLocalFatjar() {
  const jar = readdirSync(process.cwd())
    .filter((entry) => /^anserini-.+-fatjar\.jar$/.test(entry))
    .sort()
    .at(-1);
  return jar ? resolve(jar) : undefined;
}

const jar = process.env.ANSERINI_JAR ? resolve(process.env.ANSERINI_JAR) : findLocalFatjar();
const port = process.env.BACKEND_PORT ?? process.env.ANSERINI_PORT ?? '8080';

if (!jar || !existsSync(jar)) {
  console.error('Anserini fatjar not found. Set ANSERINI_JAR or place an anserini-*-fatjar.jar in this directory.');
  process.exit(1);
}

console.log(`Starting Anserini REST API on port ${port}`);
console.log(`Using ${jar}`);

const child = spawn('java', ['-cp', jar, 'io.anserini.api.RestServer', '--port', port], {
  stdio: 'inherit',
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 0);
});
