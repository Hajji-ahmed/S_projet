"use client";

import { Building2, Check, ChevronDown, Plus, Settings2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useCompany } from "@/components/company/CompanyProvider";
import { SocieteFormModal } from "@/components/company/SocieteFormModal";
import { SocietesModal } from "@/components/company/SocietesModal";
import { buttonClasses } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { hasAnyPermission, PERMISSIONS } from "@/lib/permissions";
import type { CompanyAdmin } from "@/types/company";

const ITEM =
  "flex w-full items-center gap-2 rounded-[10px] px-3 py-2 text-left text-sm transition-colors hover:bg-simtis-surface focus-visible:bg-simtis-surface focus-visible:outline-none";

/** Fenêtre ouverte depuis le sélecteur (une seule à la fois). */
type Fenetre =
  | { type: "liste" }
  | { type: "ajout"; depuisListe: boolean }
  | { type: "edition"; societe: CompanyAdmin }
  | { type: "creee"; societe: CompanyAdmin };

/** Choix de la société active, dans l'en-tête. Un administrateur (`admin.settings`) peut aussi
 * ajouter, renommer, désactiver ou réactiver une société (17/11/2026). */
export function CompanySelector() {
  const { companies, company, setCompanyId, reload } = useCompany();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [fenetre, setFenetre] = useState<Fenetre | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const canManage = !!user && hasAnyPermission(user.permissions, [PERMISSIONS.ADMIN_SETTINGS]);

  useEffect(() => {
    if (!open) return;
    // Le focus va sur la société active à l'ouverture
    menuRef.current?.querySelector<HTMLElement>("[aria-checked='true']")?.focus();
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", closeOnOutsideClick);
    return () => window.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  if (!company) return null;

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      containerRef.current?.querySelector<HTMLElement>("button")?.focus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>("[role^='menuitem']") ?? [],
    );
    const index = items.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "ArrowDown" ? index + 1 : index - 1;
    items[(next + items.length) % items.length]?.focus();
  }

  function choisir(id: number) {
    setCompanyId(id);
    setOpen(false);
  }

  function ouvrir(f: Fenetre) {
    setOpen(false);
    setFenetre(f);
  }

  async function onSaved(societe: CompanyAdmin, mode: "create" | "edit") {
    await reload().catch(() => undefined);
    if (mode === "create") {
      setCompanyId(societe.id);
      setFenetre({ type: "creee", societe });
    } else {
      setFenetre({ type: "liste" });
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Société active : ${company.nom}`}
        className="flex h-10 max-w-[150px] items-center gap-2 rounded-[12px] border border-simtis-border bg-simtis-card px-3 text-sm font-medium text-simtis-primary-dark shadow-simtis transition-colors duration-200 hover:bg-simtis-surface focus-visible:border-simtis-primary focus-visible:ring-4 focus-visible:ring-simtis-primary/10 focus-visible:outline-none sm:max-w-none"
      >
        <Building2 className="hidden h-4 w-4 shrink-0 text-simtis-primary sm:block" aria-hidden />
        <span className="truncate">{company.nom}</span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-simtis-primary transition-transform duration-200",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Société active"
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 z-30 mt-2 w-64 rounded-card border border-simtis-border bg-simtis-card p-2 shadow-simtis-hover"
        >
          {companies.map((item) => {
            const active = item.id === company.id;
            return (
              <button
                key={item.id}
                type="button"
                role="menuitemradio"
                aria-checked={active}
                onClick={() => choisir(item.id)}
                className={cn(
                  ITEM,
                  active ? "font-semibold text-simtis-primary-dark" : "text-simtis-text",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{item.nom}</span>
                {active && <Check className="h-4 w-4 shrink-0 text-simtis-primary" aria-hidden />}
              </button>
            );
          })}

          {canManage && (
            <>
              <div className="my-1 border-t border-simtis-border" role="separator" />
              <button
                type="button"
                role="menuitem"
                onClick={() => ouvrir({ type: "ajout", depuisListe: false })}
                className={cn(ITEM, "text-simtis-primary")}
              >
                <Plus className="h-4 w-4 shrink-0" aria-hidden />
                Ajouter une société…
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => ouvrir({ type: "liste" })}
                className={cn(ITEM, "text-simtis-text")}
              >
                <Settings2 className="h-4 w-4 shrink-0 text-simtis-muted" aria-hidden />
                Gérer les sociétés…
              </button>
            </>
          )}
        </div>
      )}

      {fenetre?.type === "liste" && (
        <SocietesModal
          onClose={() => setFenetre(null)}
          onAdd={() => setFenetre({ type: "ajout", depuisListe: true })}
          onEdit={(societe) => setFenetre({ type: "edition", societe })}
          onChanged={() => void reload().catch(() => undefined)}
        />
      )}
      {fenetre?.type === "ajout" && (
        <SocieteFormModal
          onClose={() => setFenetre(fenetre.depuisListe ? { type: "liste" } : null)}
          onSaved={onSaved}
        />
      )}
      {fenetre?.type === "edition" && (
        <SocieteFormModal
          societe={fenetre.societe}
          onClose={() => setFenetre({ type: "liste" })}
          onSaved={onSaved}
        />
      )}
      {fenetre?.type === "creee" && (
        <Modal
          open
          title="Société créée"
          onClose={() => setFenetre(null)}
          footer={
            <>
              <button
                type="button"
                onClick={() => setFenetre(null)}
                className={buttonClasses("secondary")}
              >
                Fermer
              </button>
              <Link
                href="/comptes"
                onClick={() => setFenetre(null)}
                className={buttonClasses("primary")}
              >
                Créer ses comptes
              </Link>
            </>
          }
        >
          <p>
            La société <strong>{fenetre.societe.nom}</strong> ({fenetre.societe.code}) est créée et
            devient la société active.
          </p>
          <p className="mt-2 text-simtis-muted">
            Ses écrans restent vides tant qu&apos;aucun compte bancaire n&apos;est créé.
          </p>
        </Modal>
      )}
    </div>
  );
}
