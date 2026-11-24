import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";
import { Check, Lock, Star, X } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import { img, type PhotoRow } from "../api";

interface Props {
  pid: string;
  photos: PhotoRow[];
  onOpen: (index: number) => void;
  tile?: number;
  selectable?: boolean;
  picked?: Set<number>;
  onTogglePick?: (id: number, shift: boolean) => void;
  height?: string;
}

export function PhotoGrid({ pid, photos, onOpen, tile = 180, selectable, picked, onTogglePick, height = "calc(100vh - 210px)" }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const gap = 6;
  const cols = Math.max(2, Math.floor((width + gap) / (tile + gap)));
  const size = (width - gap * (cols - 1)) / cols;
  const rows = Math.ceil(photos.length / cols);
  const v = useVirtualizer({
    count: rows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => size + gap,
    overscan: 4,
  });
  useEffect(() => v.measure(), [size, v]);

  return (
    <div ref={parentRef} className="overflow-auto scroll-thin" style={{ height }}>
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {v.getVirtualItems().map((row) => (
          <div key={row.key} className="absolute inset-x-0 flex" style={{ top: row.start, gap, height: size }}>
            {Array.from({ length: cols }).map((_, c) => {
              const i = row.index * cols + c;
              const p = photos[i];
              if (!p) return <div key={c} style={{ width: size }} />;
              return (
                <Tile
                  key={p.id}
                  pid={pid}
                  p={p}
                  size={size}
                  onOpen={() => onOpen(i)}
                  selectable={selectable}
                  picked={picked?.has(p.id)}
                  onTogglePick={onTogglePick}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const Tile = memo(function Tile({
  pid,
  p,
  size,
  onOpen,
  selectable,
  picked,
  onTogglePick,
}: {
  pid: string;
  p: PhotoRow;
  size: number;
  onOpen: () => void;
  selectable?: boolean;
  picked?: boolean;
  onTogglePick?: (id: number, shift: boolean) => void;
}) {
  const inAlbum = p.album_rank != null && p.decision !== "rejected";
  return (
    <button
      onClick={(e) => (selectable && (e.metaKey || e.ctrlKey || e.shiftKey) ? onTogglePick?.(p.id, e.shiftKey) : onOpen())}
      className={clsx(
        "group relative shrink-0 overflow-hidden rounded-lg bg-raised focus-visible:ring-2 focus-visible:ring-accent",
        p.decision === "rejected" && "opacity-40",
        picked && "ring-2 ring-accent",
      )}
      style={{ width: size, height: size }}
      aria-label={`Photo ${p.id}`}
    >
      <img src={img.thumb(pid, p.id)} loading="lazy" decoding="async" alt="" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-1.5">
        <div className="flex gap-1">
          {p.decision === "selected" && (
            <span className="rounded-full bg-good p-1 text-black" title="Selected (locked)">
              <Lock size={11} />
            </span>
          )}
          {inAlbum && p.decision !== "selected" && (
            <span className="rounded-full bg-accent p-1 text-accent-ink" title="AI recommendation">
              <Check size={11} />
            </span>
          )}
          {p.decision === "rejected" && (
            <span className="rounded-full bg-bad p-1 text-black" title="Rejected">
              <X size={11} />
            </span>
          )}
        </div>
        {!!p.favorite && <Star size={16} className="fill-accent text-accent drop-shadow" />}
      </div>
      {!!p.rating && <div className="absolute bottom-1 start-1.5 text-xs text-accent drop-shadow">{"★".repeat(p.rating)}</div>}
      {selectable && (
        <span
          role="checkbox"
          aria-checked={!!picked}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePick?.(p.id, e.shiftKey);
          }}
          className={clsx(
            "absolute bottom-1.5 end-1.5 h-5 w-5 rounded-full border-2 transition-opacity",
            picked ? "border-accent bg-accent opacity-100" : "border-white/80 bg-black/30 opacity-0 group-hover:opacity-100",
          )}
        />
      )}
    </button>
  );
});
