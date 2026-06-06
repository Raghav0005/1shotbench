FROM node:20-bookworm-slim

# Install OpenJDK 21, curl, and jq
RUN apt-get update && \
    apt-get install -y openjdk-21-jdk-headless curl jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up environment variables
ENV PORT=10000
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Set the working directory
WORKDIR /app

# Copy package.json and install dependencies
COPY package*.json ./
RUN npm install --production

# We don't want to rely on the host's backend/anserini directory because Render will rebuild it.
# Actually, wait, it's better to copy the pre-downloaded fatjar or download it during docker build.
# Let's download it during docker build.
RUN mkdir -p backend/anserini && \
    curl -fL -o backend/anserini/anserini-2.1.1-fatjar.jar "https://repo1.maven.org/maven2/io/anserini/anserini/2.1.1/anserini-2.1.1-fatjar.jar"
ENV ANSERINI_JAR=/app/backend/anserini/anserini-2.1.1-fatjar.jar

# Pre-download the prebuilt index by running a dummy search
RUN java -cp ${ANSERINI_JAR} io.anserini.search.SearchCollection \
    -threads 1 -index beir-v1.0.0-nfcorpus.flat -topics beir-nfcorpus \
    -output /dev/null -bm25 -removeQuery -hits 1

# Copy server code
COPY server.js .

# Copy built frontend
COPY frontend/dist ./frontend/dist

# Expose the default port
EXPOSE ${PORT}

# Run the server
CMD ["node", "server.js"]
