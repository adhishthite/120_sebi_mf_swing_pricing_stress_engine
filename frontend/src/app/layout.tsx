import type { Metadata } from 'next';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'SEBI MF Swing Pricing & Outflow Stress Cockpit',
  description: 'Asset Management Company Swing Pricing & Outflow Stress Engine Compliance Cockpit',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en' className='h-full antialiased font-sans'>
      <body className='min-h-full flex flex-col bg-background text-foreground'>{children}</body>
    </html>
  );
}
