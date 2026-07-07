import { Injectable } from '@angular/core';

import {
  PDF_INTERSECTION_ROOT_MARGIN,
  PDF_INTERSECTION_THRESHOLDS,
  PDF_SCROLL_LOG_SAMPLE_RATE
} from '../const';
import type { ScrollState } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for scroll position tracking and restoration.
 * Manages intersection observer for page detection and scroll event handling.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfScrollManager {
  private pageIntersectionObserver?: IntersectionObserver;
  private currentPage = 1;
  private scrollLock = false;
  private scrollEventCount = 0;
  private diagnosticMode = false;

  private onPageChangeCallback?: (page: number) => void;
  private hostElement?: HTMLElement;

  /**
   * Set up scroll listener and intersection observer.
   * @param host - Host element containing PDF pages
   * @param onPageChange - Callback when current page changes
   */
  setupScrollListener(
    host: HTMLElement,
    onPageChange?: (page: number) => void
  ): void {
    this.disconnectScrollListener();
    this.hostElement = host;
    this.onPageChangeCallback = onPageChange;
    host.addEventListener('scroll', this.handleScroll, { passive: true });
    this.attachPageObservers(host);
  }

  /**
   * Disconnect scroll listener and intersection observer.
   */
  disconnectScrollListener(): void {
    if (this.hostElement) {
      this.hostElement.removeEventListener('scroll', this.handleScroll);
    }
    this.disconnectPageObserver();
    this.hostElement = undefined;
  }

  /**
   * Save current scroll position for restoration.
   * @returns Scroll state with current page and scroll position
   */
  saveScrollPosition(): ScrollState {
    const scrollTop = this.hostElement?.scrollTop || 0;
    return {
      currentPage: this.currentPage,
      scrollTop
    };
  }

  /**
   * Restore scroll position from saved state.
   * @param state - Saved scroll state
   * @param totalPages - Total number of pages in document
   */
  async restoreScrollPosition(state: ScrollState, totalPages: number): Promise<void> {
    const host = this.hostElement;
    if (!host) {
      return;
    }

    // Wait for next frame to ensure DOM is fully settled
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));

    const { currentPage, scrollTop } = state;

    if (currentPage > 1 && currentPage <= totalPages) {
      const target = host.querySelector<HTMLElement>(
        `#pdf-page-${currentPage}`
      );
      if (target) {
        target.scrollIntoView({ behavior: 'auto', block: 'start' });
        
        if (this.diagnosticMode && Math.abs(host.scrollTop - scrollTop) > 100) {
          console.log('[PDF ScrollManager] Scroll position adjusted', {
            before: scrollTop,
            after: host.scrollTop,
            targetPage: currentPage
          });
        }
      }
    }
  }

  /**
   * Scroll to a specific page.
   * @param pageNum - Page number to scroll to
   */
  scrollToPage(pageNum: number): void {
    const host = this.hostElement;
    if (!host) {
      return;
    }
    const el = host.querySelector<HTMLElement>(`#pdf-page-${pageNum}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    this.currentPage = pageNum;
  }

  /**
   * Get the current page number.
   */
  getCurrentPage(): number {
    return this.currentPage;
  }

  /**
   * Set the current page number.
   */
  setCurrentPage(page: number): void {
    this.currentPage = page;
  }

  /**
   * Check if scroll is locked.
   */
  getScrollLock(): boolean {
    return this.scrollLock;
  }

  /**
   * Set scroll lock state.
   */
  setScrollLock(locked: boolean): void {
    this.scrollLock = locked;
  }

  /**
   * Enable or disable diagnostic logging.
   */
  setDiagnosticMode(enabled: boolean): void {
    this.diagnosticMode = enabled;
  }

  /**
   * Get diagnostic information.
   */
  getDiagnosticInfo() {
    return {
      scrollEventCount: this.scrollEventCount,
      isRepainting: false,
      scrollLock: this.scrollLock
    };
  }

  /**
   * Attach intersection observer to track visible pages.
   */
  attachPageObservers(host: HTMLElement): void {
    this.disconnectPageObserver();
    const pages = host.querySelectorAll<HTMLElement>('.pdf-page');
    if (pages.length === 0) {
      return;
    }

    this.pageIntersectionObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length === 0) {
          return;
        }
        const best = visible.reduce((a, b) =>
          a.intersectionRatio >= b.intersectionRatio ? a : b
        );
        const p = Number((best.target as HTMLElement).dataset['pageNumber']);
        if (!Number.isNaN(p) && p !== this.currentPage) {
          this.currentPage = p;
          if (this.onPageChangeCallback) {
            this.onPageChangeCallback(p);
          }
        }
      },
      {
        root: host,
        rootMargin: PDF_INTERSECTION_ROOT_MARGIN,
        threshold: PDF_INTERSECTION_THRESHOLDS
      }
    );

    pages.forEach((el) => this.pageIntersectionObserver!.observe(el));
  }

  /**
   * Disconnect intersection observer.
   */
  private disconnectPageObserver(): void {
    this.pageIntersectionObserver?.disconnect();
    this.pageIntersectionObserver = undefined;
  }

  /**
   * Handle scroll events.
   */
  private handleScroll = (): void => {
    this.scrollEventCount++;
    if (this.diagnosticMode && this.scrollEventCount % PDF_SCROLL_LOG_SAMPLE_RATE === 0) {
      console.log('[PDF ScrollManager] Scroll event', {
        count: this.scrollEventCount,
        scrollLock: this.scrollLock
      });
    }
    // Block scroll-triggered operations during repaint
    if (this.scrollLock) {
      return;
    }
  };
}
