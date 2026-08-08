import { Injectable } from '@angular/core';
import type { PDFDocumentProxy } from 'pdfjs-dist';

import { PDF_THUMB_MAX_WIDTH } from '../const';
import type { ThumbnailConfig } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for PDF thumbnail rendering.
 * Handles thumbnail generation and highlighting.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfThumbnailManager {
  private thumbsRenderToken = 0;
  private currentPage = 1;
  private hostElement?: HTMLElement;

  /**
   * Set the host element for thumbnails.
   * @param host - Host element for thumbnails
   */
  setHostElement(host: HTMLElement): void {
    this.hostElement = host;
  }

  /**
   * Set the current page number for highlighting.
   * @param page - Current page number
   */
  setCurrentPage(page: number): void {
    this.currentPage = page;
    this.highlightThumbnail(page);
  }

  /**
   * Render all thumbnails for a PDF document.
   * @param doc - PDF document proxy
   * @param config - Thumbnail rendering configuration
   * @param onPageClick - Callback when a thumbnail is clicked
   */
  async renderThumbnails(
    doc: PDFDocumentProxy,
    config: ThumbnailConfig,
    onPageClick?: (pageNum: number) => void
  ): Promise<void> {
    const host = this.hostElement;
    if (!host) {
      return;
    }

    this.thumbsRenderToken++;
    const token = this.thumbsRenderToken;
    host.innerHTML = '';
    host.dataset['rendered'] = '1';

    const { maxWidth, dpr } = config;

    for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
      if (token !== this.thumbsRenderToken) {
        return;
      }

      const page = await doc.getPage(pageNum);
      const base = page.getViewport({ scale: 1 });
      const scale = Math.min(maxWidth / base.width, 1);
      const viewport = page.getViewport({ scale });

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'pdf-thumb';
      btn.dataset['page'] = String(pageNum);
      if (pageNum === this.currentPage) {
        btn.classList.add('active');
      }

      if (onPageClick) {
        btn.addEventListener('click', () => {
          onPageClick(pageNum);
        });
      }

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        continue;
      }

      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;

      const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;

      btn.appendChild(canvas);
      host.appendChild(btn);

      try {
        await page.render({ canvasContext: ctx, viewport, transform }).promise;
      } catch {
        // Document was swapped while thumbnails were rendering; the new
        // document triggers its own thumbnail pass, so this is safe to drop.
        return;
      }
      if (token !== this.thumbsRenderToken) {
        return;
      }
    }
  }

  /**
   * Highlight the thumbnail for a specific page.
   * @param activePage - Page number to highlight
   */
  highlightThumbnail(activePage: number): void {
    const host = this.hostElement;
    if (!host) {
      return;
    }

    host.querySelectorAll('.pdf-thumb').forEach((node) => {
      const el = node as HTMLElement;
      const p = Number(el.dataset['page']);
      el.classList.toggle('active', p === activePage);
    });
  }

  /**
   * Clear all thumbnails.
   */
  clearThumbnails(): void {
    const host = this.hostElement;
    if (!host) {
      return;
    }

    host.innerHTML = '';
    delete host.dataset['rendered'];
    this.thumbsRenderToken++;
  }

  /**
   * Check if thumbnails have been rendered.
   */
  isRendered(): boolean {
    const host = this.hostElement;
    if (!host) {
      return false;
    }
    return host.dataset['rendered'] === '1';
  }
}
