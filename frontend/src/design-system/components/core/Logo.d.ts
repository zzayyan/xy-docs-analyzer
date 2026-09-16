/**
 * The XY Intelligence mark. "full" is the horizontal lockup (mark + Intelligence
 * wordmark), "mark" the four-panel X alone, "wordmark" the type alone, "lockup"
 * pairs the mark with live text when a custom label is needed.
 */
export interface LogoProps {
  variant?: 'full' | 'mark' | 'wordmark' | 'lockup';
  /** Rendered height in px. Default 44. Never below 24px. */
  height?: number;
  label?: string;
  /** Directory that holds the logo PNGs, relative to the page. Default "assets/". */
  basePath?: string;
  style?: React.CSSProperties;
}
export declare function Logo(props: LogoProps): JSX.Element;
