import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: 'IRONCLAD · Code Guardian', description: 'Mission control for autonomous code repair.' };
export default function Layout({children}:Readonly<{children:React.ReactNode}>) {return <html lang="en"><body>{children}</body></html>}
