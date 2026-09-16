/**
 * Product sidebar used by XYLM and XY Automate. Active row lifts to a white card
 * with a soft red hairline and red label.
 */
export interface SideNavItem { id: string; label: string; iconSrc?: string; meta?: string }
export interface SideNavProps {
  items?: SideNavItem[];
  activeId?: string;
  onSelect?: (id: string) => void;
  footer?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function SideNav(props: SideNavProps): JSX.Element;
