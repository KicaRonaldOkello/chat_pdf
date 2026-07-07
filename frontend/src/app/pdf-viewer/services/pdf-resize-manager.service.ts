import { Injectable } from '@angular/core';

import { PDF_RESIZE_DEBOUNCE_MS } from '../const';
import type { ResizeEventData } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for resize observation and debouncing.
 * Manages ResizeObserver and triggers repaint callbacks.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfResizeManager {
  private resizeObserver?: ResizeObserver;
  private resizeTimer: ReturnType<typeof setTimeout> | null = null;
  private resizeEventCount = 0;
  private diagnosticMode = false;
  private hostElement?: HTMLElement;
  private onResizeCallback?: () => void;
  private isRepainting = false;
  private scrollLock = false;

  /**
   * Set up resize observer on the host element.
   * @param host - Host element to observe
   * @param onResize - Callback when resize occurs (debounced)
   */
  setupResizeObserver(host: HTMLElement, onResize?: () => void): void {
    this.disconnect();
    this.hostElement = host;
    this.onResizeCallback = onResize;

    this.resizeObserver = new ResizeObserver((entries) => {
      this.handleResize(entries);
    });
    this.resizeObserver.observe(host);
  }

  /**
   * Disconnect resize observer.
   */
  disconnect(): void {
    if (this.resizeTimer !== null) {
      clearTimeout(this.resizeTimer);
      this.resizeTimer = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = undefined;
    this.hostElement = undefined;
  }

  /**
   * Set the repaint state to prevent resize handling during repaints.
   * @param isRepainting - Whether currently repainting
   */
  setIsRepainting(isRepainting: boolean): void {
    this.isRepainting = isRepainting;
  }

  /**
   * Set the scroll lock state.
   * @param locked - Whether scroll is locked
   */
  setScrollLock(locked: boolean): void {
    this.scrollLock = locked;
  }

  /**
   * Enable or disable diagnostic logging.
   * @param enabled - Whether to enable diagnostics
   */
  setDiagnosticMode(enabled: boolean): void {
    this.diagnosticMode = enabled;
  }

  /**
   * Get resize event count.
   */
  getResizeEventCount(): number {
    return this.resizeEventCount;
  }

  /**
   * Handle resize observer callbacks.
   */
  private handleResize(entries: ResizeObserverEntry[]): void {
    this.resizeEventCount++;

    if (this.diagnosticMode) {
      const eventData: ResizeEventData = {
        count: this.resizeEventCount,
        isRepainting: this.isRepainting,
        scrollLock: this.scrollLock,
        entries: entries.map(e => ({
          width: e.contentRect.width,
          height: e.contentRect.height
        }))
      };
      console.log('[PDF ResizeManager] ResizeObserver triggered', eventData);
    }

    // Skip resize handling during active repaint to prevent thrashing
    if (this.isRepainting) {
      if (this.diagnosticMode) {
        console.log('[PDF ResizeManager] Skipping resize during repaint');
      }
      return;
    }

    if (this.resizeTimer !== null) {
      clearTimeout(this.resizeTimer);
    }

    this.resizeTimer = setTimeout(() => {
      this.resizeTimer = null;
      if (this.onResizeCallback) {
        this.onResizeCallback();
      }
    }, PDF_RESIZE_DEBOUNCE_MS);
  }
}
