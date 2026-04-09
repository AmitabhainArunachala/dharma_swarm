import type { NextConfig } from "next";

const apiProxyTarget =
  process.env.DHARMA_API_PROXY_URL ?? "http://127.0.0.1:8420";

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
