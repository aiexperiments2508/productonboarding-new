import type { SVGProps } from "react";

/* Icons, drawn in-repo.
 *
 * An icon library would cover the generic half of this set, but not the half
 * that matters: the five section marks and the correction glyph have to read at
 * 16px, as a matched family, in both themes. Mixing a generic library with
 * hand-drawn domain glyphs gives you two visual languages in the same chrome,
 * so the whole set is drawn here.
 *
 * House rules, so they stay a family:
 *
 *   24x24 viewBox, 20x20 live area (2px of optical padding on every side)
 *   stroke: currentColor, never fill, so colour comes from the text colour
 *   stroke-width 1.6, round caps and joins
 *   no sub-pixel coordinates - everything on the half-pixel grid or better
 */

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "children"> {
  /** Edge length in px. Defaults to 16 - the size used across the chrome. */
  size?: number;
}

function Icon({ size = 16, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      // Icons here are always paired with a text label or an aria-label on the
      // control that owns them, so they are decorative to a screen reader.
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/* --- navigation ----------------------------------------------------------- */

/** Product 360. A box seen from three sides at once - the record, the
 *  assessment and the page it would become. */
export const IconProduct = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3 20.5 7.5 20.5 16.5 12 21 3.5 16.5 3.5 7.5Z" />
    <path d="M12 12 20.5 7.5" />
    <path d="M12 12 3.5 7.5" />
    <path d="M12 12 12 21" />
  </Icon>
);

/** Supplier intake. A stack of rows with the last one ticked: a batch, judged. */
export const IconIntake = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="3.5" width="18" height="17" rx="2" />
    <path d="M7 8.5h10M7 12h6" />
    <path d="m13.5 16.2 2 2 4-4.2" />
  </Icon>
);

/** Ingest fabric. A radar sweep - the view that watches the whole catalog. */
export const IconTower = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 12 12 4" />
    <path d="M12 12 18.9 16" />
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
  </Icon>
);

/** Investigation. A magnifier over a branching trail - the causal chain. */
export const IconInvestigate = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="M15.4 15.4 20.5 20.5" />
    <path d="M7.5 12.5 10 10 12 12 14 8.5" />
  </Icon>
);

/** Scenarios. Two diverging paths, one of them chosen. */
export const IconScenarios = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="6" cy="19" r="2.2" />
    <circle cx="18" cy="5" r="2.2" />
    <circle cx="18" cy="15" r="2.2" />
    <path d="M6 16.8V9a4 4 0 0 1 4-4h5.8" />
    <path d="M8 17.6h3a4 4 0 0 0 4-4v-.6" strokeDasharray="2.5 2.5" />
  </Icon>
);

/** Approvals. A shield with a check - a decision that was authorised. */
export const IconApprovals = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 2.8 19.5 6v6c0 4.4-3.1 8.2-7.5 9.3C7.6 20.2 4.5 16.4 4.5 12V6z" />
    <path d="M8.8 12.2 11 14.4l4.4-4.6" />
  </Icon>
);

/** System control. Sliders - the operational knobs. */
/* Lifecycle: three lanes with a card moving between them. Not a clock and not
 * an arrow - the question the view answers is "which column is it in", and a
 * timeline glyph would promise a chart it deliberately does not draw. */
export const IconLifecycle = (p: IconProps) => (
  <Icon {...p}>
    <rect x="2.5" y="4" width="5.5" height="16" rx="1" />
    <rect x="9.5" y="4" width="5" height="16" rx="1" />
    <rect x="16" y="4" width="5.5" height="16" rx="1" />
    <path d="M4 8h3M11 8h2M17.5 8h2.5" />
    <path d="M4 11h2.5M11 11h2M17.5 11h2" />
  </Icon>
);

export const IconSystem = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2.2" />
    <circle cx="9" cy="17" r="2.2" />
  </Icon>
);

/* --- domain glyphs -------------------------------------------------------- */

/** Correction. A broken link - a value the published copy was built on that no
 *  longer holds, which is the thing the whole product exists for. */
