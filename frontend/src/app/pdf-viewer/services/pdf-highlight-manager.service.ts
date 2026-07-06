import { Injectable } from '@angular/core';

import {
  PDF_HIGHLIGHT_FADE_DURATION,
  PDF_HIGHLIGHT_PADDING,
  PDF_HIGHLIGHT_PULSE_DURATION,
  PDF_MIN_HIGHLIGHT_SIZE
} from '../const';
import type { HighlightState, PdfJumpTarget } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for source highlighting in PDF viewer.
 * Manages highlight overlays and animation timing.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfHighlightManager {
  private highlightState: HighlightState = {
    active: null,
    fadeTimer: null
  };
  private hostElement?: HTMLElement;
  /** Bumped on clear/re-apply so stale fade timers cannot touch removed overlays. */
  private highlightSession = 0;

  /**
   * Set the host element for highlight overlays.
   * @param host - Host element containing PDF pages
   */
  setHostElement(host: HTMLElement): void {
    this.hostElement = host;
  }

  /**
   * Apply a highlight overlay for the given target.
   * @param target - Jump target with bbox and page size
   * @param pulse - Whether to play the pulse animation
   */
  applyHighlight(target: PdfJumpTarget, pulse: boolean = true): void {
    const host = this.hostElement;
    if (!host) {
      return;
    }

    // Clear existing highlights
    this.clearHighlights();

    if (!target.bbox || !target.pageSize) {
      // Page-level jump only -- nothing to draw
      this.highlightState.active = { page: target.page };
      return;
    }

    const pageEl = host.querySelector<HTMLElement>(`#pdf-page-${target.page}`);
    const inner = pageEl?.querySelector<HTMLElement>('.pdf-page-inner');
    const canvas = inner?.querySelector<HTMLCanvasElement>('canvas');
    if (!inner || !canvas) {
      // Page may not be painted yet
      this.highlightState.active = { page: target.page };
      return;
    }

    const pageSize = target.pageSize;
    if (!pageSize || pageSize.length < 2) {
      this.highlightState.active = { page: target.page };
      return;
    }
    const [pw, ph] = pageSize;
    const renderedW = canvas.clientWidth || parseFloat(canvas.style.width) || 0;
    const renderedH = canvas.clientHeight || parseFloat(canvas.style.height) || 0;
    if (!renderedW || !renderedH || !pw || !ph) {
      this.highlightState.active = { page: target.page };
      return;
    }

    const sx = renderedW / pw;
    const sy = renderedH / ph;
    const [x0, y0, x1, y1] = target.bbox;

    const left = Math.max(0, x0 * sx - PDF_HIGHLIGHT_PADDING);
    const top = Math.max(0, y0 * sy - PDF_HIGHLIGHT_PADDING);
    const width = Math.max(PDF_MIN_HIGHLIGHT_SIZE, (x1 - x0) * sx + PDF_HIGHLIGHT_PADDING * 2);
    const height = Math.max(PDF_MIN_HIGHLIGHT_SIZE, (y1 - y0) * sy + PDF_HIGHLIGHT_PADDING * 2);

    const overlay = document.createElement('div');
    overlay.className = 'pdf-source-highlight';
    if (pulse) {
      overlay.classList.add('pdf-source-highlight--pulse');
    }
    overlay.style.left = `${left}px`;
    overlay.style.top = `${top}px`;
    overlay.style.width = `${width}px`;
    overlay.style.height = `${height}px`;
    inner.appendChild(overlay);

    if (this.highlightState.fadeTimer !== null) {
      clearTimeout(this.highlightState.fadeTimer);
    }

    const session = ++this.highlightSession;

    // After the pulse settles, keep a softer persistent tint for a few seconds
    this.highlightState.fadeTimer = setTimeout(() => {
      if (session !== this.highlightSession) {
        return;
      }
      overlay.classList.add('pdf-source-highlight--fading');
      this.highlightState.fadeTimer = setTimeout(() => {
        if (session !== this.highlightSession) {
          return;
        }
        this.highlightState.active = null;
        if (overlay.isConnected) {
          overlay.remove();
        }
        this.highlightState.fadeTimer = null;
      }, PDF_HIGHLIGHT_FADE_DURATION);
    }, PDF_HIGHLIGHT_PULSE_DURATION);

    this.highlightState.active = target;
  }

  /**
   * Clear all highlight overlays and reset state.
   */
  clearHighlights(): void {
    this.highlightSession++;

    const host = this.hostElement;
    if (host) {
      host.querySelectorAll('.pdf-source-highlight').forEach((n) => n.remove());
    }

    if (this.highlightState.fadeTimer !== null) {
      clearTimeout(this.highlightState.fadeTimer);
      this.highlightState.fadeTimer = null;
    }

    this.highlightState.active = null;
  }

  /**
   * Set the active highlight target without applying it immediately.
   * @param target - Jump target to set as active
   */
  setActiveHighlight(target: PdfJumpTarget | null): void {
    this.highlightState.active = target;
  }

  /**
   * Get the active highlight target.
   */
  getActiveHighlight(): PdfJumpTarget | null {
    return this.highlightState.active;
  }

  /**
   * Get the current highlight state.
   */
  getState(): HighlightState {
    return { ...this.highlightState };
  }
}
