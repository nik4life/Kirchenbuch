import "./globals.css";
export const metadata={title:"Kirchenbuch Stollhofen",description:"Digitalisate laden und als PDF zusammenführen"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="de"><body>{children}</body></html>}