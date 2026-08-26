import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'
import { DESCRIPTION, SITE, TITLE } from '@/lib/site'
import './root.css'

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: TITLE,
  description: DESCRIPTION,
  applicationName: 'shiemi',
  robots: { index: true, follow: true },
  // No icons entry: app/icon.png and app/apple-icon.png are picked up by file
  // convention, which fingerprints them and fills in the sizes. Declaring a
  // path here as well would emit a second, competing link tag.
  openGraph: {
    type: 'website',
    siteName: 'shiemi',
    locale: 'en_US',
    url: SITE,
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: { card: 'summary', title: TITLE, description: DESCRIPTION },
}

export const viewport: Viewport = {
  themeColor: '#0d0d0c',
}

// No webfont link, and no analytics. A site for a browser that strips out calls
// to Google should not open by making one, and a hosted font is exactly that: a
// request carrying the visitor's address to a third party before the page has
// even painted. The type is whatever the reader's machine already has.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
