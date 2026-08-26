import type { Metadata } from 'next'
import { REPO, X } from '@/lib/site'
import './landing.css'

export const metadata: Metadata = {
  alternates: { canonical: '/' },
}

export default function Home() {
  return (
    <main className="page">
      <div className="stage">
        <div className="field" aria-hidden="true">
          <span className="you" />
        </div>

        <h1>You’re someone, not a datapoint.</h1>

        <p className="lede">
          A Chromium browser with the calls home taken out, and the extension
          API that content blockers actually need left in.
        </p>
      </div>

      <nav className="rail" aria-label="elsewhere">
        <a href={REPO} rel="noopener" aria-label="Source on GitHub" title="GitHub">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 1.8a10.2 10.2 0 0 0-3.23 19.88c.51.1.7-.22.7-.49v-1.9c-2.84.62-3.44-1.2-3.44-1.2-.47-1.18-1.14-1.5-1.14-1.5-.93-.63.07-.62.07-.62 1.03.07 1.57 1.06 1.57 1.06.91 1.57 2.4 1.11 2.99.85.09-.66.36-1.11.65-1.37-2.27-.26-4.65-1.13-4.65-5.04 0-1.11.4-2.02 1.05-2.74-.11-.26-.46-1.3.1-2.71 0 0 .86-.27 2.81 1.05a9.7 9.7 0 0 1 5.12 0c1.95-1.32 2.8-1.05 2.8-1.05.56 1.41.21 2.45.11 2.71.66.72 1.05 1.63 1.05 2.74 0 3.92-2.39 4.78-4.66 5.03.37.32.7.94.7 1.9v2.81c0 .27.18.6.7.49A10.2 10.2 0 0 0 12 1.8Z" />
          </svg>
        </a>
        <a href={X} rel="noopener" aria-label="On X" title="X">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M18.9 2.5h3.4l-7.5 8.6 8.8 11.6h-6.9l-5.4-7.1-6.2 7.1H1.7l7.9-9L1.2 2.5h7l5.1 6.7 5.6-6.7Zm-1.2 18.2h1.9L6.6 4.4H4.6l13.1 16.3Z" />
          </svg>
        </a>
      </nav>
    </main>
  )
}
