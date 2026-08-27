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
  // Icons come from app/icon.svg and app/apple-icon.png by file convention; an
  // icons entry here would emit a second, competing link tag.
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

// No webfont and no analytics: a hosted font would carry the visitor's address
// to a third party before the page has painted.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
