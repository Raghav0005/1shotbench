// Resolves the set of qrels symbols that the local Anserini fatjar
// actually knows about. We extract them from `io.anserini.eval.Qrels` by
// asking `javap` to print the class, then parsing the static initializer
// to recover (enum name, qrels filename) pairs and the extra symbol
// aliases registered in `generateSymbolFileDict`. From those we compute
// the set of lowercase symbols that `io.anserini.eval.TrecEval` accepts
// as qrels arguments (the lookup uses the substring between the dots of
// the qrels filename, e.g. `cacm` from `qrels.cacm.txt`, plus a few
// hardcoded aliases registered by the class).

const { execFileSync } = require('child_process');
const { jarPath } = require('./registry');

function parseQrelsClass() {
  const jar = jarPath();
  let out;
  try {
    out = execFileSync(
      'javap',
      ['-c', '-p', '-cp', jar, 'io.anserini.eval.Qrels'],
      { maxBuffer: 16 * 1024 * 1024 }
    );
  } catch (err) {
    throw new Error(
      `Failed to read Qrels constants via javap from ${jar}: ${err.message}\n` +
        `Make sure javap is on PATH and is from a JDK that can read modern class files.`
    );
  }
  const text = out.toString();

  // 1. Parse the static initializer: pairs of (enumName, qrelsFilename).
  // Each enum is constructed with two `ldc_w` constants back-to-back.
  const staticMatch = text.match(/static\s*\{\};\s*\n([\s\S]*?)\n\s*\}/);
  if (!staticMatch) {
    throw new Error('Could not find Qrels static initializer in javap output.');
  }
  const staticInit = staticMatch[1];
  const stringConsts = [];
  const re = /ldc_w\s+#\d+\s+\/\/\s+String\s+(\S+)/g;
  let m;
  while ((m = re.exec(staticInit)) !== null) {
    stringConsts.push(m[1]);
  }
  if (stringConsts.length % 2 !== 0) {
    throw new Error(
      `Unexpected odd number of string constants in Qrels static initializer: ${stringConsts.length}`
    );
  }
  const enumPairs = [];
  for (let i = 0; i < stringConsts.length; i += 2) {
    enumPairs.push([stringConsts[i], stringConsts[i + 1]]);
  }

  // 2. Parse the generateSymbolFileDict method: a sequence of (key, value)
  // pairs that the class registers as lowercase aliases.
  const methodMatch = text.match(
    /private\s+static\s+java\.util\.HashMap[\s\S]*?generateSymbolFileDict\([\s\S]*?(?=\n\s*private\s|\n\s*public\s|\n\s*static\s*\{)/
  );
  const extras = [];
  if (methodMatch) {
    const re2 = /ldc_w\s+#\d+\s+\/\/\s+String\s+(\S+)/g;
    let m2;
    const methodStrings = [];
    while ((m2 = re2.exec(methodMatch[0])) !== null) {
      methodStrings.push(m2[1]);
    }
    for (let i = 0; i + 1 < methodStrings.length; i += 2) {
      extras.push([methodStrings[i], methodStrings[i + 1]]);
    }
  }

  return { enumPairs, extras };
}

function listKnownQrels() {
  const { enumPairs, extras } = parseQrelsClass();
  // TrecEval's `potentiallyExpandSymbol` looks up the qrels argument
  // against the lowercase substring of the qrels filename between the
  // first and last dot. For `qrels.cacm.txt` that yields `cacm`. For
  // multi-dot paths like `qrels.msmarco-passage.dev-subset.txt` it
  // yields `msmarco-passage.dev-subset`. The class also registers a
  // handful of shorter aliases (e.g. `msmarco-passage-dev`) in
  // `generateSymbolFileDict`.
  const symbols = new Set();
  for (const [, path] of enumPairs) {
    const firstDot = path.indexOf('.');
    const lastDot = path.lastIndexOf('.');
    if (firstDot >= 0 && lastDot > firstDot) {
      symbols.add(path.substring(firstDot + 1, lastDot).toLowerCase());
    }
  }
  for (const [alias] of extras) {
    symbols.add(alias.toLowerCase());
  }
  if (symbols.size === 0) {
    throw new Error('No qrels symbols could be parsed from the Qrels class.');
  }
  return symbols;
}

module.exports = {
  listKnownQrels,
  parseQrelsClass,
};
