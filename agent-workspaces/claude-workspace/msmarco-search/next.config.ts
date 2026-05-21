import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow configuring the backend port via env var; default 8080
  env: {
    ANSERINI_BACKEND_URL:
      process.env.ANSERINI_BACKEND_URL ??
      `http://localhost:${process.env.ANSERINI_BACKEND_PORT ?? "8080"}`,
  },
};

export default nextConfig;
