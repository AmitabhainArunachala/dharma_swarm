import type { Metadata } from "next";
import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/Sidebar";
import { AmbientParticles } from "@/components/layout/AmbientParticles";
import { ScanLines } from "@/components/layout/ScanLines";
import { ChatOverlayWrapper } from "@/components/chat/ChatOverlayWrapper";
import "./globals.css";

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------

export const metadata: Metadata = {
  title: "DHARMA COMMAND",
  description: "Neo-Tokyo swarm visualization dashboard",
};

// ---------------------------------------------------------------------------
// Root layout
// ---------------------------------------------------------------------------

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-sumi-950 font-body text-torinoko antialiased">
        <Providers>
          {/* Ambient effects */}
          <AmbientParticles />
          <ScanLines />

          {/* Layout shell: sidebar + main */}
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="ml-[260px] flex-1">
              {children}
            </main>
          </div>

          {/* Floating chat overlay */}
          <ChatOverlayWrapper />
        </Providers>
      </body>
    </html>
  );
}
