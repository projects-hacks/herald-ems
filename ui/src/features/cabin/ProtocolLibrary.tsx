import { useEffect, useRef, useState, type FormEvent } from "react";
import { BookOpen, ExternalLink, FileSearch, LoaderCircle, Search } from "lucide-react";
import { useHerald } from "@/lib/store";

interface Passage { doc: string; title: string | null; section: string; heading: string; page: number; text: string; effective: string | null; text_layer_uncertain?: boolean }
interface SearchResult { query: string; answerable: boolean | null; results: Passage[]; error?: string }

export function ProtocolLibrary() {
  const county = useHerald((s) => s.snapshot?.county);
  const status = useHerald((s) => s.snapshot?.protocols);
  const replay = useHerald((s) => s.source === "fixture");
  const disconnected = useHerald((s) => s.conn !== "open" || s.stale);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    request.current?.abort(); request.current = null; setResult(null); setError(""); setBusy(false);
    return () => { request.current?.abort(); request.current = null; };
  }, [county?.id, replay, disconnected]);
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || replay || disconnected) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(""); setResult(null);
    const timeout = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await fetch(`/api/protocols/search?q=${encodeURIComponent(query.trim())}&k=5`, { signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 404 ? "Protocol lookup is not enabled on this vehicle." : response.status === 503 ? "The local protocol library is preparing. Try again shortly." : "The protocol library could not be reached. Try again.");
      const data: SearchResult = await response.json();
      if (request.current === controller) setResult(data);
    } catch (failure) {
      if (request.current === controller) setError(controller.signal.aborted ? "Search timed out. Try again." : failure instanceof Error ? failure.message : "Search failed. Try again.");
    } finally { clearTimeout(timeout); if (request.current === controller) setBusy(false); }
  }
  return <div className="protocol-library">
    <div className="protocol-intro"><span className="workspace-icon"><BookOpen size={25} /></span><div><h3>Your county. Your protocols.</h3><p>Search the locally stored {county?.name || "county"} documents. Results show the original passage and its source.</p></div></div>
    <form className="protocol-search" onSubmit={(event) => void search(event)}><Search size={21} aria-hidden /><input aria-label="Search county protocols" placeholder="Search a topic or ask a protocol question…" value={query} maxLength={500} onChange={(event) => setQuery(event.target.value)} />
      <button className="cabin-button primary" disabled={busy || !query.trim() || replay || disconnected}>{busy ? <LoaderCircle size={18} className="animate-spin" /> : <Search size={18} />}{busy ? "Searching" : "Search"}</button></form>
    {replay && <p className="protocol-notice">Protocol search is available when connected to the vehicle. This view is a recorded replay.</p>}
    {!replay && disconnected && <p className="protocol-notice">Reconnect to the vehicle to search its local library.</p>}
    {(status?.review_required.length ?? 0) > 0 && <p className="protocol-notice">Updated documents awaiting review: {status!.review_required.join(", ")}. Verify against the current county manual.</p>}
    {error && <p className="protocol-notice" role="alert">{error}</p>}
    <div role="status" aria-live="polite" className="workspace-caption">{busy ? "Searching local protocol passages…" : result ? `${result.results.length} source passages for “${result.query}”` : ""}</div>
    {result?.answerable === false && <p className="protocol-notice">The library could not establish an answer. These are related passages, not a recommendation.</p>}
    {result?.error && <p className="protocol-notice">Passage ranking is unavailable. Showing search matches for your review.</p>}
    {result && !result.results.length && <div className="protocol-empty"><FileSearch size={32} /><h3>No matching passages</h3><p>Try a different topic or a protocol number.</p></div>}
    {result?.results.map((passage, index) => <article className="protocol-passage" key={`${passage.doc}-${passage.section}-${index}`}><div><span className="readiness-badge">{passage.doc} · § {passage.section}</span><span className="workspace-caption">Effective {passage.effective || "date not recorded"}</span></div>
      <h3>{passage.heading || passage.title}</h3><p className="protocol-passage-text">{passage.text}</p>
      {passage.text_layer_uncertain && <p className="protocol-notice">Text extraction is uncertain. Check the original page.</p>}
      <a href={`/api/protocols/${encodeURIComponent(passage.doc)}/page/${passage.page}`} target="_blank" rel="noreferrer">{passage.title || passage.doc} · page {passage.page}<ExternalLink size={15} /></a>
    </article>)}
    {!result && !busy && <div className="protocol-documents"><h3><BookOpen size={18} />Available documents <span>{status?.documents.length ?? 0}</span></h3>
      {status?.documents.length ? <ul>{status.documents.map((doc) => <li key={doc.id}><BookOpen size={18} /><span><strong>{doc.title}</strong><small>{doc.id} · Effective {doc.effective || "date not recorded"}</small></span></li>)}</ul> : <div className="protocol-empty"><FileSearch size={32} /><p>{replay ? "Connect to the vehicle to access the protocol library." : "The document inventory will appear when the local library is ready."}</p></div>}
    </div>}
  </div>;
}
