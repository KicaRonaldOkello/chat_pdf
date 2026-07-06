import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';
import type { RetrievedSource } from '../../interfaces';

/**
 * Where a clicked source chip wants to land in the viewer.
 */
export interface PdfJumpTarget {
  page: number;
  /** `[x0, y0, x1, y1]` in the same coord system as `pageSize`. */
  bbox?: [number, number, number, number];
  /** `[width, height]` of that coord system. */
  pageSize?: [number, number];
}

/**
 * State of scroll position for restoration after repaints.
 */
export interface ScrollState {
  currentPage: number;
  scrollTop: number;
}

/**
 * Options for rendering a single page.
 */
export interface RenderOptions {
  pageNum: number;
  scale: number;
  dpr: number;
  maxWidth: number;
}

/**
 * Configuration for rendering all pages.
 */
export interface RenderConfig {
  host: HTMLElement;
  zoomPercent: number;
  generation: number;
  onPageRendered?: (pageNum: number) => void;
}

/**
 * Result of a page render operation.
 */
export interface PageRenderResult {
  element: HTMLElement;
  pageNum: number;
  viewport: { width: number; height: number };
}

/**
 * State of the PDF document loader.
 */
export interface DocumentLoaderState {
  loading: boolean;
  error: string | null;
  pdf: PDFDocumentProxy | null;
  inFlightLoad: PDFDocumentLoadingTask | null;
  loadGeneration: number;
}

/**
 * Configuration for thumbnail rendering.
 */
export interface ThumbnailConfig {
  maxWidth: number;
  dpr: number;
}

/**
 * Search state and results.
 */
export interface SearchState {
  query: string;
  results: RetrievedSource[];
  activeIndex: number;
  loading: boolean;
  error: string | null;
  ran: boolean;
  hidden: boolean;
}

/**
 * Highlight state.
 */
export interface HighlightState {
  active: PdfJumpTarget | null;
  fadeTimer: ReturnType<typeof setTimeout> | null;
}

/**
 * Resize observer callback data.
 */
export interface ResizeEventData {
  count: number;
  isRepainting: boolean;
  scrollLock: boolean;
  entries: Array<{ width: number; height: number }>;
}

/**
 * Diagnostic information for debugging.
 */
export interface DiagnosticInfo {
  scrollEventCount: number;
  resizeEventCount: number;
  isRepainting: boolean;
  scrollLock: boolean;
}
