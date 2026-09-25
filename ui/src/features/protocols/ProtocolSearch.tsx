// Protocol lookup (P9, UX_PLAN §5.9b): the county's own passages, quoted verbatim with document, section, page and
// effective date. A local model only picks which passages answer; nothing here paraphrases or recommends.
import { useEffect, useRef, useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/kit";
import { useHerald } from "@/lib/store";
import type { ProtocolAnswer, ProtocolPassage } from "@/lib/types";

type Outcome = { answer: ProtocolAnswer } | { error: string };

async function search(q: string): Promise<Outcome> {
  try {
    const r = await fetch(`/api/protocols/search?${new URLSearchParams({ q, k: "5" })}`, { signal: AbortSignal.timeout(30000) });
    if (r.status === 404) return { error: "Protocol lookup is off on this vehicle." };
    if (r.status === 503) {
      const building = (await r.json().catch(() => ({}))).detail?.building;
      return { error: building ? "The county documents are still loading. Try again in a moment." : "Protocol lookup isn't ready. Try again." };
    }
    if (!r.ok) throw new Error(String(r.status));
    return { answer: await r.json() };
  } catch {
    return { error: "The Herald server didn't answer. Try again." };
  }
}

const citation = (p: ProtocolPassage) =>
  `${p.doc} §${p.section}, page ${p.page}, effective ${p.effective ?? "date not printed"}`;

function Passage({ p, first }: { p: ProtocolPassage; first: boolean }) {
  return (
    <details open={first} className="rounded-[14px] bg-surface-2 p-3">
      <summary className="cursor-pointer">
        <span className="font-semibold">{p.heading}</span>
        <span className="block text-meta text-text-muted">{citation(p)}</span>
      </summary>
      {p.parents.length > 0 && <p className="mt-2 text-meta text-text-muted">{p.parents.join(" › ")}</p>}
      <p className="mt-2 whitespace-pre-wrap">{p.text}</p>
      {p.text_layer_uncertain && (
        <p className="mt-2 text-meta text-medium-fg">
          The printed page may differ from the extracted text.{" "}
          <a className="underline" href={`/api/protocols/${encodeURIComponent(p.doc)}/page/${p.page}`} target="_blank" rel="noreferrer">
            View the printed page
          </a>
        </p>
      )}
    </details>
  );
}

/** A side sheet the host screen opens; `query` pre-fills and runs a search (e.g. from a score's county-policy link). */
export function ProtocolSearch({ open, query = "", onClose }: { open: boolean; query?: string; onClose: () => void }) {
  const live = useHerald((s) => s.source === "live");
  const review = useHerald((s) => s.snapshot?.protocols?.review_required);
  const [q, setQ] = useState(query);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState<"no" | "yes" | "slow">("no");
  const seq = useRef(0);

  async function run(text: string) {
    if (!live || !text.trim()) return;
    const mine = ++seq.current;              // a newer search replaces an older one still in flight
    setBusy("yes");
    const slow = setTimeout(() => seq.current === mine && setBusy("slow"), 2000);
    const res = await search(text.trim());
    clearTimeout(slow);
    if (seq.current !== mine) return;
    setOutcome(res);
    setBusy("no");
  }

  useEffect(() => {
    if (!open) return;
    setQ(query);
    setOutcome(null);
    void run(query);
  }, [open, query]);                         // re-run only when the sheet opens or the host changes the query

  const answer = outcome && "answer" in outcome ? outcome.answer : null;
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-[36rem] max-w-full gap-0 border-border-subtle bg-surface-3 sm:max-w-xl">
        <SheetHeader className="px-6 pt-6">
          <SheetTitle className="text-value font-bold">County protocols</SheetTitle>
          <SheetDescription className="text-body text-text-muted">The county's own text, quoted with its section and effective date.</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-6 text-body">
          {review && review.length > 0 && <p className="text-medium-fg">Protocol updated: review county settings ({review.join(", ")}).</p>}
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(q); }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} disabled={!live} aria-label="Search the county protocols"
              placeholder="e.g. stroke destination" className="h-10 min-w-0 flex-1 rounded-[var(--radius-control)] border border-border-subtle bg-surface-2 px-3" />
            <Button type="submit" variant="primary" disabled={!live || busy !== "no" || !q.trim()}>Search</Button>
          </form>
          {!live && <p className="text-text-muted">Replay: protocol search needs the live server.</p>}
          {busy !== "no" && <p role="status" className="text-text-muted">{busy === "slow" ? "Still waiting for the server…" : "Searching the county documents…"}</p>}
          {busy === "no" && outcome && "error" in outcome && <p role="alert" className="text-high-fg">{outcome.error}</p>}
          {busy === "no" && answer && <>
            {answer.answerable === false && <p className="font-semibold">The county documents don't cover this. Closest passages:</p>}
            {answer.results.length === 0 && <p className="text-text-muted">No passage matches.</p>}
            {answer.results.map((p, i) => <Passage key={`${p.doc}:${p.section}:${p.page}`} p={p} first={i === 0} />)}
          </>}
        </div>
      </SheetContent>
    </Sheet>
  );
}
