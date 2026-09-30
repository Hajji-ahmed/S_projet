import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  /** Boutons ou sélecteurs alignés à droite du titre. */
  actions?: ReactNode;
};

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-[28px] leading-tight font-bold text-simtis-text lg:text-[30px]">
          {title}
        </h1>
        {description && <p className="mt-1 text-[15px] text-simtis-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}
