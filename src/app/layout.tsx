import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NGX investment literacy",
    template: "%s | NGX investment literacy",
  },
  description:
    "Plain-language explainers and sourced company profiles for companies listed on the Nigerian Exchange.",
};

const NAV = [
  { href: "/basics", label: "Basics" },
  { href: "/companies", label: "Companies" },
  { href: "/ask", label: "Ask" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-NG">
      <body className="min-h-screen flex flex-col">
        <header className="border-b border-[var(--color-rule)]">
          <div className="mx-auto w-full max-w-4xl px-4 py-4 flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <Link href="/" className="font-serif text-lg tracking-tight">
              NGX investment literacy
            </Link>
            <nav className="flex gap-5 text-sm text-[var(--color-ink-soft)]">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="hover:text-[var(--color-accent)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-10">{children}</main>

        <footer className="border-t border-[var(--color-rule)] mt-16">
          <div className="mx-auto w-full max-w-4xl px-4 py-6 text-sm text-[var(--color-ink-faint)] space-y-2">
            <p>
              This site explains concepts and reports figures that companies have
              themselves disclosed, with the source document and date attached to each
              one. It does not give investment advice and does not tell you what to buy
              or sell.
            </p>
            <p>
              For advice on your own circumstances, speak to an adviser registered with
              the Securities and Exchange Commission of Nigeria.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
