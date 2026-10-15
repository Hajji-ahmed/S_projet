"use client";

import { ChevronDown, History, ServerCog } from "lucide-react";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { DateInput, Field, Select } from "@/components/ui/Field";
import { FilterBar } from "@/components/ui/FilterBar";
import { LoadingState } from "@/components/ui/LoadingState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { cn } from "@/lib/cn";
import { champLisible, filtreActif, valeurLisible } from "@/lib/historique";
import { formatDateTime } from "@/lib/statements";
import { getDetailHistorique, getFiltresHistorique, getHistorique } from "@/services/historique";
import type {
  DetailHistorique,
  FiltresHistorique,
  LigneHistorique,
  PageHistorique,
  RechercheHistorique,
} from "@/types/historique";

const VIDE: RechercheHistorique = {
  page: 1,
  user_id: "",
  action: "",
  entite: "",
  from: "",
  to: "",
};

/** Historique (P16.2) : qui a fait quoi, quand, avec l'avant et l'après de chaque action. */
export function HistoriqueView() {
  const [recherche, setRecherche] = useState<RechercheHistorique>(VIDE);
  const [resultat, setResultat] = useState<{ cle: string; page: PageHistorique } | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [filtres, setFiltres] = useState<FiltresHistorique | null>(null);
  const [ouverte, setOuverte] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const cle = JSON.stringify(recherche) + version;
  const periodeInvalide =
    recherche.from !== "" && recherche.to !== "" && recherche.from > recherche.to;

  useEffect(() => {
    getFiltresHistorique().then(setFiltres, () => undefined);
  }, []);

  useEffect(() => {
    if (periodeInvalide) return;
    let annule = false;
    getHistorique(recherche).then(
      (page) => {
        if (annule) return;
        setResultat({ cle, page });
        setErreur(null);
      },
      () => {
        if (!annule) setErreur(cle);
      },
    );
    return () => {
      annule = true;
    };
  }, [recherche, cle, periodeInvalide]);

  function changer(champ: keyof RechercheHistorique, valeur: string) {
    setOuverte(null);
    setRecherche((r) => ({ ...r, [champ]: valeur, page: 1 }));
  }

  const page = resultat?.cle === cle ? resultat.page : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Historique"
        description="Journal des opérations sensibles : qui, quand, et les valeurs avant / après"
      />

      <FilterBar active={filtreActif(recherche)} onReset={() => setRecherche(VIDE)}>
        <div className="w-full sm:w-[200px]">
          <Field label="Utilisateur" htmlFor="histo-user">
            <Select
              id="histo-user"
              value={recherche.user_id}
              onChange={(e) => changer("user_id", e.target.value)}
              placeholder="Tous"
              options={(filtres?.utilisateurs ?? []).map((u) => ({
                value: String(u.id),
                label: u.nom,
              }))}
            />
          </Field>
        </div>
        <div className="w-full sm:w-[260px]">
          <Field label="Action" htmlFor="histo-action">
            <Select
              id="histo-action"
              value={recherche.action}
              onChange={(e) => changer("action", e.target.value)}
              placeholder="Toutes"
              options={(filtres?.actions ?? []).map((a) => ({
                value: a.code,
                label: `${a.libelle} (${a.nb ?? 0})`,
              }))}
            />
          </Field>
        </div>
        <div className="w-full sm:w-[200px]">
          <Field label="Objet" htmlFor="histo-entite">
            <Select
              id="histo-entite"
              value={recherche.entite}
              onChange={(e) => changer("entite", e.target.value)}
              placeholder="Tous"
              options={(filtres?.entites ?? []).map((e) => ({ value: e.code, label: e.libelle }))}
            />
          </Field>
        </div>
        <div className="w-full sm:w-[160px]">
          <Field label="Du" htmlFor="histo-from">
            <DateInput
              id="histo-from"
              value={recherche.from}
              onChange={(e) => changer("from", e.target.value)}
            />
          </Field>
        </div>
        <div className="w-full sm:w-[160px]">
          <Field label="Au" htmlFor="histo-to">
            <DateInput
              id="histo-to"
              value={recherche.to}
              onChange={(e) => changer("to", e.target.value)}
            />
          </Field>
        </div>
      </FilterBar>

      <Card title="Journal" icon={History}>
        {periodeInvalide ? (
          <p className="text-sm text-simtis-danger-fg">
            La date de début doit précéder la date de fin.
          </p>
        ) : erreur === cle ? (
          <ErrorState
            message="Impossible de charger l'historique."
            onRetry={() => setVersion((n) => n + 1)}
          />
        ) : page === null ? (
          <LoadingState rows={8} />
        ) : page.items.length === 0 ? (
          <p className="py-8 text-center text-sm text-simtis-muted">
            Aucune action ne correspond à ces filtres.
          </p>
        ) : (
          <>
            <ul className="divide-y divide-simtis-border">
              {page.items.map((ligne) => (
                <Entree
                  key={ligne.id}
                  ligne={ligne}
                  ouverte={ouverte === ligne.id}
                  onToggle={() => setOuverte((id) => (id === ligne.id ? null : ligne.id))}
                />
              ))}
            </ul>
            <Pagination
              label="Pages de l'historique"
              page={page.page}
              pages={page.pages}
              total={page.total}
              noun="action"
              onPage={(n) => {
                setOuverte(null);
                setRecherche((r) => ({ ...r, page: n }));
              }}
            />
          </>
        )}
      </Card>
    </div>
  );
}

