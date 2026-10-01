import type { Metadata } from "next";
import Image from "next/image";
import { Suspense } from "react";

import { LoginForm } from "@/components/auth/LoginForm";
import { Skeleton } from "@/components/ui/LoadingState";

export const metadata: Metadata = { title: "Connexion" };

function FormFallback() {
  return (
    <div className="space-y-5" aria-hidden>
      <Skeleton className="h-[62px] w-full" />
      <Skeleton className="h-[62px] w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-simtis-background px-4 py-10">
      <div className="w-full max-w-[400px]">
        <section className="rounded-[14px] border border-simtis-border bg-simtis-card p-6 shadow-simtis sm:p-8">
          <Image
            src="/logo-simtis.png"
            alt="SIMTIS — Printing & Weaving"
            width={373}
            height={135}
            priority
            className="mx-auto h-auto w-[168px]"
          />
          <h1 className="mt-6 text-center text-[22px] font-bold text-simtis-text">Connexion</h1>
          <p className="mt-1 mb-6 text-center text-sm text-simtis-muted">
            Trésorerie et rapprochement bancaire
          </p>
          {/* useSearchParams (paramètre ?next=) doit être sous Suspense pour la génération statique */}
          <Suspense fallback={<FormFallback />}>
            <LoginForm />
          </Suspense>
        </section>
        <p className="mt-6 text-center text-xs text-simtis-muted">SIMTIS Finance · v1.0.0</p>
      </div>
    </main>
  );
}
