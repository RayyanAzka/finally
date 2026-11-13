/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: false,
  // Dev only: proxy API to the FastAPI backend (ignored by static export build).
};
export default nextConfig;
