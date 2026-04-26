import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  Input,
  OnChanges,
  OnDestroy,
  OnInit,
  SimpleChanges,
  ViewChild,
  inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { firstValueFrom, Subscription } from 'rxjs';
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';

import { ensurePdfWorker } from './pdfjs-worker';
import { RetrievedSource } from '../interfaces';
import { ChatService } from '../services/chat.service';
import { DocumentSessionService } from '../services/document-session.service';

/** Same major/minor as package.json — used for CMap CDN. */
const PDFJS_VERSION = '4.10.38';

const THUMB_MAX_WIDTH = 104;

/** Where a clicked source chip wants to land in the viewer. */
export interface PdfJumpTarget {
  page: number;
  /** `[x0, y0, x1, y1]` in the same coord system as `pageSize`. */
  bbox?: [number, number, number, number];
  /** `[width, height]` of that coord system. */
  pageSize?: [number, number];
}

@Component({
  selector: 'app-pdf-viewer',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule],
  templateUrl: './pdf-viewer.component.html',
  styleUrl: './pdf-viewer.component.scss'
})
export class PdfViewerComponent implements OnInit, AfterViewInit, OnChanges, OnDestroy {
  @Input() pdfData: ArrayBuffer | null = null;
  /**
   * Document ID the backend knows this PDF by.  Required for semantic
   * search -- the viewer will disable the search feature when it's null
   * (e.g. before upload completes).
   */
  @Input() documentId: string | null = null;

  @ViewChild('pagesHost') private pagesHost?: ElementRef<HTMLDivElement>;
  @ViewChild('thumbHost') private thumbHost?: ElementRef<HTMLDivElement>;

  loading = false;
  error: string | null = null;

  /** True once a document is loaded (toolbar visible). */
  pdfReady = false;
  totalPages = 0;
  currentPage = 1;
  zoomPercent = 100;
  readonly zoomPresets = [50, 75, 100, 125, 150, 186, 200];

  thumbnailsOpen = false;
  searchOpen = false;
  searchQuery = '';
  /** Semantic hits returned by the last query, in descending score order. */
  searchResults: RetrievedSource[] = [];
  /** Index of the hit whose highlight is currently drawn. */
  searchActiveIndex = -1;
  /** True once a query has completed at least once since the bar opened. */
  searchRan = false;
  searchLoading = false;
  searchError: string | null = null;
  /**
   * When true the results list is hidden but `searchResults` is kept in
   * memory so the user can reopen it (via "Show results" or a new query)
   * without having to re-run the search and re-embed the query.
   */
  searchResultsHidden = false;

