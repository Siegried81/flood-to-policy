import React, { useMemo, useState } from "react";

/**
 * A table whose every header sorts the rows it is given.
 *
 * Each column is `{ label, sort, render, className }`: `sort(row)` returns the
 * value compared (a number or a string) and `render(row)` what the cell shows,
 * so a figure displayed as "12.3%" still sorts as the number behind it. A
 * column without `sort` is not clickable.
 *
 * It orders the rows the caller passed and nothing more. Each table here shows
 * a selection ("the 15 largest increases"), and re-sorting a column must not
 * quietly swap that selection for another one, or the heading above the table
 * would stop being true. Missing values sort last in both directions: a blank
 * is not the smallest number.
 */
export default function SortableTable({ columns, rows, rowKey, rowClassName }) {
  const [sortBy, setSortBy] = useState(null);
  const [ascending, setAscending] = useState(false);

  const ordered = useMemo(() => {
    if (sortBy === null || !columns[sortBy]?.sort) return rows;
    const value = columns[sortBy].sort;
    const missing = (v) => v === null || v === undefined || Number.isNaN(v);
    return [...rows].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      if (missing(x) || missing(y)) return missing(x) - missing(y);
      const order =
        typeof x === "string" || typeof y === "string"
          ? String(x).localeCompare(String(y))
          : x - y;
      return ascending ? order : -order;
    });
  }, [rows, columns, sortBy, ascending]);

  const click = (index) => {
    if (!columns[index].sort) return;
    if (index === sortBy) {
      setAscending(!ascending);
    } else {
      setSortBy(index);
      // Text reads A-Z first; a figure reads largest first, which is what
      // every table here was sorted by to begin with.
      setAscending(typeof columns[index].sort(rows[0] ?? {}) === "string");
    }
  };

  return (
    <table className="sortable">
      <thead>
        <tr>
          {columns.map((column, index) => (
            <th
              key={column.label}
              onClick={() => click(index)}
              className={column.sort ? "sortable-header" : undefined}
              aria-sort={
                index === sortBy ? (ascending ? "ascending" : "descending") : undefined
              }
              title={column.sort ? "Click to sort" : undefined}
            >
              {column.label}
              {index === sortBy ? (ascending ? " ▲" : " ▼") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ordered.map((row) => (
          <tr key={rowKey(row)} className={rowClassName?.(row)}>
            {columns.map((column) => (
              <td key={column.label} className={column.className}>
                {column.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
