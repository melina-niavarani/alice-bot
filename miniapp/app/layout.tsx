import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'آلیس | مجموعه ورزشی',description:'خدمات، سانس‌ها و تعرفه‌های بدنسازی، استخر و سونای آلیس تهرانپارس',icons:{icon:'/favicon.svg',shortcut:'/favicon.svg'}};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="fa" dir="rtl"><head><link rel="preload" href="/fonts/Vazirmatn.woff2" as="font" type="font/woff2" crossOrigin="anonymous" /></head><body>{children}</body></html>}