export const IconCorrection = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9.5 14.5 7 17a3.9 3.9 0 0 1-5.5-5.5l2.5-2.5" />
    <path d="M14.5 9.5 17 7a3.9 3.9 0 0 1 5.5 5.5L20 15" />
    <path d="M12 3.5v2.2M20.5 12h-2.2M3.5 12h2.2M12 18.3v2.2" />
  </Icon>
);

/* --- transport controls --------------------------------------------------- */

export const IconPlay = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 4.8 19.5 12 7 19.2z" fill="currentColor" />
  </Icon>
);

export const IconPause = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8.5 4.5v15M15.5 4.5v15" strokeWidth={2.4} />
  </Icon>
);

export const IconStep = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 5 15 12 6 19z" fill="currentColor" />
    <path d="M18.5 4.8v14.4" strokeWidth={2} />
  </Icon>
);

export const IconJump = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 5 11 12 3.5 19z" fill="currentColor" />
    <path d="M12 5 19.5 12 12 19z" fill="currentColor" />
  </Icon>
);

export const IconReset = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.6 12a8.4 8.4 0 1 0 2.6-6.1" />
    <path d="M3.2 4.2v4.6h4.6" />
  </Icon>
);

export const IconRefresh = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20.4 12a8.4 8.4 0 0 1-14.6 5.7" />
    <path d="M3.6 12a8.4 8.4 0 0 1 14.6-5.7" />
    <path d="M18.6 2.4v4.4h-4.4M5.4 21.6v-4.4h4.4" />
  </Icon>
);

/* --- chrome --------------------------------------------------------------- */

export const IconSearch = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10.8" cy="10.8" r="6.8" />
    <path d="M15.8 15.8 20.6 20.6" />
  </Icon>
);

export const IconChevronDown = (p: IconProps) => (
  <Icon {...p}><path d="M5.5 9 12 15.5 18.5 9" /></Icon>
);

export const IconChevronRight = (p: IconProps) => (
  <Icon {...p}><path d="M9 5.5 15.5 12 9 18.5" /></Icon>
);

export const IconChevronLeft = (p: IconProps) => (
  <Icon {...p}><path d="M15 5.5 8.5 12 15 18.5" /></Icon>
);

export const IconClose = (p: IconProps) => (
  <Icon {...p}><path d="M5.5 5.5 18.5 18.5M18.5 5.5 5.5 18.5" /></Icon>
);

export const IconCheck = (p: IconProps) => (
  <Icon {...p}><path d="M4.5 12.5 9.5 17.5 19.5 6.5" /></Icon>
);

export const IconAlert = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.6 22 20.4H2z" />
    <path d="M12 9.6v4.6M12 17.4h.01" />
  </Icon>
);

export const IconInfo = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.8" />
    <path d="M12 11v5.4M12 7.8h.01" />
  </Icon>
);

export const IconClock = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.8" />
    <path d="M12 6.8V12l3.4 2" />
  </Icon>
);

export const IconActivity = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12h4L9 5.5l5 13L16.6 12h4.9" />
  </Icon>
);

export const IconSun = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 1.8v2.6M12 19.6v2.6M4.8 4.8l1.9 1.9M17.3 17.3l1.9 1.9M1.8 12h2.6M19.6 12h2.6M4.8 19.2l1.9-1.9M17.3 6.7l1.9-1.9" />
  </Icon>
);

export const IconMoon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20.5 14.4A8.8 8.8 0 0 1 9.6 3.5 8.8 8.8 0 1 0 20.5 14.4z" />
  </Icon>
);

export const IconMonitor = (p: IconProps) => (
  <Icon {...p}>
    <rect x="2.5" y="4" width="19" height="13" rx="2" />
    <path d="M8.5 20.5h7M12 17v3.5" />
  </Icon>
);

export const IconDensity = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 6h17M3.5 12h17M3.5 18h17" />
  </Icon>
);

export const IconPalette = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.2a8.8 8.8 0 0 0 0 17.6c1.3 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.2-.3-.4-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8h1.4a4.6 4.6 0 0 0 4.6-4.6c0-3.9-3.9-7-8.8-7z" />
    <circle cx="7.8" cy="11.4" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="11.4" cy="7.6" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="16" cy="9.4" r="1.1" fill="currentColor" stroke="none" />
  </Icon>
);

