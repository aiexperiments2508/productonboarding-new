import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { IconAlert, IconRefresh } from "../icons";
import { Button } from "./Button";
import { cn } from "./cn";

/* Error boundary.
 *
 * React unmounts the whole tree on an uncaught render error, so without one of
 * these a single bad dereference in one panel is a white screen - and a white
 * screen mid-demo reads as "the system fell over" no matter how narrow the
 * actual fault was.
 *
 * The failure this replaces is worth naming, because it is the shape all of
 * them take here: the graph carries an empty `plan_diff` between the start of
 * a revision and the re-scoring that fills it in, and an empty object is
 * truthy, so a panel rendered for a diff that did not exist yet. One optional
 * field, one blank application.
 *
 * So the boundary states what failed and keeps the shell - the rail, the
 * transport, the header - alive around it, because everything else on screen
 * was fine and the run behind it is checkpointed server-side and still there.
 */

interface Props {
  children: ReactNode;
  /** Named in the message, so the reader knows which panel died. */
  label?: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept: the console trace is how this gets diagnosed, and swallowing it to
    // keep the console tidy would trade the only useful artefact for neatness.
    console.error("Render failed", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className={cn(
          "animate-rise-in rounded-md border border-danger-border",
          "bg-danger-soft p-4"
        )}
      >
        <div className="flex items-start gap-2.5">
          <IconAlert size={16} className="mt-0.5 shrink-0 text-danger-text" />
          <div className="min-w-0 flex-1">
            <h2 className="text-md font-semibold text-danger-text">
              {this.props.label
                ? `The ${this.props.label} view could not be drawn`
                : "This view could not be drawn"}
            </h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
              The rest of the application is unaffected, and the run itself is
              checkpointed on the server - move to another section, or reload,
              and it will still be there.
            </p>
            <pre className="mt-2.5 max-h-32 overflow-auto rounded-sm border border-danger-border bg-sunken p-2 font-mono text-xs text-muted">
              {error.message}
            </pre>
            <div className="mt-2.5 flex gap-2">
              <Button
                size="sm"
                icon={<IconRefresh size={14} />}
                onClick={() => this.setState({ error: null })}
              >
                Try again
              </Button>
              <Button
                size="sm"
                tone="ghost"
                onClick={() => window.location.reload()}
              >
                Reload
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
