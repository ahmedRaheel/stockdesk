import { t as tr } from "./i18n";
import { useEffect, useRef, useState } from "react";
import type { PlotlyHTMLElement } from "plotly.js";

/** Load the plotting runtime only when a chart is mounted; POS does not need it. */
export default function PlotlyChart({
  figure,
  onSelect,
}: {
  figure: any;
  onSelect?: (label: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const node = ref.current;
    if (!node || !figure) return;
    let cancelled = false;
    let dispose = () => {};
    setError("");
    import("plotly.js-dist-min")
      .then(async ({ default: Plotly }) => {
        if (cancelled) return;
        const chart = await Plotly.react(
          node,
          figure.data,
          {
            ...figure.layout,
            autosize: true,
            font: {
              family: "Segoe UI, Arial, sans-serif",
              color: "#526175",
              size: 12,
              ...figure.layout?.font,
            },
          },
          {
            responsive: true,
            displaylogo: false,
            modeBarButtonsToRemove: ["select2d", "lasso2d"],
            toImageButtonOptions: {
              format: "png",
              filename: "stockdesk-chart",
            },
          },
        );
        if (cancelled) {
          Plotly.purge(node);
          return;
        }
        if (onSelect)
          (chart as PlotlyHTMLElement).on("plotly_click", (e) =>
            onSelect(
              (e.points?.[0] as unknown as { label?: string })?.label || "",
            ),
          );
        const resize = new ResizeObserver(() => Plotly.Plots.resize(node));
        resize.observe(node);
        dispose = () => {
          resize.disconnect();
          Plotly.purge(node);
        };
      })
      .catch(() => {
        if (!cancelled) setError("The chart could not load. Refresh to retry.");
      });
    return () => {
      cancelled = true;
      dispose();
    };
  }, [figure, onSelect]);
  return (
    <div>
      {error && <p role="alert">{tr(error)}</p>}
      <div
        ref={ref}
        style={{ width: "100%", minHeight: 220 }}
        aria-label={tr("Interactive dashboard chart")}
      />
    </div>
  );
}
