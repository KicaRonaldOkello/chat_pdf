import { Injectable } from '@angular/core';
import type { PDFDocumentProxy, PageViewport, RenderTask } from 'pdfjs-dist';

import { PDF_MAX_SCALE_FACTOR, PDF_MIN_CONTAINER_WIDTH } from '../const';
import type { RenderConfig } from '../interfaces/pdf-viewer.types';

/** How many page renders to run concurrently (keeps the UI responsive). */
const PDF_RENDER_CONCURRENCY = 4;

/** Drop rendered canvases farther than this many pages from the viewport. */
const PDF_CANVAS_EVICTION_PAGES = 12;

/**
 * Service responsible for PDF page rendering.
 *
 * The document is laid out as lightweight placeholders first (correct page
 * geometry, no canvases), and real canvas renders happen lazily for pages in
 * or near the viewport. Resize/zoom updates placeholder/canvas CSS geometry
 * and re-renders only the visible pages; off-screen pages refresh when they
 * scroll into view.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfRenderService {
  private isRepainting = false;
  private renderCancelled = false;
  private currentRenderTasks = new Set<RenderTask>();
  private activeRenderBatch: Promise<void> | null = null;
  private pageBaseSizes = new Map<number, { width: number; height: number }>();
  private stalePages = new Set<number>();
  private pendingRenders = new Set<number>();
  private loadGeneration = 0;

  /**
   * Cancel in-flight renders so a swap never races the worker teardown.
   */
  async cancelRender(): Promise<void> {
    this.renderCancelled = true;
    for (const task of this.currentRenderTasks) {
      task.cancel();
    }
    this.currentRenderTasks.clear();
    if (this.activeRenderBatch) {
      try {
        await this.activeRenderBatch;
      } catch {
        // Cancellation is expected during a document swap.
      }
    }
  }

  /** Prepare for a new render pass (clears the cancellation flag). */
  beginRenderPass(): void {
    this.renderCancelled = false;
  }

  getIsRepainting(): boolean {
    return this.isRepainting;
  }

  setLoadGeneration(gen: number): void {
    this.loadGeneration = gen;
  }

  getLoadGeneration(): number {
    return this.loadGeneration;
  }

  /**
   * Lay out the whole document as placeholders with correct page geometry.
   * No canvases are created here — pages render lazily when visible.
   */
  async renderDocument(
    doc: PDFDocumentProxy,
    config: RenderConfig
  ): Promise<boolean> {
    if (this.isRepainting) {
      return false;
    }
    this.isRepainting = true;
    this.beginRenderPass();
    this.pageBaseSizes.clear();
    this.stalePages.clear();
    this.pendingRenders.clear();

    const pass = (async (): Promise<boolean> => {
      const { host, zoomPercent, generation } = config;
      if (generation !== this.loadGeneration) {
        return false;
      }
      const maxWidth = Math.max(host.clientWidth - 8, PDF_MIN_CONTAINER_WIDTH);
      const scale = zoomPercent / 100;

      const fragment = document.createDocumentFragment();
      for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
        if (generation !== this.loadGeneration || this.renderCancelled) {
          return false;
        }
        const page = await doc.getPage(pageNum);
        const base = page.getViewport({ scale: 1 });
        this.pageBaseSizes.set(pageNum, {
          width: base.width,
          height: base.height
        });
        const fitScale = Math.min(maxWidth / base.width, PDF_MAX_SCALE_FACTOR);
        const viewport = page.getViewport({ scale: fitScale * scale });
        fragment.appendChild(this.buildPlaceholder(pageNum, viewport));
      }

      if (generation !== this.loadGeneration || this.renderCancelled) {
        return false;
      }
      host.innerHTML = '';
      host.appendChild(fragment);
      host.offsetHeight; // force reflow so geometry is settled
      return true;
    })();

    this.activeRenderBatch = pass.then(
      () => undefined,
      () => undefined
    );
    try {
      return await pass;
    } finally {
      this.isRepainting = false;
      this.activeRenderBatch = null;
    }
  }

  /**
   * Update placeholder/canvas geometry after a resize or zoom, and mark every
   * page stale so visible pages re-render at the new scale immediately and
   * off-screen pages refresh when scrolled into view.
   */
  async updateLayout(config: RenderConfig): Promise<boolean> {
    const { host, zoomPercent, generation } = config;
    if (generation !== this.loadGeneration) {
      return false;
    }
    const maxWidth = Math.max(host.clientWidth - 8, PDF_MIN_CONTAINER_WIDTH);
    const scale = zoomPercent / 100;

    for (const el of host.querySelectorAll<HTMLElement>('.pdf-page')) {
      if (generation !== this.loadGeneration) {
        return false;
      }
      const pageNum = Number(el.dataset['pageNumber']);
      const base = this.pageBaseSizes.get(pageNum);
      if (!base) {
        continue;
      }
      const fitScale = Math.min(maxWidth / base.width, PDF_MAX_SCALE_FACTOR);
      const w = Math.floor(base.width * fitScale * scale);
      const h = Math.floor(base.height * fitScale * scale);
      const inner = el.querySelector<HTMLElement>('.pdf-page-inner');
      if (inner) {
        inner.style.width = `${w}px`;
        inner.style.height = `${h}px`;
      }
      const canvas = el.querySelector<HTMLCanvasElement>('canvas');
      if (canvas) {
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
      }
    }

    this.markStale();
    return true;
  }

  /** Render the given pages, at most PDF_RENDER_CONCURRENCY at a time. */
  async renderPagesInRange(
    doc: PDFDocumentProxy,
    pageNumbers: number[],
    config: RenderConfig,
    force = false
  ): Promise<void> {
    const batch = (async (): Promise<void> => {
      for (let i = 0; i < pageNumbers.length; i += PDF_RENDER_CONCURRENCY) {
        if (this.renderCancelled || config.generation !== this.loadGeneration) {
          return;
        }
        const chunk = pageNumbers.slice(i, i + PDF_RENDER_CONCURRENCY);
        await Promise.all(
          chunk.map((pageNum) => this.renderPageInto(doc, pageNum, config, force))
        );
      }
    })();

    this.activeRenderBatch = batch;
    try {
      await batch;
    } finally {
      this.activeRenderBatch = null;
    }
  }

  /** Page numbers currently in or near the viewport, ascending. */
  getVisiblePageNumbers(host: HTMLElement, bufferPx = 0): number[] {
    const top = host.scrollTop - bufferPx;
    const bottom = host.scrollTop + host.clientHeight + bufferPx;
    const visible: number[] = [];
    for (const el of host.querySelectorAll<HTMLElement>('.pdf-page')) {
      const pageNum = Number(el.dataset['pageNumber']);
      if (Number.isNaN(pageNum)) {
        continue;
      }
      const elTop = el.offsetTop;
      const elBottom = elTop + el.offsetHeight;
      if (elBottom >= top && elTop <= bottom) {
        visible.push(pageNum);
      }
    }
    return visible;
  }

  /** Mark pages stale; when omitted, every known page becomes stale. */
  markStale(pageNumbers?: number[]): void {
    if (pageNumbers && pageNumbers.length) {
      for (const pageNum of pageNumbers) {
        this.stalePages.add(pageNum);
      }
    } else {
      this.stalePages = new Set(this.pageBaseSizes.keys());
    }
  }

  clearPages(host: HTMLElement): void {
    host.innerHTML = '';
  }

  /**
   * Drop canvases for pages far outside the visible range so long documents
   * don't accumulate hundreds of MB of bitmaps. Placeholders stay in place
   * (with the page hint) and re-render when scrolled back into view.
   */
  evictDistantCanvases(host: HTMLElement, visiblePageNumbers: number[]): void {
    if (!visiblePageNumbers.length) {
      return;
    }
    const lo = visiblePageNumbers[0];
    const hi = visiblePageNumbers[visiblePageNumbers.length - 1];

    for (const el of host.querySelectorAll<HTMLElement>('.pdf-page')) {
      const pageNum = Number(el.dataset['pageNumber']);
      if (Number.isNaN(pageNum)) {
        continue;
      }
      if (
        pageNum >= lo - PDF_CANVAS_EVICTION_PAGES &&
        pageNum <= hi + PDF_CANVAS_EVICTION_PAGES
      ) {
        continue;
      }
      const inner = el.querySelector<HTMLElement>('.pdf-page-inner');
      el.querySelector('canvas')?.remove();
      if (inner && !inner.querySelector('.pdf-page-hint')) {
        const hint = document.createElement('div');
        hint.className = 'pdf-page-hint';
        hint.textContent = String(pageNum);
        inner.appendChild(hint);
      }
    }
  }

  private buildPlaceholder(pageNum: number, viewport: PageViewport): HTMLElement {
    const wrapper = document.createElement('div');
    wrapper.className = 'pdf-page';
    wrapper.id = `pdf-page-${pageNum}`;
    wrapper.dataset['pageNumber'] = String(pageNum);

    const inner = document.createElement('div');
    inner.className = 'pdf-page-inner';
    inner.style.width = `${Math.floor(viewport.width)}px`;
    inner.style.height = `${Math.floor(viewport.height)}px`;

    const hint = document.createElement('div');
    hint.className = 'pdf-page-hint';
    hint.textContent = String(pageNum);
    inner.appendChild(hint);

    wrapper.appendChild(inner);
    return wrapper;
  }

  private needsRender(el: HTMLElement, pageNum: number): boolean {
    return this.stalePages.has(pageNum) || !el.querySelector('canvas');
  }

  private async renderPageInto(
    doc: PDFDocumentProxy,
    pageNum: number,
    config: RenderConfig,
    force: boolean
  ): Promise<void> {
    const { host, zoomPercent, generation } = config;
    if (generation !== this.loadGeneration || this.renderCancelled) {
      return;
    }
    if (this.pendingRenders.has(pageNum)) {
      return;
    }
    const el = host.querySelector<HTMLElement>(`#pdf-page-${pageNum}`);
    if (!el || (!force && !this.needsRender(el, pageNum))) {
      return;
    }
    const base = this.pageBaseSizes.get(pageNum);
    if (!base) {
      return;
    }

    this.pendingRenders.add(pageNum);
    try {
      const maxWidth = Math.max(host.clientWidth - 8, PDF_MIN_CONTAINER_WIDTH);
      const scale = zoomPercent / 100;
      const dpr = window.devicePixelRatio || 1;
      const fitScale = Math.min(maxWidth / base.width, PDF_MAX_SCALE_FACTOR);
      const finalScale = fitScale * scale;

      const page = await doc.getPage(pageNum);
      if (generation !== this.loadGeneration || this.renderCancelled) {
        return;
      }
      const viewport = page.getViewport({ scale: finalScale });

      const inner = el.querySelector<HTMLElement>('.pdf-page-inner');
      if (!inner) {
        return;
      }
      inner.querySelector('canvas')?.remove();
      inner.querySelector('.pdf-page-hint')?.remove();

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        return;
      }
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      inner.appendChild(canvas);

      const renderTask = page.render({
        canvasContext: ctx,
        viewport,
        transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined
      });
      this.currentRenderTasks.add(renderTask);
      try {
        await renderTask.promise;
      } finally {
        this.currentRenderTasks.delete(renderTask);
      }
      if (generation !== this.loadGeneration || this.renderCancelled) {
        return;
      }
      this.stalePages.delete(pageNum);
      config.onPageRendered?.(pageNum);
    } finally {
      this.pendingRenders.delete(pageNum);
    }
  }
}