function Entree({
  ligne,
  ouverte,
  onToggle,
}: {
  ligne: LigneHistorique;
  ouverte: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={ouverte}
        className={cn(
          "flex w-full items-start gap-3 rounded-[10px] px-2 py-3 text-left transition-colors duration-150 hover:bg-simtis-surface",
          ouverte && "bg-simtis-surface",
        )}
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-simtis-light text-xs font-semibold text-simtis-primary">
          {ligne.utilisateur ? (
            ligne.utilisateur.charAt(0).toUpperCase()
          ) : (
            <ServerCog className="h-4 w-4" aria-hidden />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-simtis-text">
            <span className="text-simtis-muted tabular-nums">
              {formatDateTime(ligne.created_at)}
            </span>
            {" — "}
            <span className="font-medium">{ligne.utilisateur ?? "Système"}</span>
            {" — "}
            <span className="font-semibold text-simtis-primary-dark">{ligne.action_libelle}</span>
          </span>
          <span className="mt-0.5 block truncate text-[13px] text-simtis-muted">
            {ligne.entite_libelle}
            {ligne.entite_id && ` n° ${ligne.entite_id}`}
            {ligne.resume && ` — ${ligne.resume}`}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-simtis-muted transition-transform duration-200",
            ouverte && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {ouverte && <Detail id={ligne.id} />}
    </li>
  );
}

function Detail({ id }: { id: number }) {
  const [detail, setDetail] = useState<DetailHistorique | null>(null);
  const [erreur, setErreur] = useState(false);

  useEffect(() => {
    let annule = false;
    getDetailHistorique(id).then(
      (d) => {
        if (!annule) setDetail(d);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [id]);

  if (erreur)
    return <p className="px-2 pb-3 text-sm text-simtis-danger-fg">Détail indisponible.</p>;
  if (!detail) return <LoadingState rows={2} />;
  return (
    <div className="mx-2 mb-3 space-y-2">
      {detail.differences.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucune valeur enregistrée pour cette action.</p>
      ) : (
        <div className="overflow-x-auto rounded-[12px] border border-simtis-border">
          <table className="w-full text-[13px]">
            <thead className="bg-simtis-light/60 text-left text-simtis-primary-dark">
              <tr>
                <th className="px-3 py-2 font-semibold">Champ</th>
                <th className="px-3 py-2 font-semibold">Avant</th>
                <th className="px-3 py-2 font-semibold">Après</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-simtis-border">
              {detail.differences.map((d) => (
                <tr key={d.champ} className={d.modifie ? "bg-simtis-warning-bg/40" : undefined}>
                  <td className="px-3 py-2 align-top font-medium whitespace-nowrap text-simtis-text">
                    {champLisible(d.champ)}
                  </td>
                  <td className="max-w-[420px] px-3 py-2 align-top break-words text-simtis-muted">
                    {valeurLisible(d.avant)}
                  </td>
                  <td
                    className={cn(
                      "max-w-[420px] px-3 py-2 align-top break-words",
                      d.modifie ? "font-medium text-simtis-text" : "text-simtis-muted",
                    )}
                  >
                    {valeurLisible(d.apres)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detail.ip && <p className="text-xs text-simtis-muted">Adresse IP : {detail.ip}</p>}
    </div>
  );
}
