/**
 * The brand's capability card: white fill, 18px corners, and a heavy 4pt red
 * stroke. Icons overhang the top edge in the deck; in app contexts use the
 * "quiet" variant instead.
 */
export interface CardProps {
  /** "outline" = 4pt --border-brand (deck default). "accent" = 4pt --brand-accent.
   *  "quiet" = hairline + soft shadow for dense app UI. "tint" = red-50 wash. */
  variant?: 'outline' | 'accent' | 'quiet' | 'tint';
  title?: string;
  body?: string;
  /** PNG from assets/icons. */
  iconSrc?: string;
  align?: 'center' | 'left';
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Card(props: CardProps): JSX.Element;
