import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "loose",
  theme: "base",
  themeVariables: {
    background: "#0d1218",
    primaryColor: "#141b24",
    primaryTextColor: "#d7e1ec",
    primaryBorderColor: "#2a3644",
    lineColor: "#4a5b6e",
    secondaryColor: "#1a2530",
    tertiaryColor: "#10161e",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "13px",
    noteBkgColor: "#1d2733",
    noteTextColor: "#c5d2e0",
    noteBorderColor: "#2a3644",
    actorBkg: "#141b24",
    actorTextColor: "#d7e1ec",
    actorBorder: "#3b4c5e",
    signalColor: "#7a8da1",
    signalTextColor: "#aebccb",
    labelBoxBkgColor: "#1a2530",
    labelTextColor: "#d7e1ec",
    loopTextColor: "#ffb224",
    altSectionBkgColor: "#10161e",
    edgeLabelBackground: "#10161e",
    clusterBkg: "#0f151c",
    clusterBorder: "#243040",
    titleColor: "#ffb224",
  },
});

let mmdCounter = 0;

export const Mermaid = ({ code }) => {
  const reactId = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setError(null);
    const renderId = `mmd${reactId}${++mmdCounter}`;
    mermaid
      .render(renderId, code)
      .then(({ svg: out }) => {
        if (!cancelled) setSvg(out);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message || "diagram render failed");
        const orphan = document.getElementById(`d${renderId}`);
        if (orphan) orphan.remove();
      });
    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  if (error) {
    return (
      <pre className="mmd-fallback" data-testid="mermaid-fallback">
        {code}
      </pre>
    );
  }
  if (!svg) return <div className="mmd-loading">rendering diagram…</div>;
  return (
    <div
      className="mmd-diagram"
      data-testid="mermaid-diagram"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};
