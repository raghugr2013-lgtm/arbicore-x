import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { FileText, Loader2 } from "lucide-react";
import { MarkdownDoc } from "@/components/MarkdownDoc";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SECTION_ORDER = ["Overview", "Architecture", "Data Layer", "Integration", "Risk & Security", "Delivery Plan"];

export default function DocsViewer() {
  const [pkg, setPkg] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [doc, setDoc] = useState(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/docs-package`).then((res) => {
      setPkg(res.data);
      if (res.data.documents?.length) setActiveId(res.data.documents[0].id);
    }).catch(() => setError("Failed to load architecture package"));
  }, []);

  const loadDoc = useCallback((id) => {
    setLoadingDoc(true);
    axios.get(`${API}/docs-package/${id}`)
      .then((res) => setDoc(res.data))
      .catch(() => setError("Failed to load document"))
      .finally(() => setLoadingDoc(false));
  }, []);

  useEffect(() => { if (activeId) loadDoc(activeId); }, [activeId, loadDoc]);

  const sections = pkg
    ? SECTION_ORDER.map((s) => ({ name: s, docs: pkg.documents.filter((d) => d.section === s) })).filter((s) => s.docs.length)
    : [];

  return (
    <div className="term-body" data-testid="docs-viewer-page">
      <aside className="term-sidebar" data-testid="doc-sidebar">
        {error && <div className="sidebar-error" data-testid="load-error">{error}</div>}
        {!pkg && !error && <div className="sidebar-loading"><Loader2 className="spin" size={14} /> loading package…</div>}
        {sections.map((section) => (
          <div className="nav-section" key={section.name}>
            <div className="nav-section-title">{section.name}</div>
            {section.docs.map((d) => (
              <button key={d.id} data-testid={`nav-doc-${d.id}`}
                      className={`nav-item ${activeId === d.id ? "active" : ""}`}
                      onClick={() => setActiveId(d.id)}>
                <FileText size={13} />
                <span>{d.title}</span>
              </button>
            ))}
          </div>
        ))}
        {pkg && (
          <div className="sidebar-footer" data-testid="package-version">
            pkg v{pkg.version} · {pkg.documents.length} documents
          </div>
        )}
      </aside>
      <main className="term-content" data-testid="doc-viewer">
        {loadingDoc && <div className="doc-loading" data-testid="doc-loading"><Loader2 className="spin" size={18} /> loading document…</div>}
        {!loadingDoc && doc && (
          <>
            <div className="doc-breadcrumb" data-testid="doc-breadcrumb">
              {doc.section} <span className="crumb-sep">/</span> {doc.title}
            </div>
            <MarkdownDoc content={doc.content} />
          </>
        )}
      </main>
    </div>
  );
}
