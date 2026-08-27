import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "EXPRESS OS",
  description: "Your life, in command.",
  manifest: "/manifest.webmanifest",
  applicationName: "EXPRESS",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    title: "EXPRESS",
    // The shell paints its own dark background; a translucent bar lets the
    // page colour run under the status bar instead of showing a white strip.
    statusBarStyle: "black-translucent",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#090B11",
  width: "device-width",
  initialScale: 1,
  // Lets the page extend under the notch and home indicator; the safe-area
  // tokens in globals.css then keep content clear of both.
  viewportFit: "cover",
  // Deliberately zoomable — capping zoom is an accessibility regression.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
