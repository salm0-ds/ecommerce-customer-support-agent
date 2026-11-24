/** @type {import('next').NextConfig} */
const nextConfig = {
  // Build the site as plain HTML/CSS/JS files (in `out/`) so Cloudflare can serve
  // them directly. All dynamic work (chat) happens on the FastAPI backend on Render.
  output: 'export',
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
