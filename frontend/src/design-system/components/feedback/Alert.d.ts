/**
 * Inline system message. "secure" (teal) is the brand's governance/compliance
 * voice — use it for data-sovereignty confirmations.
 */
export interface AlertProps {
  tone?: 'info' | 'success' | 'warning' | 'danger' | 'secure';
  title?: string;
  children?: React.ReactNode;
  iconSrc?: string;
  onDismiss?: () => void;
  style?: React.CSSProperties;
}
export declare function Alert(props: AlertProps): JSX.Element;
