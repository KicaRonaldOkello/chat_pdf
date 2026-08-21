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
import { Subscription } from 'rxjs';

import { RetrievedSource } from '../interfaces';
import { DocumentSessionService } from '../services/document-session.service';

import {
  PDF_DEFAULT_PAGE_NUMBER,
  PDF_DEFAULT_ZOOM_PERCENT,
  PDF_REPAINT_DEBOUNCE_MS,
  PDF_THUMB_MAX_WIDTH,
  PDF_ZOOM_PRESETS
} from './const';
import type { PdfJumpTarget } from './interfaces/pdf-viewer.types';
import { PdfDocumentLoader } from './services/pdf-document-loader.service';
import { PdfHighlightManager } from './services/pdf-highlight-manager.service';
import { PdfRenderService } from './services/pdf-render.service';
import { PdfResizeManager } from './services/pdf-resize-manager.service';
import { PdfScrollManager } from './services/pdf-scroll-manager.service';
import { PdfSearchManager } from './services/pdf-search-manager.service';
import { PdfThumbnailManager } from './services/pdf-thumbnail-manager.service';

@Component({
  selector: 'app-pdf-viewer',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule],
  templateUrl: './pdf-viewer.component.html',
  styleUrl: './pdf-viewer.component.scss'
})
export class PdfViewerComponent implements OnInit, AfterViewInit, OnChanges, OnDestroy {
  @Input() pdfData: ArrayBuffer | null = null;
  @Input() documentId: string | null = null;

  @ViewChild('pagesHost') private pagesHost?: ElementRef<HTMLDivElement>;
  @ViewChild('thumbHost') private thumbHost?: ElementRef<HTMLDivElement>;

  // Public state for template binding
  loading = false;
  error: string | null = null;
  pdfReady = false;
  totalPages = 0;
  currentPage = PDF_DEFAULT_PAGE_NUMBER;
  zoomPercent = PDF_DEFAULT_ZOOM_PERCENT;
  readonly zoomPresets = PDF_ZOOM_PRESETS;
  thumbnailsOpen = false;
  searchOpen = false;
  searchQuery = '';
  searchResults: RetrievedSource[] = [];
  searchActiveIndex = -1;
  searchRan = false;
  searchLoading = false;
  searchError: string | null = null;
  searchResultsHidden = false;

  // Service injections
  private readonly documentLoader = inject(PdfDocumentLoader);
  private readonly renderService = inject(PdfRenderService);
  private readonly scrollManager = inject(PdfScrollManager);
  private readonly searchManager = inject(PdfSearchManager);
  private readonly highlightManager = inject(PdfHighlightManager);
  private readonly thumbnailManager = inject(PdfThumbnailManager);
  private readonly resizeManager = inject(PdfResizeManager);
  private readonly documentSession = inject(DocumentSessionService);
  private readonly cdr = inject(ChangeDetectorRef);

  // State management
  private viewReady = false;
  private repaintRafId: number | null = null;
  private lazyRenderRafId: number | null = null;
  private lastRepaintTime = 0;
  private jumpSub: Subscription | undefined;

