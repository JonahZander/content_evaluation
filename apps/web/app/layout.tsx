import type { Metadata } from "next";
import "./globals.css";
import DotGrid from "@/components/DotGrid/DotGrid";

export const metadata: Metadata = {
  title: "Content Evaluation",
  description: "Editorial review workbench for multi-agent content evaluation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <DotGrid dotSize={4} gap={28} baseColor="#d4d4d4" activeColor="#9a9a9a" proximity={120} />
        {children}
      </body>
    </html>
  );
}
