'use server';

import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = promisify(exec);
let ANSERINI_JAR = process.env.ANSERINI_JAR;
if (!ANSERINI_JAR || !fs.existsSync(ANSERINI_JAR)) {
  const possiblePaths = [
    path.join(process.cwd(), 'anserini-2.1.1-fatjar.jar'),
    path.join(process.cwd(), '..', 'anserini-2.1.1-fatjar.jar'),
  ];
  for (const p of possiblePaths) {
    if (fs.existsSync(p)) {
      ANSERINI_JAR = p;
      break;
    }
  }
}

if (!ANSERINI_JAR) {
  ANSERINI_JAR = 'anserini-fatjar-not-found.jar'; // Will cause standard java error caught by UI
}

export async function getPrebuiltIndexes() {
  const { stdout } = await execAsync(`java -cp "${ANSERINI_JAR}" io.anserini.cli.PrebuiltIndexRegistry --type inverted --list`, { maxBuffer: 1024 * 1024 * 10 });
  const indexes = JSON.parse(stdout);
  return indexes;
}

export async function getTopics() {
  const { stdout } = await execAsync(`java -cp "${ANSERINI_JAR}" io.anserini.cli.TopicsRegistry --list`, { maxBuffer: 1024 * 1024 * 10 });
  const topics = JSON.parse(stdout);
  return topics;
}

export async function runEvaluation(index: string, topics: string, metric: string) {
  const outputRun = `run.${index}.${topics}.txt`;
  
  try {
    // 1. Run SearchCollection
    const searchCmd = `java -cp "${ANSERINI_JAR}" io.anserini.search.SearchCollection -threads 1 -index ${index} -topics ${topics} -output ${outputRun} -hits 1000 -bm25`;
    const searchStartTime = Date.now();
    await execAsync(searchCmd);
    const searchElapsed = Date.now() - searchStartTime;

    // 2. Run TrecEval
    const evalCmd = `java -cp "${ANSERINI_JAR}" io.anserini.eval.TrecEval -c -m ${metric} ${topics} ${outputRun}`;
    const { stdout: evalStdout } = await execAsync(evalCmd);

    // Parse the metric score from trec_eval output
    let score = null;
    const lines = evalStdout.trim().split('\n');
    for (const line of lines) {
      if (line.startsWith(metric) || line.startsWith(metric.replace('.', '_')) || line.toLowerCase().includes(metric.toLowerCase())) {
        const parts = line.trim().split(/\s+/);
        if (parts.length === 3) {
          score = parts[2];
          break;
        }
      }
    }

    return {
      index,
      topics,
      metric,
      score,
      searchElapsed,
      runFile: outputRun,
      evalOutput: evalStdout,
    };
  } catch (error: unknown) {
    if (error instanceof Error) {
      return { error: error.message };
    }
    return {
      error: String(error)
    };
  }
}
