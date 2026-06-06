curl -fL -o "anserini-2.1.1-fatjar.jar" "https://repo1.maven.org/maven2/io/anserini/anserini/2.1.1/anserini-2.1.1-fatjar.jar"
java -cp "anserini-2.1.1-fatjar.jar" io.anserini.reproduce.ReproduceFromPrebuiltIndexes --list > configs.txt
cat configs.txt | grep nfcorpus