  constructor() {}

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
    this.initializeServices();
    queueMicrotask(() => void this.loadPdf());
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['documentId'] && this.viewReady) {
      const prevId = changes['documentId'].previousValue;
      if (
        typeof prevId === 'string' &&
        prevId &&
        prevId !== this.documentId
      ) {
        // Persist the outgoing document's reader position under its own id
        // before loadPdf swaps in the new document.
        const host = this.pagesHost?.nativeElement;
        this.documentSession.setDocumentViewState(prevId, {
          page: this.currentPage,
          scrollTop: host?.scrollTop ?? 0
        });
      }
      this.searchManager.setDocumentId(this.documentId);
    }
    if (changes['pdfData'] && this.viewReady) {
      queueMicrotask(() => void this.loadPdf());
    }
  }

  ngOnDestroy(): void {
    this.jumpSub?.unsubscribe();
    if (this.repaintRafId !== null) {
      cancelAnimationFrame(this.repaintRafId);
      this.repaintRafId = null;
    }
    if (this.lazyRenderRafId !== null) {
      cancelAnimationFrame(this.lazyRenderRafId);
      this.lazyRenderRafId = null;
    }
    this.cleanupServices();
    void this.documentLoader.destroyDocument();
  }

  // Public methods for template binding
  toggleThumbnails(): void {
    this.thumbnailsOpen = !this.thumbnailsOpen;
    if (this.thumbnailsOpen) {
      this.cdr.detectChanges();
      void this.renderThumbnails();
    }
  }

  toggleSearch(): void {
    this.searchOpen = !this.searchOpen;
    if (!this.searchOpen) {
      this.searchManager.clearResults();
    } else {
      this.searchManager.showResults();
    }
  }

  onSearchInput(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value;
    this.searchQuery = v;
    this.searchManager.showResults();
  }

  hideSearchResults(): void {
    this.searchManager.hideResults();
    this.cdr.markForCheck();
  }

  showSearchResults(): void {
    this.searchManager.showResults();
    this.cdr.markForCheck();
  }

  async runSearch(): Promise<void> {
    await this.searchManager.runSearch(this.searchQuery);
    this.syncSearchState();
    if (this.searchResults.length > 0) {
      this.selectSearchResult(0);
    }
  }

  selectSearchResult(index: number): void {
    const hit = this.searchManager.selectResult(index);
    if (hit?.page) {
      this.goToSource({
        page: hit.page,
        bbox: hit.bbox,
        pageSize: hit.page_size
      });
    }
    this.syncSearchState();
    this.cdr.markForCheck();
  }

  goToPrevPage(): void {
    if (this.currentPage > 1) {
      this.scrollManager.scrollToPage(this.currentPage - 1);
      this.currentPage = this.scrollManager.getCurrentPage();
      this.cdr.markForCheck();
    }
  }

  goToNextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.scrollManager.scrollToPage(this.currentPage + 1);
      this.currentPage = this.scrollManager.getCurrentPage();
      this.cdr.markForCheck();
    }
  }

  async setZoom(pct: number): Promise<void> {
    this.zoomPercent = pct;
    await this.applyLayoutChange();
  }

  goToSource(target: PdfJumpTarget): void {
    if (!target?.page || target.page < 1) {
      return;
    }
    this.highlightManager.setActiveHighlight(target);
    this.scrollManager.scrollToPage(target.page);
    this.currentPage = this.scrollManager.getCurrentPage();
    this.scheduleLazyRender();
    requestAnimationFrame(() => this.highlightManager.applyHighlight(target, true));
  }

  clearHighlights(): void {
    this.highlightManager.clearHighlights();
  }

  // Private methods
  private initializeServices(): void {
    const pagesHost = this.pagesHost?.nativeElement;
    const thumbHost = this.thumbHost?.nativeElement;

    if (!pagesHost) {
      console.warn('[PdfViewer] pagesHost not available during initialization');
      return;
    }

    this.highlightManager.setHostElement(pagesHost);
    this.resizeManager.setupResizeObserver(pagesHost, () => this.scheduleResizeRepaint());
    this.scrollManager.setupScrollListener(
      pagesHost,
      (page) => this.handlePageChange(page),
      () => {
        this.saveViewState();
        this.scheduleLazyRender();
      }
    );

    if (thumbHost) {
      this.thumbnailManager.setHostElement(thumbHost);
    }

    this.searchManager.setDocumentId(this.documentId);
  }

  private cleanupServices(): void {
    this.resizeManager.disconnect();
    this.scrollManager.disconnectScrollListener();
    this.thumbnailManager.clearThumbnails();
  }

  private handlePageChange(page: number): void {
    this.currentPage = page;
    this.saveViewState();
    this.thumbnailManager.setCurrentPage(page);
    this.cdr.markForCheck();
  }

  private saveViewState(): void {
    if (!this.documentId) {
      return;
    }
    const host = this.pagesHost?.nativeElement;
    this.documentSession.setDocumentViewState(this.documentId, {
      page: this.currentPage,
      scrollTop: host?.scrollTop ?? 0
    });
  }

  private syncSearchState(): void {
    const state = this.searchManager.getState();
    this.searchResults = state.results;
    this.searchActiveIndex = state.activeIndex;
    this.searchLoading = state.loading;
    this.searchError = state.error;
    this.searchRan = state.ran;
    this.searchResultsHidden = state.hidden;
  }

  private async loadPdf(): Promise<void> {
    if (!this.viewReady || !this.pdfData?.byteLength) {
      return;
    }

    this.loading = true;
    this.error = null;
    this.pdfReady = false;
    await this.renderService.cancelRender();
    this.highlightManager.clearHighlights();
    this.searchManager.clearResults();
    this.syncSearchState();

    try {
      const pdf = await this.documentLoader.loadDocument(this.pdfData);
      this.totalPages = pdf.numPages;
      
      const saved = this.documentId 
        ? this.documentSession.getDocumentViewPage(this.documentId) 
        : undefined;
      this.currentPage = saved !== undefined && saved >= 1 && saved <= pdf.numPages 
        ? saved 
        : PDF_DEFAULT_PAGE_NUMBER;
      
      this.pdfReady = true;
      await this.renderPages();
      this.applyPendingSourceJump();
      
      if (this.thumbnailsOpen) {
        this.cdr.detectChanges();
        void this.renderThumbnails();
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (
        message.includes('worker is being destroyed') ||
        message.includes('Worker was destroyed') ||
        message.includes('Loading task cancelled')
      ) {
        // Teardown race while swapping documents — the replacement load is
        // already queued and will render this document fresh.
        console.warn('[PdfViewer] suppressed document-swap teardown error', message);
        return;
      }
      this.error = message;
    } finally {
      this.loading = false;
    }
  }

  private async renderPages(): Promise<void> {
    const host = this.pagesHost?.nativeElement;
    const pdf = this.documentLoader.getPdf();
    if (!host || !pdf) {
      return;
    }

    const gen = this.documentLoader.getLoadGeneration();
    this.renderService.setLoadGeneration(gen);
    this.resizeManager.setIsRepainting(true);
    this.scrollManager.setScrollLock(true);

    try {
      const savedState = this.documentSession.getDocumentViewState(this.documentId);

      const rendered = await this.renderService.renderDocument(pdf, {
        host,
        zoomPercent: this.zoomPercent,
        generation: gen
      });

      if (!rendered) {
        this.scheduleRepaint();
        return;
      }

      // Re-attach intersection observer to new page elements
      this.scrollManager.attachPageObservers(host);

      // Restore the exact per-document scroll position now that the
      // placeholders exist (correct page geometry).
      if (savedState.scrollTop !== undefined && savedState.scrollTop > 0) {
        host.scrollTop = savedState.scrollTop;
      }
      await this.renderVisiblePages();

      const activeHighlight = this.highlightManager.getActiveHighlight();
      if (activeHighlight) {
        requestAnimationFrame(() => {
          this.highlightManager.applyHighlight(activeHighlight, false);
        });
      }
    } finally {
      this.resizeManager.setIsRepainting(false);
      this.scrollManager.setScrollLock(false);
    }
  }

  private async renderThumbnails(): Promise<void> {
    const host = this.thumbHost?.nativeElement;
    const pdf = this.documentLoader.getPdf();
    if (!host || !pdf) {
      return;
    }

    await this.thumbnailManager.renderThumbnails(pdf, {
      maxWidth: PDF_THUMB_MAX_WIDTH,
      dpr: window.devicePixelRatio || 1
    }, (pageNum) => {
      this.scrollManager.scrollToPage(pageNum);
      this.currentPage = pageNum;
      this.cdr.markForCheck();
    });
  }

  private async repaintPages(): Promise<void> {
    const now = Date.now();
    if (now - this.lastRepaintTime < PDF_REPAINT_DEBOUNCE_MS) {
      return;
    }
    this.lastRepaintTime = now;
    await this.renderPages();
  }

  private scheduleRepaint(): void {
    if (this.repaintRafId !== null) {
      cancelAnimationFrame(this.repaintRafId);
    }
    this.repaintRafId = requestAnimationFrame(() => {
      this.repaintRafId = null;
      void this.repaintPages();
    });
  }

  private scheduleResizeRepaint(): void {
    if (this.repaintRafId !== null) {
      cancelAnimationFrame(this.repaintRafId);
    }
    this.repaintRafId = requestAnimationFrame(() => {
      this.repaintRafId = null;
      void this.applyLayoutChange();
    });
  }

  /** Resize/zoom: update geometry in place, re-render only visible pages. */
  private async applyLayoutChange(): Promise<void> {
    const host = this.pagesHost?.nativeElement;
    const pdf = this.documentLoader.getPdf();
    if (!host || !pdf || !this.pdfReady) {
      return;
    }
    const gen = this.documentLoader.getLoadGeneration();
    const ok = await this.renderService.updateLayout({
      host,
      zoomPercent: this.zoomPercent,
      generation: gen
    });
    if (!ok) {
      this.scheduleResizeRepaint();
      return;
    }
    await this.renderVisiblePages(true);
  }

  private async renderVisiblePages(force = false): Promise<void> {
    const host = this.pagesHost?.nativeElement;
    const pdf = this.documentLoader.getPdf();
    if (!host || !pdf || !this.pdfReady) {
      return;
    }
    const gen = this.documentLoader.getLoadGeneration();
    const buffer = Math.max(host.clientHeight, 800);
    const pages = this.renderService.getVisiblePageNumbers(host, buffer);
    await this.renderService.renderPagesInRange(
      pdf,
      pages,
      {
        host,
        zoomPercent: this.zoomPercent,
        generation: gen
      },
      force
    );
    this.renderService.evictDistantCanvases(host, pages);
  }

  private scheduleLazyRender(): void {
    if (this.lazyRenderRafId !== null) {
      return;
    }
    this.lazyRenderRafId = requestAnimationFrame(() => {
      this.lazyRenderRafId = null;
      void this.renderVisiblePages();
    });
  }

  private applyPendingSourceJump(): void {
    const src = this.documentSession.takeSourceJumpForDocument(this.documentId);
    if (src?.page) {
      this.goToSource({
        page: src.page,
        bbox: src.bbox,
        pageSize: src.page_size
      });
    }
  }
}
