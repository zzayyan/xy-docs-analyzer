/**
 * Section switcher. "pill" reproduces the deck's XY LM / XY Automate product
 * toggle (filled #E06666 when selected); "underline" is the in-app default.
 */
export interface TabsProps {
  tabs?: string[];
  activeIndex?: number;
  onChange?: (index: number) => void;
  variant?: 'underline' | 'pill';
  style?: React.CSSProperties;
}
export declare function Tabs(props: TabsProps): JSX.Element;
