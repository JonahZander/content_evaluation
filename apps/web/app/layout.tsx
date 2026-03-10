import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Content Evaluation",
  description: "Editorial review workbench for multi-agent content evaluation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
