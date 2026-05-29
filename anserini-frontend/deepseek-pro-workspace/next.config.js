/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    BACKEND_PORT: process.env.BACKEND_PORT || '8080',
    BACKEND_HOST: process.env.BACKEND_HOST || 'localhost',
  },
};

module.exports = nextConfig;
