import { promises as fs } from 'node:fs';
import path from 'node:path';
import { ROOT } from '../src/anserini.js';

async function text(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return await response.text();
}

async function main() {
  const metadata = await text('https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml');
  const version = metadata.match(/<release>([^<]+)<\/release>/)?.[1];
  if (!version) throw new Error('Could not discover latest Anserini release from Maven metadata.');
  const toolsDir = path.join(ROOT, 'tools');
  await fs.mkdir(toolsDir, { recursive: true });
  const out = path.join(toolsDir, `anserini-${version}-fatjar.jar`);
  try {
    await fs.stat(out);
    console.log(`Anserini fatjar already exists: ${out}`);
    return;
  } catch {}
  const url = `https://repo1.maven.org/maven2/io/anserini/anserini/${version}/anserini-${version}-fatjar.jar`;
  console.log(`Downloading ${url}`);
  const response = await fetch(url);
  if (!response.ok || !response.body) throw new Error(`Failed to download ${url}: ${response.status}`);
  const file = await fs.open(out, 'w');
  try {
    for await (const chunk of response.body) {
      await file.write(chunk);
    }
  } finally {
    await file.close();
  }
  console.log(`Downloaded ${out}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
