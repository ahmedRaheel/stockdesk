/** CSV cells preserve numeric values; untrusted strings cannot become formulas. */
export function csvText(rows: unknown[][]): string {
  const cell = (value: unknown) => {
    let text = value == null ? "" : String(value);
    if (typeof value !== "number" && /^[\s]*[=+@-]/u.test(text))
      text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  return "\uFEFF" + rows.map((row) => row.map(cell).join(",")).join("\r\n");
}
export function downloadCsv(name: string, rows: unknown[][]) {
  const url = URL.createObjectURL(
    new Blob([csvText(rows)], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
