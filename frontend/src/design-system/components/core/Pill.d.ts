/**
 * The deck's tech-stack chip: a 7px-radius rectangle-ish pill with a 1pt red
 * outline. Use for technology names, capability labels and product tags.
 */
export interface PillProps {
  /** Default "outline" (white fill, red hairline). */
  tone?: 'outline' | 'filled' | 'soft' | 'neutral';
  size?: 'sm' | 'md';
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Pill(props: PillProps): JSX.Element;
