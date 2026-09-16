/**
 * Flat data grid for candidate rankings, risk scores and run logs. Header is
 * uppercase micro-caps on --surface-subtle; rows separated by hairlines only.
 */
export interface DataTableColumn { key: string; label: string; align?: 'left' | 'right' | 'center' }
export interface DataTableProps {
  columns?: Array<DataTableColumn | string>;
  rows?: Array<Record<string, React.ReactNode>>;
  dense?: boolean;
  style?: React.CSSProperties;
}
export declare function DataTable(props: DataTableProps): JSX.Element;