  private pdf: PDFDocumentProxy | null = null;
  private loadGeneration = 0;
  private viewReady = false;
  private resizeObserver?: ResizeObserver;
  private resizeTimer: ReturnType<typeof setTimeout> | null = null;
  private pageIntersectionObserver?: IntersectionObserver;
  private thumbsRenderToken = 0;
  /** Bumped on every new search so late responses from stale requests are dropped. */
  private searchGeneration = 0;
  private readonly chatService = inject(ChatService);
  private readonly documentSession = inject(DocumentSessionService);
  private jumpSub: Subscription | undefined;
  /**
   * Kept across repaints (zoom / resize) so the highlight re-lands in the
   * right place after the canvas is re-rendered at a new scale.  Cleared
   * only on `clearHighlights()` or when a new document loads.
   */
  private activeHighlight: PdfJumpTarget | null = null;
  private highlightFadeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.jumpSub = this.documentSession.jump$.subscribe(() => {
      setTimeout(() => {
        if (!this.pdfReady) {
          return;
        }
        const src = this.documentSession.takeSourceJumpForDocument(this.documentId);
        if (src?.page) {
          this.goToSource({
            page: src.page,
            bbox: src.bbox,
            pageSize: src.page_size
          });
        }
      });
    });
  }

  ngAfterViewInit(): void {
    this.viewReady = true;
    this.setupResizeObserver();
    queueMicrotask(() => void this.loadPdf());
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['pdfData'] && this.viewReady) {
      queueMicrotask(() => void this.loadPdf());
    }
  }

  ngOnDestroy(): void {
    this.jumpSub?.unsubscribe();
    if (this.resizeTimer !== null) {
      clearTimeout(this.resizeTimer);
    }
    this.resizeObserver?.disconnect();
    this.disconnectPageObserver();
    void this.teardown();
  }

  toggleThumbnails(): void {
    this.thumbnailsOpen = !this.thumbnailsOpen;
    if (this.thumbnailsOpen) {
      // aside stays in DOM when pdfReady; CD so layout updates before painting thumbs
      this.cdr.detectChanges();
      void this.ensureThumbnailsRendered();
    }
  }

  toggleSearch(): void {
    this.searchOpen = !this.searchOpen;
    if (!this.searchOpen) {
      this.searchRan = false;
      this.searchError = null;
      // Leave searchResults in place -- reopening shouldn't force a re-query.
    } else {
      // Reopening the bar should show results again if we have any cached.
      this.searchResultsHidden = false;
    }
  }

  onSearchInput(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value;
    this.searchQuery = v;
    // A new keystroke invalidates the "No matches" empty state and
    // un-hides results so the user sees them stream in when Find runs.
    this.searchRan = false;
    this.searchError = null;
    this.searchResultsHidden = false;
  }

  /**
   * Dismiss the results dropdown without clearing state.  Called from the
   * close button on the dropdown and (implicitly) after a user clicks a
   * result: we keep them on the page they jumped to but get the overlay
   * out of the way so they can actually read it.
   */
  hideSearchResults(): void {
    this.searchResultsHidden = true;
    this.cdr.markForCheck();
  }

  /** Reopen the cached results list (toolbar chip / keyboard). */
  showSearchResults(): void {
    if (this.searchResults.length > 0) {
      this.searchResultsHidden = false;
      this.cdr.markForCheck();
    }
  }

  /**
   * Run a semantic search against the backend.  Replaces the old page-text
   * scan (which relied on pdf.js text extraction and routinely missed hits
   * on scanned / complex PDFs): we embed the query with the same model
   * that was used at ingest, search Qdrant scoped to this doc, and render
   * hits as clickable sources.
   */
  async runSearch(): Promise<void> {
    const q = this.searchQuery.trim();
    this.searchRan = true;
    this.searchError = null;
    // A fresh query always re-opens the dropdown, even if the user had
    // previously dismissed it on a stale result set.
    this.searchResultsHidden = false;

    if (!q) {
      this.searchResults = [];
      this.searchActiveIndex = -1;
      this.cdr.markForCheck();
      return;
    }
    if (!this.documentId) {
      // Happens if the component is shown without a processed doc.
      this.searchResults = [];
      this.searchError = 'Document is not ready for search yet.';
      this.cdr.markForCheck();
      return;
    }

    this.searchGeneration++;
    const gen = this.searchGeneration;
    this.searchLoading = true;
    this.cdr.markForCheck();

    try {
      const results = await firstValueFrom(
        this.chatService.searchDocument(this.documentId, q, 10)
      );
      if (gen !== this.searchGeneration) {
        return;
      }
      this.searchResults = results;
      this.searchActiveIndex = -1;
      // Auto-jump to the top hit so the user gets immediate feedback even
      // before they click anything.  Subsequent clicks override this.
      if (results.length > 0) {
        this.selectSearchResult(0);
      }
    } catch (e) {
      if (gen !== this.searchGeneration) {
        return;
      }
      this.searchResults = [];
      this.searchError =
        e instanceof Error ? e.message : 'Search failed; try again in a moment.';
    } finally {
      if (gen === this.searchGeneration) {
        this.searchLoading = false;
        this.cdr.markForCheck();
      }
    }
  }

  /** Click handler for a search-result chip: jump + highlight that hit. */
  selectSearchResult(index: number): void {
    const hit = this.searchResults[index];
    if (!hit || !hit.page) {
      return;
    }
    this.searchActiveIndex = index;
    this.goToSource({
      page: hit.page,
      bbox: hit.bbox,
      pageSize: hit.page_size
    });
    this.cdr.markForCheck();
  }

  goToPrevPage(): void {
    if (this.currentPage > 1) {
      this.scrollToPage(this.currentPage - 1);
    }
  }

  goToNextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.scrollToPage(this.currentPage + 1);
    }
  }

  async setZoom(pct: number): Promise<void> {
    this.zoomPercent = pct;
    await this.repaintPages();
  }

  /**
   * Public: scroll to `target.page` and, when the target carries a bbox,
   * draw a pulsing highlight on the rendered canvas.  Called from the chat
   * Trust panel when the user clicks a retrieved source.
   *
   * Safe to call before the PDF finishes loading -- we'll stash the target
   * and apply it after repaint.
   */
  goToSource(target: PdfJumpTarget): void {
    if (!target?.page || target.page < 1) {
      return;
    }
    const hasBox =
      Array.isArray(target.bbox) &&
      target.bbox.length === 4 &&
      Array.isArray(target.pageSize) &&
      target.pageSize.length === 2 &&
      target.pageSize[0] > 0 &&
      target.pageSize[1] > 0;
    this.activeHighlight = hasBox ? { ...target } : { page: target.page };
    this.scrollToPage(target.page);
    // DOM needs a tick to let scroll + any pending layout settle so that
    // getBoundingClientRect / canvas.style.width reflect final size.
    requestAnimationFrame(() => this.applyActiveHighlight(true));
  }

  /** Public: remove any drawn highlight and forget the pending target. */
  clearHighlights(): void {
    this.activeHighlight = null;
    if (this.highlightFadeTimer !== null) {
      clearTimeout(this.highlightFadeTimer);
      this.highlightFadeTimer = null;
    }
    const host = this.pagesHost?.nativeElement;
    host?.querySelectorAll('.pdf-source-highlight').forEach((n) => n.remove());
  }

  private scrollToPage(n: number): void {
    const host = this.pagesHost?.nativeElement;
    if (!host) {
      return;
    }
    const el = host.querySelector<HTMLElement>(`#pdf-page-${n}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    this.currentPage = n;
    if (this.documentId) {
      this.documentSession.setDocumentViewPage(this.documentId, n);
    }
    this.highlightThumbnail(n);
    this.cdr.markForCheck();
  }

  /**
   * Draw (or redraw) the pulse overlay for `this.activeHighlight`.
   *
   * We derive the CSS rect from the canvas's current rendered size so
   * the overlay scales cleanly through zoom / resize.  The backend gives
   * us bbox coordinates in an arbitrary coord system whose bounds are
   * `page_size`; rescaling to `canvas.clientWidth/Height` lands us on
   * the same pixels the user sees.
   *
   * `pulse=true` plays the enter animation; false just re-positions the
   * existing highlight (used during repaints so the flash doesn't retrigger
   * on every wheel-zoom).
   */
  private applyActiveHighlight(pulse: boolean): void {
    const target = this.activeHighlight;
    const host = this.pagesHost?.nativeElement;
    if (!host || !target) {
      return;
    }
    host.querySelectorAll('.pdf-source-highlight').forEach((n) => n.remove());

    if (!target.bbox || !target.pageSize) {
      // Page-level jump only -- nothing to draw.
      return;
    }

    const pageEl = host.querySelector<HTMLElement>(`#pdf-page-${target.page}`);
    const inner = pageEl?.querySelector<HTMLElement>('.pdf-page-inner');
    const canvas = inner?.querySelector<HTMLCanvasElement>('canvas');
    if (!inner || !canvas) {
      // Page may not be painted yet -- another repaint will call us again.
      return;
    }

    const [pw, ph] = target.pageSize;
    const renderedW = canvas.clientWidth || parseFloat(canvas.style.width) || 0;
    const renderedH = canvas.clientHeight || parseFloat(canvas.style.height) || 0;
    if (!renderedW || !renderedH || !pw || !ph) {
      return;
    }
    const sx = renderedW / pw;
    const sy = renderedH / ph;
    const [x0, y0, x1, y1] = target.bbox;
    // Pad a couple of px so text doesn't sit flush against the box edge.
    const PAD = 2;
    const left = Math.max(0, x0 * sx - PAD);
    const top = Math.max(0, y0 * sy - PAD);
    const width = Math.max(4, (x1 - x0) * sx + PAD * 2);
    const height = Math.max(4, (y1 - y0) * sy + PAD * 2);

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

    if (this.highlightFadeTimer !== null) {
      clearTimeout(this.highlightFadeTimer);
    }
    // After the pulse settles, keep a softer persistent tint for a few
    // seconds so the user can visually anchor the source before it fades.
    this.highlightFadeTimer = setTimeout(() => {
      overlay.classList.add('pdf-source-highlight--fading');
      this.highlightFadeTimer = setTimeout(() => {
        this.activeHighlight = null;
        overlay.remove();
        this.highlightFadeTimer = null;
      }, 900);
    }, 4200);
  }

  private highlightThumbnail(activePage: number): void {
    const host = this.thumbHost?.nativeElement;
    if (!host) {
      return;
    }
    host.querySelectorAll('.pdf-thumb').forEach((node) => {
      const el = node as HTMLElement;
      const p = Number(el.dataset['page']);
      el.classList.toggle('active', p === activePage);
    });
  }

  private async ensureThumbnailsRendered(): Promise<void> {
    if (!this.thumbHost?.nativeElement && this.pdfReady) {
      this.cdr.detectChanges();
    }
    const host = this.thumbHost?.nativeElement;
    const doc = this.pdf;
    if (!host || !doc) {
      return;
    }
    this.thumbsRenderToken++;
    const token = this.thumbsRenderToken;
    host.innerHTML = '';
    host.dataset['rendered'] = '1';

    const dpr = window.devicePixelRatio || 1;

    for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
      if (token !== this.thumbsRenderToken) {
        return;
      }
      const page = await doc.getPage(pageNum);
      const base = page.getViewport({ scale: 1 });
      const scale = Math.min(THUMB_MAX_WIDTH / base.width, 1);
      const viewport = page.getViewport({ scale });

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'pdf-thumb';
      btn.dataset['page'] = String(pageNum);
      if (pageNum === this.currentPage) {
        btn.classList.add('active');
      }
      btn.addEventListener('click', () => {
        this.scrollToPage(pageNum);
      });

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

      await page.render({ canvasContext: ctx, viewport, transform }).promise;
    }
  }

  private setupResizeObserver(): void {
    const el = this.pagesHost?.nativeElement;
    if (!el) {
      return;
    }
    this.resizeObserver = new ResizeObserver(() => {
      if (this.resizeTimer !== null) {
        clearTimeout(this.resizeTimer);
      }
      this.resizeTimer = setTimeout(() => {
        this.resizeTimer = null;
        void this.repaintPages();
      }, 120);
    });
    this.resizeObserver.observe(el);
  }

  private disconnectPageObserver(): void {
    this.pageIntersectionObserver?.disconnect();
    this.pageIntersectionObserver = undefined;
  }

  private attachPageObservers(host: HTMLElement): void {
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
          if (this.documentId) {
            this.documentSession.setDocumentViewPage(this.documentId, p);
          }
          this.highlightThumbnail(p);
          this.cdr.markForCheck();
        }
      },
      { root: host, rootMargin: '-40% 0px -40% 0px', threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] }
    );
    pages.forEach((el) => this.pageIntersectionObserver!.observe(el));
  }

  private applyPendingSourceJumpAfterLoad(): void {
    const src = this.documentSession.takeSourceJumpForDocument(this.documentId);
    if (!src?.page) {
      return;
    }
    this.goToSource({
      page: src.page,
      bbox: src.bbox,
      pageSize: src.page_size
    });
  }

  private async loadPdf(): Promise<void> {
    if (!this.viewReady || !this.pagesHost?.nativeElement) {
      return;
    }

    this.loadGeneration++;
    const gen = this.loadGeneration;

    this.loading = true;
    this.error = null;
    this.pdfReady = false;
    this.clearHighlights();
    this.searchResults = [];
    this.searchActiveIndex = -1;
    this.searchRan = false;
    this.searchError = null;

    await this.destroyDocument();

    if (gen !== this.loadGeneration) {
      return;
    }

    const sourceData = this.pdfData;
    if (!sourceData?.byteLength) {
      this.loading = false;
      return;
    }

    try {
      // pdf.js may transfer `data` to the worker thread and detach the buffer.
      // Always pass a copy so the session-stored ArrayBuffer remains reusable
      // when switching documents/tabs after source jumps.
      const data = sourceData.slice(0);
      ensurePdfWorker();
      const loadingTask = pdfjsLib.getDocument({
        data,
        cMapUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/cmaps/`,
        cMapPacked: true
      });
      const pdf = await loadingTask.promise;

      if (gen !== this.loadGeneration) {
        await pdf.destroy();
        return;
      }

      this.pdf = pdf;
      this.totalPages = pdf.numPages;
      const id = this.documentId;
      const saved = id ? this.documentSession.getDocumentViewPage(id) : undefined;
      this.currentPage =
        saved !== undefined && saved >= 1 && saved <= pdf.numPages ? saved : 1;
      this.pdfReady = true;
      await this.paintPages(gen);
      this.applyPendingSourceJumpAfterLoad();
      this.thumbsRenderToken++;
      if (this.thumbnailsOpen) {
        this.cdr.detectChanges();
        void this.ensureThumbnailsRendered();
      }
    } catch (e) {
      if (gen === this.loadGeneration) {
        this.error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      if (gen === this.loadGeneration) {
        this.loading = false;
      }
    }
  }

  private async repaintPages(): Promise<void> {
    await this.paintPages(this.loadGeneration);
  }

  private async paintPages(gen: number): Promise<void> {
    const host = this.pagesHost?.nativeElement;
    const doc = this.pdf;
    if (!host || !doc || gen !== this.loadGeneration) {
      return;
    }

    // Preserve scroll position across the rebuild.  Wiping `innerHTML`
    // resets scrollTop to 0, and a ResizeObserver-triggered repaint (e.g.
    // opening/closing the search sidebar) would otherwise dump the user
    // back at page 1.  We restore via scrollToPage after the canvases are
    // in place, using the page that was most-visible before the repaint.
    const pageBeforeRepaint = this.currentPage;

    this.disconnectPageObserver();
    host.innerHTML = '';

    const maxWidth = Math.max(host.clientWidth - 8, 80);
    const dpr = window.devicePixelRatio || 1;

    for (let pageNum = 1; pageNum <= doc.numPages; pageNum++) {
      if (gen !== this.loadGeneration) {
        return;
      }

      const page = await doc.getPage(pageNum);
      const baseViewport = page.getViewport({ scale: 1 });
      const fitScale = Math.min(maxWidth / baseViewport.width, 3);
      const scale = fitScale * (this.zoomPercent / 100);
      const viewport = page.getViewport({ scale });

      const wrapper = document.createElement('div');
      wrapper.className = 'pdf-page';
      wrapper.id = `pdf-page-${pageNum}`;
      wrapper.dataset['pageNumber'] = String(pageNum);

      // `.pdf-page-inner` is the positioned anchor for absolute overlays
      // (source highlights, future annotations).  SCSS already declares it
      // `position: relative` with the canvas stacked at z:0 below.
      const inner = document.createElement('div');
      inner.className = 'pdf-page-inner';

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        continue;
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
      host.appendChild(wrapper);

      await page.render({ canvasContext: ctx, viewport, transform }).promise;

      if (gen !== this.loadGeneration) {
        return;
      }
    }

    this.attachPageObservers(host);

    // Restore scroll to where the user was before the repaint.  We jump
    // without smooth scrolling because the user didn't trigger this
    // navigation -- they resized a neighbouring panel or changed zoom.
    if (pageBeforeRepaint > 1 && pageBeforeRepaint <= doc.numPages) {
      const target = host.querySelector<HTMLElement>(
        `#pdf-page-${pageBeforeRepaint}`
      );
      if (target) {
        target.scrollIntoView({ behavior: 'auto', block: 'start' });
      }
    }

    // Repainting nukes the overlay nodes along with the old canvases, so
    // re-apply without re-pulsing (user didn't click; they just zoomed).
    if (this.activeHighlight) {
      this.applyActiveHighlight(false);
    }
  }

  private async destroyDocument(): Promise<void> {
    const doc = this.pdf;
    this.pdf = null;
    this.pdfReady = false;
    this.totalPages = 0;
    this.searchResults = [];
    this.searchActiveIndex = -1;
    if (doc) {
      await doc.destroy();
    }
    const host = this.pagesHost?.nativeElement;
    if (host) {
      host.innerHTML = '';
    }
    const thumbs = this.thumbHost?.nativeElement;
    if (thumbs) {
      thumbs.innerHTML = '';
      delete thumbs.dataset['rendered'];
    }
    this.thumbsRenderToken++;
  }

  private async teardown(): Promise<void> {
    this.loadGeneration++;
    await this.destroyDocument();
  }
}
