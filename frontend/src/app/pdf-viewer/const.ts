/**
 * Configuration constants for the PDF viewer component.
 * Centralized for easy tuning and maintenance.
 */

/** Same major/minor as package.json — used for CMap CDN. */
export const PDF_PDFJS_VERSION = '4.10.38';

/** Maximum width for thumbnail rendering. */
export const PDF_THUMB_MAX_WIDTH = 104;

/** Available zoom percentage presets. */
export const PDF_ZOOM_PRESETS = [50, 75, 100, 125, 150, 186, 200];

/** Debounce time for resize-triggered repaints in milliseconds. */
export const PDF_RESIZE_DEBOUNCE_MS = 120;

/** Minimum time between repaints to prevent thrashing. */
export const PDF_REPAINT_DEBOUNCE_MS = 150;

/** Maximum scale factor for page rendering. */
export const PDF_MAX_SCALE_FACTOR = 3;

/** Minimum container width for rendering. */
export const PDF_MIN_CONTAINER_WIDTH = 80;

/** Padding for highlight boxes in pixels. */
export const PDF_HIGHLIGHT_PADDING = 2;

/** Minimum highlight box size in pixels. */
export const PDF_MIN_HIGHLIGHT_SIZE = 4;

/** Duration of highlight pulse animation in milliseconds. */
export const PDF_HIGHLIGHT_PULSE_DURATION = 4200;

/** Duration of highlight fade animation in milliseconds. */
export const PDF_HIGHLIGHT_FADE_DURATION = 900;

/** Intersection observer root margin for page detection (format: 'top right bottom left'). */
export const PDF_INTERSECTION_ROOT_MARGIN = '-40% 0px -40% 0px';

/** Intersection observer thresholds for page detection. */
export const PDF_INTERSECTION_THRESHOLDS = [0, 0.1, 0.25, 0.5, 0.75, 1];

/** Sampling rate for scroll event logging (every N events). */
export const PDF_SCROLL_LOG_SAMPLE_RATE = 10;

/** Default zoom percentage. */
export const PDF_DEFAULT_ZOOM_PERCENT = 100;

/** Default page number. */
export const PDF_DEFAULT_PAGE_NUMBER = 1;
