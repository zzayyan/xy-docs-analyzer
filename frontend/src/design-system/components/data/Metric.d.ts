/**
 * Big-number result claim ("70% reduction in initial CV screening time").
 */
export interface MetricProps {
  value: string;
  label: string;
  delta?: string;
  tone?: 'brand' | 'ink' | 'secure';
  align?: 'left' | 'center';
  style?: React.CSSProperties;
}
export declare function Metric(props: MetricProps): JSX.Element;
