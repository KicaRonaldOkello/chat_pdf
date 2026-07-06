import { Injectable } from '@angular/core';
import type { PDFDocumentProxy } from 'pdfjs-dist';

import {
  PDF_MAX_SCALE_FACTOR,
  PDF_MIN_CONTAINER_WIDTH
} from '../const';
import type { PageRenderResult, RenderConfig, RenderOptions } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for PDF page rendering logic.
 * Handles canvas creation, viewport calculation, and page rendering.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfRenderService {
  private isRepainting = false;

  /**
   * Render a single PDF page to a DOM element.
   * @param doc - PDF document proxy
   * @param options - Rendering options
   * @returns Promise resolving to rendered page element
   */
  async renderPage(
    doc: PDFDocumentProxy,
    options: RenderOptions
  ): Promise<PageRenderResult> {
    const { pageNum, scale, dpr, maxWidth } = options;

    const page = await doc.getPage(pageNum);
    const baseViewport = page.getViewport({ scale: 1 });
    const fitScale = Math.min(maxWidth / baseViewport.width, PDF_MAX_SCALE_FACTOR);
    const finalScale = fitScale * scale;
    const viewport = page.getViewport({ scale: finalScale });

    const wrapper = document.createElement('div');
    wrapper.className = 'pdf-page';
    wrapper.id = `pdf-page-${pageNum}`;
    wrapper.dataset['pageNumber'] = String(pageNum);

    // `.pdf-page-inner` is the positioned anchor for absolute overlays
    // (source highlights, future annotations).
    const inner = document.createElement('div');
    inner.className = 'pdf-page-inner';

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Failed to get 2D context for canvas');
    }

    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    inner.style.width = `${Math.floor(viewport.width)}px`;
    inner.style.height = `${Math.floor(viewport.height)}px`;

    const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;

    inner.appendChild(canvas);
    wrapper.appendChild(inner);

    await page.render({ canvasContext: ctx, viewport, transform }).promise;

    return {
      element: wrapper,
      pageNum,
      viewport: { width: viewport.width, height: viewport.height }
    };
  }

  /**
   * Render all pages of a PDF document to a host element.
   * Uses document fragment for batch DOM insertion to reduce reflows.
   * @param doc - PDF document proxy
   * @param config - Rendering configuration
   * @returns Promise resolving to true if rendered, false if skipped due to concurrent repaint
   */
  async renderAllPages(
    doc: PDFDocumentProxy,
    config: RenderConfig
  ): Promise<boolean> {
    // Prevent concurrent repaints
    if (this.isRepainting) {
      return false;
    }
    this.isRepainting = true;

    try {
      const { host, zoomPercent, generation, onPageRendered } = config;

      if (generation !== this.loadGeneration) {
        return false;
      }

      host.innerHTML = '';

      const maxWidth = Math.max(host.clientWidth - 8, PDF_MIN_CONTAINER_WIDTH);
      const dpr = window.devicePixelRatio || 1;
      const scale = zoomPercent / 100;

      // Use document fragment for batch DOM insertion to reduce reflows
      const fragment = document.createDocumentFragment();

      for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
        if (generation !== this.loadGeneration) {
          return false;
        }

        const result = await this.renderPage(doc, {
          pageNum,
          scale,
          dpr,
          maxWidth
        });

        fragment.appendChild(result.element);

        if (onPageRendered) {
          onPageRendered(pageNum);
        }
      }

      // Batch insert all pages at once to minimize layout thrashing
      host.appendChild(fragment);

      // Force a layout calculation
      host.offsetHeight; // Trigger reflow
    } finally {
      this.isRepainting = false;
    }
    return true;
  }

  /**
   * Clear all rendered pages from the host element.
   * @param host - Host element containing pages
   */
  clearPages(host: HTMLElement): void {
    host.innerHTML = '';
  }

  /**
   * Check if currently repainting.
   */
  getIsRepainting(): boolean {
    return this.isRepainting;
  }

  /**
   * Set the load generation for cancellation checking.
   */
  private loadGeneration = 0;

  /**
   * Update the load generation.
   */
  setLoadGeneration(gen: number): void {
    this.loadGeneration = gen;
  }

  /**
   * Get the current load generation.
   */
  getLoadGeneration(): number {
    return this.loadGeneration;
  }
}
