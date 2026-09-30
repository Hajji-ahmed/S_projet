import { Banknote, CircleDollarSign, FileCheck, Landmark, Plus, TrendingUp } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";

import { ApiStatus } from "@/components/dev/ApiStatus";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { KpiCard } from "@/components/ui/KpiCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatAmount } from "@/lib/format";
import { STATUSES } from "@/types/status";

import { InteractiveDemo } from "./InteractiveDemo";

export const metadata: Metadata = { title: "Design System" };

type DemoRow = {
  id: string;
  bank: string;
  logo: string;
  balance: number;
  authorized: number;
  used: number;
  available: number;
  position: number;
};

// Données d'exemple pour la démonstration uniquement : aucune n'est calculée ni lue depuis l'API.
const DEMO_ROWS: DemoRow[] = [
  {
    id: "cih",
    bank: "CIH",
    logo: "cih",
    balance: 1200000,
    authorized: 800000,
    used: 300000,
    available: 500000,
    position: 1700000,
  },
  {
    id: "bp",
    bank: "BP",
    logo: "bp",
    balance: 650000,
    authorized: 600000,
    used: 200000,
    available: 400000,
    position: 1050000,
  },
  {
    id: "awb",
    bank: "Attijariwafa",
    logo: "attijariwafa",
    balance: 400000,
    authorized: 500000,
    used: 250000,
    available: 250000,
    position: 650000,
  },
  {
    id: "bmce",
    bank: "BMCE",
    logo: "bmce",
    balance: 200000,
    authorized: 300000,
    used: 150000,
    available: 150000,
    position: 350000,
  },
];

const amount = (value: number) => formatAmount(value);

const COLUMNS: Column<DemoRow>[] = [
  {
    key: "bank",
    header: "Banque",
    render: (row) => (
      <span className="flex items-center gap-3">
        <Image
          src={`/banques/${row.logo}.png`}
          alt=""
          width={28}
          height={28}
          className="h-7 w-7 rounded"
        />
        {row.bank}
      </span>
    ),
  },
  {
    key: "balance",
    header: "Solde bancaire",
    align: "right",
    render: (row) => amount(row.balance),
  },
  {
    key: "authorized",
    header: "Crédit autorisé",
    align: "right",
    render: (row) => amount(row.authorized),
  },
  { key: "used", header: "Crédit utilisé", align: "right", render: (row) => amount(row.used) },
  {
    key: "available",
    header: "Crédit disponible",
    align: "right",
    render: (row) => <span className="text-simtis-success">{amount(row.available)}</span>,
  },
  {
    key: "position",
    header: "Position disponible",
    align: "right",
    render: (row) => (
      <span className="font-medium text-simtis-primary">{amount(row.position)}</span>
    ),
  },
];

const DEMO_TOTAL = {
  bank: "Total",
  balance: amount(2450000),
  authorized: amount(2200000),
  used: amount(900000),
  available: <span className="text-simtis-success">{amount(1200000)}</span>,
  position: <span className="text-simtis-primary">{amount(3650000)}</span>,
};

export default function DesignSystemPage() {
  return (
    <>
      <PageHeader
        title="Design System"
        description="Composants du socle technique SIMTIS Finance. Toutes les données affichées sont des exemples."
        actions={
          <>
            <Button variant="secondary">Exporter</Button>
            <Button icon={Plus}>Importer un relevé</Button>
          </>
        }
      />

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Total soldes bancaires"
          value={formatAmount(2450000, "DH")}
          icon={Landmark}
          delta="+5.2%"
        />
        <KpiCard
          title="Crédit disponible"
          value={formatAmount(1200000, "DH")}
          icon={Banknote}
          delta="+3.1%"
        />
        <KpiCard
          title="Position disponible"
          value={formatAmount(3650000, "DH")}
          icon={TrendingUp}
          delta="+4.8%"
        />
        <KpiCard
          title="Opérations rapprochées"
          value="1 520"
          icon={FileCheck}
          delta="+12%"
          progress={85}
        />
      </div>

      <Card
        title="Position bancaire par banque"
        icon={CircleDollarSign}
        action={{ label: "Voir tout", href: "/position-bancaire" }}
      >
        <DataTable
          columns={COLUMNS}
          rows={DEMO_ROWS}
          getRowKey={(row) => row.id}
          footer={DEMO_TOTAL}
        />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Boutons">
          <div className="flex flex-wrap gap-3">
            <Button>Primaire</Button>
            <Button variant="secondary">Secondaire</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="ghost">Voir tout →</Button>
            <Button disabled>Désactivé</Button>
          </div>
        </Card>

        <Card title="Connexion à l'API">
          <ApiStatus />
        </Card>
      </div>

      <Card title="Badges de statut">
        <div className="flex flex-wrap gap-3">
          {STATUSES.map((status) => (
            <StatusBadge key={status} status={status} />
          ))}
        </div>
      </Card>

      <InteractiveDemo />
    </>
  );
}
