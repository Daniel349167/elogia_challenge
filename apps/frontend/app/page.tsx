import { ChatPanel } from "@/components/chat-panel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-paper text-ink">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-8 md:px-8">
        <header className="mb-6 rounded-3xl border border-ink/10 bg-gradient-to-r from-pine to-rust p-6 text-paper shadow-panel">
          <p className="font-mono text-xs uppercase tracking-[0.2em]">Developer Challenge</p>
          <h1 className="mt-2 text-3xl font-bold md:text-4xl">IA para Analisis de Comprobantes</h1>
          <p className="mt-2 max-w-2xl text-sm text-paper/90 md:text-base">
            Envia comprobantes, estructura datos en JSON y consulta insights desde el chat.
          </p>
        </header>

        <ChatPanel />
      </div>
    </main>
  );
}
