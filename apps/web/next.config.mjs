/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // Next offers to write AGENTS.md and CLAUDE.md describing itself. The repo
  // keeps its own guidance, so decline rather than have them regenerate.
  agentRules: false,
}

export default config
