/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  env: {
    ALPHAOS_PREVIEW_DIAGNOSTICS: process.env.ALPHAOS_PREVIEW_DIAGNOSTICS === "true" ? "true" : "false",
  },
  typescript: {
    tsconfigPath: process.env.ALPHAOS_NETLIFY_BUILD === "true"
      ? "tsconfig.netlify.json"
      : "tsconfig.json",
  },
};

export default nextConfig;
