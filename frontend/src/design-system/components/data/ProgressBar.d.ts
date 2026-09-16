/** Determinate progress / score bar. 8px track, pill ends. */
export interface ProgressBarProps {
  /** 0-100. */
  value?: number;
  label?: string;
  tone?: 'brand' | 'accent' | 'secure';
  showValue?: boolean;
  style?: React.CSSProperties;
}
export declare function ProgressBar(props: ProgressBarProps): JSX.Element;
