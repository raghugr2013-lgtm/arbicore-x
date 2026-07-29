import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mermaid } from "./Mermaid";

const components = {
  // Handle fenced blocks at the <pre> level — react-markdown v9+ has no `inline`
  // prop, and returning <pre> from the `code` override nests it inside <p>.
  pre({ children, ...props }) {
    const child = Array.isArray(children) ? children[0] : children;
    const cls = child?.props?.className || "";
    if (/language-mermaid/.test(cls)) {
      const raw = String(child.props.children).replace(/\n$/, "");
      return <Mermaid code={raw} />;
    }
    return (
      <pre className="md-code-block" {...props}>
        {children}
      </pre>
    );
  },
  code({ className, children, ...props }) {
    return (
      <code className={className || "md-inline-code"} {...props}>
        {children}
      </code>
    );
  },
  table({ children }) {
    return (
      <div className="md-table-wrap">
        <table>{children}</table>
      </div>
    );
  },
};

export const MarkdownDoc = ({ content }) => (
  <div className="md-doc" data-testid="doc-content">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  </div>
);
