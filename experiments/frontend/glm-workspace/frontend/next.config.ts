import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendPort = process.env.BACKEND_PORT || "8080";
    return [
      {
        source: "/api/search",
        destination: `http://localhost:${backendPort}/v1/msmarco-v1-passage/search`,
      },
    ];
  },
};

export default nextConfig;
