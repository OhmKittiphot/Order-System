import type { CSSProperties, ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
}

/** Shared table styling, also used by tables that aren't built with DataTable. */
export const TABLE = {
  wrap: "surface overflow-x-auto rounded-3xl",
  table: "w-full border-collapse text-sm tabular-nums max-md:block",
  thead: "max-md:hidden",
  th: "border-b border-slate-100 bg-slate-50/70 px-5 py-3.5 text-left font-mono text-[0.6875rem] font-medium tracking-[0.12em] whitespace-nowrap text-slate-500 uppercase first:pl-6 last:pr-6",
  tbody: "divide-y divide-slate-100 max-md:block max-md:divide-y-0 max-md:space-y-2 max-md:p-2",
  tr: "relative transition-colors duration-200 max-md:block max-md:rounded-2xl max-md:border max-md:border-slate-100 max-md:px-1 max-md:py-2",
  td: "px-5 py-4 align-middle first:pl-6 last:pr-6 max-md:flex max-md:items-center max-md:justify-between max-md:gap-4 max-md:px-3 max-md:py-1.5 max-md:text-right max-md:first:pl-3 max-md:last:pr-3 max-md:before:text-left max-md:before:font-mono max-md:before:text-[0.6875rem] max-md:before:tracking-wider max-md:before:text-slate-500 max-md:before:uppercase max-md:before:content-[attr(data-label)]",
  num: "text-right whitespace-nowrap",
};

/** Accessible table; on narrow screens rows stack and each cell shows its header. */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  caption,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  caption?: string;
}) {
  return (
    <div className={TABLE.wrap}>
      <table className={TABLE.table}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className={TABLE.thead}>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`${TABLE.th} ${c.align === "right" ? "text-right" : ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={TABLE.tbody}>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row)}
              style={{ animationDelay: `${Math.min(i, 12) * 35}ms` } as CSSProperties}
              className={`${TABLE.tr} animate-rise ${
                onRowClick
                  ? "group/row cursor-pointer hover:bg-cobalt-50/50 focus-visible:-outline-offset-2 md:[&>td:first-child]:shadow-[inset_0_0_0_0_var(--color-cobalt-600)] md:hover:[&>td:first-child]:shadow-[inset_3px_0_0_0_var(--color-cobalt-600)]"
                  : "hover:bg-slate-50/60"
              }`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === "Enter") onRowClick(row);
                    }
                  : undefined
              }
              tabIndex={onRowClick ? 0 : undefined}
            >
              {columns.map((c) => (
                <td key={c.key} data-label={c.header} className={[TABLE.td, c.align === "right" ? TABLE.num : "", c.className ?? ""].join(" ")}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
