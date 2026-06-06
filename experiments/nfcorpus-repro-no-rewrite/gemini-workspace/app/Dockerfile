FROM eclipse-temurin:21-jdk-jammy

WORKDIR /app

# Install Node.js
RUN apt-get update && apt-get install -y curl jq wget bash && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

# Download Anserini fatjar
RUN ANSERINI_VERSION="$(curl -sS https://repo1.maven.org/maven2/io/anserini/anserini/maven-metadata.xml | sed -n 's:.*<release>\(.*\)</release>.*:\1:p')" && \
    wget -q "https://repo1.maven.org/maven2/io/anserini/anserini/${ANSERINI_VERSION}/anserini-${ANSERINI_VERSION}-fatjar.jar" -O anserini-fatjar.jar

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy application files
COPY . .

# Environment setup
ENV PORT=10000
ENV ANSERINI_JAR=/app/anserini-fatjar.jar

EXPOSE 10000

CMD ["node", "server.js"]
