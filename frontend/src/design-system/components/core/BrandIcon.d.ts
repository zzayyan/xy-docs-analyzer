/**
 * Wrapper for the brand's raster icon set (assets/icons/*.png — flat 4px-stroke
 * line icons in red #E5420F, white, or teal #2ECBC7). Intentional addition: the
 * source deck places these as bare images, but every surface needs consistent
 * sizing and the deck's white-ringed circular treatment.
 */
export interface BrandIconProps {
  /** Icon file stem from assets/icons (e.g. "brain-circuit") or an explicit path. */
  name: string;
  /** Box size in px. Default 56. */
  size?: number;
  /** Render inside the deck's filled circle with a 4px white ring. */
  ring?: boolean;
  ringTone?: 'brand' | 'secure' | 'ink';
  alt?: string;
  style?: React.CSSProperties;
}
export declare function BrandIcon(props: BrandIconProps): JSX.Element;
