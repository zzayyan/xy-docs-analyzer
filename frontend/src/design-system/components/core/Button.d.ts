/**
 * Primary action control. Brand red fill for the single most important action on a
 * surface; outlined red for secondary; ghost for tertiary/toolbar actions.
 */
export interface ButtonProps {
  /** Visual weight. Default "primary". */
  variant?: 'primary' | 'secondary' | 'ghost' | 'inverse';
  /** Default "md". */
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  fullWidth?: boolean;
  /** Path to a PNG from assets/icons — the brand has no icon font. */
  iconSrc?: string;
  iconPosition?: 'left' | 'right';
  type?: 'button' | 'submit' | 'reset';
  onClick?: (e: React.MouseEvent) => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Button(props: ButtonProps): JSX.Element;
