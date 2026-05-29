#!/usr/bin/env node

/**
 * Install Anserini Fatjar
 *
 * Downloads the latest release fatjar from Maven Central
 * and sets up the ANSERINI_JAR environment.
 * Follows the install-anserini-fatjar skill.
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const MAVEN_METADATA_URL =
  'https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml';

async function getLatestVersion() {
  return new Promise((resolve, reject) => {
    https
      .get(MAVEN_METADATA_URL, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          const match = data.match(/<release>([^<]+)<\/release>/);
          if (match) resolve(match[1]);
          else reject(new Error('Could not find release version in metadata'));
        });
      })
      .on('error', reject);
  });
}

async function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(destPath);
    const protocol = url.startsWith('https') ? https : http;
    protocol
      .get(url, (res) => {
        if (res.statusCode === 302 || res.statusCode === 301) {
          file.close();
          fs.unlinkSync(destPath);
          return downloadFile(res.headers.location, destPath).then(resolve, reject);
        }
        if (res.statusCode !== 200) {
          file.close();
          fs.unlinkSync(destPath);
          reject(new Error(`Download failed with status ${res.statusCode}`));
          return;
        }
        res.pipe(file);
        file.on('finish', () => {
          file.close();
          resolve();
        });
      })
      .on('error', (err) => {
        file.close();
        fs.unlinkSync(destPath);
        reject(err);
      });
  });
}

async function main() {
  console.log('=== Anserini Fatjar Installer ===');

  // 1. Check Java
  try {
    const javaVersion = execSync('java -version 2>&1', { encoding: 'utf8' });
    console.log('Java available:', javaVersion.split('\n')[0]);
  } catch (e) {
    console.error('ERROR: Java is not available on PATH. Please install JDK 21.');
    process.exit(1);
  }

  // 2. Discover latest version
  console.log('\nFetching latest Anserini release version...');
  const version = await getLatestVersion();
  console.log('Latest version:', version);

  // 3. Determine output path
  const workspaceDir = path.resolve(__dirname, '..');
  const jarName = `anserini-${version}-fatjar.jar`;
  const jarPath = path.join(workspaceDir, jarName);

  if (fs.existsSync(jarPath)) {
    console.log(`Fatjar already exists at ${jarPath}`);
  } else {
    // 4. Download
    const url = `https://repo1.maven.org/maven2/io/anserini/anserini/${version}/anserini-${version}-fatjar.jar`;
    console.log(`\nDownloading from: ${url}`);
    console.log(`To: ${jarPath}`);
    await downloadFile(url, jarPath);
    console.log('Download complete.');
  }

  // 5. Write .env file for the app
  const envPath = path.join(workspaceDir, '.env');
  fs.writeFileSync(envPath, `ANSERINI_JAR=${jarPath}\nANSERINI_VERSION=${version}\n`);
  console.log(`\nEnvironment written to ${envPath}`);

  // 6. Smoke test: CACM retrieval
  console.log('\n=== Running CACM smoke test ===');
  try {
    const cmd = `java -cp "${jarPath}" io.anserini.search.SearchCollection -threads 1 -index cacm -topics cacm -output run.cacm.bm25.txt -hits 1000 -bm25`;
    console.log(`Running: ${cmd}`);
    execSync(cmd, { cwd: workspaceDir, stdio: 'inherit' });
    console.log('CACM retrieval completed.');

    // Evaluate
    const evalCmd = `java -cp "${jarPath}" io.anserini.eval.TrecEval -c -m map -m P.30 cacm run.cacm.bm25.txt`;
    console.log(`Running: ${evalCmd}`);
    const evalOut = execSync(evalCmd, { cwd: workspaceDir, encoding: 'utf8' });
    console.log('Evaluation output:');
    console.log(evalOut);

    // Check expected scores
    if (evalOut.includes('0.3123') && evalOut.includes('0.1942')) {
      console.log('\n✓ CACM smoke test PASSED - scores match expected values.');
    } else {
      console.log('\n⚠ CACM smoke test completed but scores may differ from expected.');
    }
  } catch (e) {
    console.error('CACM smoke test failed:', e.message);
    process.exit(1);
  }

  console.log('\n=== Installation complete ===');
  console.log(`ANSERINI_JAR=${jarPath}`);
}

main().catch((err) => {
  console.error('Installation failed:', err);
  process.exit(1);
});
