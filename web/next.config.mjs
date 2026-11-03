/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  typescript: {
    tsconfigPath: process.env.ALPHAOS_NETLIFY_BUILD === "true"
      ? "tsconfig.netlify.json"
      : "tsconfig.json",
  },
};

export default nextConfig;
