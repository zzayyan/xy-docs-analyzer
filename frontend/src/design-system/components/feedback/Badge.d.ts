/** Small status marker on rows, cards and nav items. Pill-shaped, uppercase-free. */
export interface BadgeProps {
  tone?: 'brand' | 'accent' | 'secure' | 'neutral' | 'outline';
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Badge(props: BadgeProps): JSX.Element;
