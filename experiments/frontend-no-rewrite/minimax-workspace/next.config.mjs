/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // We only call out to a single Anserini REST server on the backend port.
  // No image domains or rewrites are needed.
};

export default nextConfig;
