import { useRef, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Grip, LayoutGrid, LockKeyhole, RotateCcw } from "lucide-react";

const DEFAULT_ORDER = ["capture", "handoff"] as const;
export type WorkspaceCardId = typeof DEFAULT_ORDER[number];
const STORAGE_KEY = "herald.workspace-layout.v1";
export function validOrder(value: unknown): WorkspaceCardId[] {
  return Array.isArray(value) && value.length === DEFAULT_ORDER.length && new Set(value).size === DEFAULT_ORDER.length
    && value.every((id) => DEFAULT_ORDER.includes(id)) ? value : [...DEFAULT_ORDER];
}
function readOrder() {
  try { return validOrder(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")); }
  catch { return [...DEFAULT_ORDER]; }
}
export function WorkspaceCards({ cards }: { cards: Record<WorkspaceCardId, { label: string; content: ReactNode }> }) {
  const [saved, setSaved] = useState(readOrder);
  const [order, setOrder] = useState(saved);
  const [editing, setEditing] = useState(false);
  const [dragging, setDragging] = useState<WorkspaceCardId | null>(null);
  const [target, setTarget] = useState<WorkspaceCardId | null>(null);
  const [message, setMessage] = useState("");
  const arrangeButton = useRef<HTMLButtonElement>(null);
  const resetButton = useRef<HTMLButtonElement>(null);
  const restoreFocus = () => requestAnimationFrame(() => arrangeButton.current?.focus());
  const drag = useRef<{ id: WorkspaceCardId; target: WorkspaceCardId | null } | null>(null);
  const move = (id: WorkspaceCardId, to: WorkspaceCardId) => {
    setOrder((current) => { const next = [...current]; next.splice(next.indexOf(id), 1); next.splice(current.indexOf(to), 0, id); return next; });
    setMessage(`${cards[id].label} moved. Save layout to keep this order.`);
  };
  const finishDrag = (commit: boolean) => {
    if (commit && drag.current?.target) move(drag.current.id, drag.current.target);
    drag.current = null; setDragging(null); setTarget(null);
  };
  function save() {
    setSaved(order); setEditing(false); restoreFocus();
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(order)); setMessage("Layout saved and locked."); }
    catch { setMessage("Layout locked for this visit. This browser could not save your preference."); }
  }
  return <section className="workspace-modules" aria-label="Capture and handoff workspace">
    <div className="cabin-section-label workspace-toolbar">
      <div><h2>Your workspace</h2><p>Capture what happens. Review before sharing.</p></div>
      {editing ? <div className="cabin-actions">
        <button ref={resetButton} className="cabin-button" onClick={() => { setOrder([...DEFAULT_ORDER]); setMessage("Default order restored. Save to keep it."); }}><RotateCcw size={17} />Reset</button>
        <button className="cabin-button" onClick={() => { setOrder(saved); setEditing(false); finishDrag(false); setMessage("Layout changes cancelled."); restoreFocus(); }}>Cancel</button>
        <button className="cabin-button primary" onClick={save}><LockKeyhole size={17} />Save layout</button>
      </div> : <button ref={arrangeButton} className="cabin-button workspace-customize" onClick={() => { setEditing(true); setMessage(""); requestAnimationFrame(() => resetButton.current?.focus()); }}><LayoutGrid size={18} />Arrange cards</button>}
    </div>
    {editing && <p className="workspace-edit-hint">Drag a handle, or use the move buttons. Patient, readings, alerts and microphone controls stay pinned.</p>}
    <p className="sr-only" role="status">{message}</p>
    <div className={`workspace-grid ${editing ? "is-editing" : ""}`}>
      {order.map((id, index) => <article key={id} data-workspace-card={id} aria-label={cards[id].label}
        className={`workspace-card ${dragging === id ? "is-dragging" : ""} ${target === id ? "is-drop-target" : ""}`}>
        {editing && <div className="workspace-move-tools">
          <button className="workspace-drag" aria-label={`Drag ${cards[id].label}. Use move buttons as an alternative.`}
            onPointerDown={(event) => { if (event.button !== 0) return; event.currentTarget.setPointerCapture(event.pointerId); drag.current = { id, target: null }; setDragging(id); }}
            onPointerMove={(event) => { if (!drag.current) return; const over = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-workspace-card]")?.dataset.workspaceCard as WorkspaceCardId | undefined;
              const next = over && over !== id && DEFAULT_ORDER.includes(over) ? over : null; drag.current.target = next; setTarget(next); }}
            onPointerUp={() => finishDrag(true)} onPointerCancel={() => finishDrag(false)} onLostPointerCapture={() => finishDrag(false)}
            onKeyDown={(event) => { if (event.key === "Escape") finishDrag(false); }}><Grip size={20} />Move card</button>
          <button aria-label={`Move ${cards[id].label} earlier`} disabled={index === 0} onClick={() => move(id, order[index - 1])}><ArrowUp size={20} /></button>
          <button aria-label={`Move ${cards[id].label} later`} disabled={index === order.length - 1} onClick={() => move(id, order[index + 1])}><ArrowDown size={20} /></button>
        </div>}
        {cards[id].content}
      </article>)}
    </div>
  </section>;
}
