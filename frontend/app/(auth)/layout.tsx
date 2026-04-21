"use client";

import { useI18n } from "@/hooks/use-i18n";
import { LocaleSwitch } from "@/components/layout/locale-switch";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { messages } = useI18n();

  return (
    <main className="grid min-h-screen bg-background md:grid-cols-[minmax(0,1.2fr)_560px]">
      <section className="hidden flex-col justify-between bg-gradient-to-br from-indigo-500 via-blue-500 to-sky-400 p-12 text-white md:flex">
        <div>
          <p className="text-sm uppercase tracking-[0.28em] text-white/70">
            {messages.authLayout.eyebrow}
          </p>
          <h1 className="mt-6 max-w-lg text-5xl font-semibold tracking-tight">
            {messages.authLayout.title}
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-white/82">
            {messages.authLayout.description}
          </p>
        </div>
        <div className="grid gap-4 rounded-[32px] bg-white/12 p-6 backdrop-blur">
          <p className="text-sm text-white/72">{messages.authLayout.listTitle}</p>
          <ul className="space-y-3 text-sm leading-7 text-white/90">
            {messages.authLayout.bullets.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>
      <section className="relative flex items-center justify-center px-4 py-10 md:px-10">
        <div className="absolute right-4 top-4 md:right-8 md:top-8">
          <LocaleSwitch />
        </div>
        {children}
      </section>
    </main>
  );
}
