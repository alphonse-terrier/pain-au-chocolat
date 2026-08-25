import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // Vercel's default for /public assets is max-age=0, must-revalidate
        // -- a round trip per shard fetch. s-maxage + SWR gives CDN-level
        // caching, invalidated on each deploy (cf. plan).
        source: "/data/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=300, s-maxage=31536000, stale-while-revalidate=86400",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