export const IconSidebar = (p: IconProps) => (
  <Icon {...p}>
    <rect x="2.8" y="4" width="18.4" height="16" rx="2" />
    <path d="M9.6 4v16" />
  </Icon>
);

export const IconCommand = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8.5 3.5a2.5 2.5 0 1 0 0 5h7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0-2.5 2.5v12a2.5 2.5 0 1 0 2.5-2.5h-7a2.5 2.5 0 1 0 2.5 2.5V6a2.5 2.5 0 0 0-2.5-2.5z" />
  </Icon>
);

export const IconSpark = (p: IconProps) => (
  <Icon {...p}>
    <path d="M13.4 2.5 4.8 13.4h6L9.8 21.5l8.9-11.2h-6.2z" />
  </Icon>
);

/** The machine half of the loop. A head with an antenna and two eyes - it
 *  marks work an agent did, as against the approval gate, which is the one
 *  place in the system a person decides. */
export const IconRobot = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 2.6v3" />
    <circle cx="12" cy="2.2" r="1" fill="currentColor" stroke="none" />
    <rect x="4" y="5.6" width="16" height="13" rx="3.4" />
    <path d="M9.2 10.6v2.4M14.8 10.6v2.4" />
    <path d="M1.6 10.4v3.6M22.4 10.4v3.6" />
    <path d="M9.6 21.4h4.8" />
  </Icon>
);

export const IconDoc = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 2.8h7.5L19 8.3v12.9H6z" />
    <path d="M13.2 2.8v5.6h5.6M9 13h6M9 16.6h4.4" />
  </Icon>
);

export const IconTrace = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="5.5" cy="6" r="2.2" />
    <circle cx="18.5" cy="12" r="2.2" />
    <circle cx="5.5" cy="18" r="2.2" />
    <path d="M7.6 6.9c4 1.4 5.6 2.6 8.8 4.2M7.6 17.1c4-1.4 5.6-2.6 8.8-4.2" />
  </Icon>
);

/** A knowledge graph. Four nodes and the edges between them, drawn as a
 *  neighbourhood rather than a chain - `IconTrace` is already the chain, and
 *  the difference between the two is the whole difference between "what does
 *  this depend on" and "what is this connected to". */
export const IconGraph = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="2.4" />
    <circle cx="4.6" cy="6" r="1.9" />
    <circle cx="19.4" cy="7.2" r="1.9" />
    <circle cx="17" cy="19" r="1.9" />
    <circle cx="5.6" cy="17.4" r="1.9" />
    <path d="M6.2 7.1 10.2 10.5M17.6 8.2 13.7 10.8M15.6 17.4 13.2 13.9M7.2 16.3 10.2 13.6" />
  </Icon>
);

/** Asking in words. A speech bubble with a question in it, rather than the
 *  three dots a chat widget usually gets - the panel answers questions, and
 *  the dots read as "somebody is typing". */
export const IconAsk = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20.5 12.4a7.6 7.6 0 0 1-7.6 7.6H8.3l-3.9 2.4a.4.4 0 0 1-.6-.36V12.4a7.6 7.6 0 0 1 15.2 0Z" />
    <path d="M10.3 9.7a2.6 2.6 0 0 1 4.6 1.6c0 1.7-2.4 2-2.4 3.4" />
    <path d="M12.5 17.1h.01" />
  </Icon>
);

/** Reading an answer aloud. A speaker with two arcs - the arcs are what
 *  distinguish it from the mute state, which drops them. */
export const IconSpeaker = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 9.4h3.2L12 5.2v13.6L7.2 14.6H4a.8.8 0 0 1-.8-.8v-3.6a.8.8 0 0 1 .8-.8Z" />
    <path d="M15.4 9.6a3.6 3.6 0 0 1 0 4.8" />
    <path d="M18 7.2a7.2 7.2 0 0 1 0 9.6" />
  </Icon>
);

/** The same speaker with the arcs struck through: answers are not read out. */
export const IconSpeakerOff = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 9.4h3.2L12 5.2v13.6L7.2 14.6H4a.8.8 0 0 1-.8-.8v-3.6a.8.8 0 0 1 .8-.8Z" />
    <path d="m16 10 4 4M20 10l-4 4" />
  </Icon>
);
