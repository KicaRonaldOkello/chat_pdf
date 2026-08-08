import { HttpErrorResponse } from '@angular/common/http';
import { DestroyRef, inject, Injectable, OnDestroy } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, firstValueFrom, forkJoin, of, Subject } from 'rxjs';

import {
  CHAT_RAIL_DEFAULT,
  CHAT_RAIL_MIN,
  CHAT_RAIL_STORAGE_KEY,
  MAX_PDF_UPLOAD_BYTES,
  PDF_MIN,
  STATUS_POLL_MS
} from '../constants/const';
import {
  ChatMessage,
  ChatStreamMeta,
  DocumentProcessingStatus,
  DocumentStatus,
  OpenDocument,
  RetrievedSource
} from '../interfaces';
import { ChatService } from './chat.service';
import { LumenNotifyService } from './lumen-notify.service';

@Injectable({ providedIn: 'root' })
export class DocumentSessionService implements OnDestroy {
  /** Statuses that never change again — polling stops for them. */
  private static readonly TERMINAL_STATUSES = new Set<DocumentProcessingStatus>([
    'ready',
    'partial',
    'error',
    'failed',
    'invalid',
    'encrypted',
    'resource_limit',
    'parser_failure'
  ]);

  private static isTerminal(status: DocumentProcessingStatus | undefined): boolean {
    return !!status && DocumentSessionService.TERMINAL_STATUSES.has(status);
  }

  private static isErrorStatus(status: DocumentProcessingStatus | undefined): boolean {
    return (
      !!status &&
      status !== 'ready' &&
      status !== 'partial' &&
      DocumentSessionService.TERMINAL_STATUSES.has(status)
    );
  }

  onSessionChange?: () => void;
  private readonly chatService = inject(ChatService);
  private readonly notify = inject(LumenNotifyService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private statusPollTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly jumpSource$ = new Subject<RetrievedSource>();
  private readonly shownStatusWarningKeys = new Set<string>();
  private pendingSourceJump: RetrievedSource | null = null;

  openDocuments: OpenDocument[] = [];
  activeDocumentId: string | null = null;
  userInput = '';
  messages: ChatMessage[] = [];
  messageMeta: Record<number, ChatStreamMeta> = {};
  currentStage: string | null = null;
  expandedTrustFor: number | null = null;
  uploading = false;
  /**
   * `documentId` of a file open from the server (Home recent / Library) while
   * the blob is fetched, so list rows can show a spinner. Cleared in finally;
   * compare `documentId` before nulling in case a second open overlapped.
   */
  activeRemoteOpenId: string | null = null;
  sending = false;
  chatRailWidthPx = CHAT_RAIL_DEFAULT;
  private shouldScroll = false;

  readonly jump$ = this.jumpSource$.asObservable();

  constructor() {
    try {
      const raw = localStorage.getItem(CHAT_RAIL_STORAGE_KEY);
      if (raw) {
        const n = Number.parseInt(raw, 10);
        if (!Number.isNaN(n) && n >= CHAT_RAIL_MIN && n <= 900) {
          this.chatRailWidthPx = n;
        }
      }
    } catch {
      /* ignore */
    }
    this.destroyRef.onDestroy(() => {
      this.stopStatusPolling();
    });
  }

  get documentId(): string | null {
    return this.activeDocumentId;
  }

  get pdfData(): ArrayBuffer | null {
    const o = this.openDocuments.find((d) => d.id === this.activeDocumentId);
    return o?.data ?? null;
  }

  get activeFileName(): string | null {
    const o = this.openDocuments.find((d) => d.id === this.activeDocumentId);
    return o?.filename ?? null;
  }

  get docsInProgress(): OpenDocument[] {
    return this.openDocuments.filter(
      (d) => !DocumentSessionService.isTerminal(d.status?.status)
    );
  }

  get docsReadyList(): OpenDocument[] {
    return this.openDocuments.filter(
      (d) => d.status?.status === 'ready' || d.status?.status === 'partial'
    );
  }

  get docsFailedList(): OpenDocument[] {
    return this.openDocuments.filter((d) =>
      DocumentSessionService.isErrorStatus(d.status?.status)
    );
  }

  get isDocumentReady(): boolean {
    if (this.openDocuments.length === 0) {
      return false;
    }
    return this.openDocuments.every(
      (d) => d.status?.status === 'ready' || d.status?.status === 'partial'
    );
  }

  get hasPendingInFlight(): boolean {
    return this.openDocuments.some(
      (d) => !DocumentSessionService.isTerminal(d.status?.status)
    );
  }

  get processingBannerText(): string {
    const pending = this.openDocuments.filter(
      (d) => !DocumentSessionService.isTerminal(d.status?.status)
    );
    if (pending.length) {
      if (pending.length > 1) {
        return `Processing ${pending.length} documents…`;
      }
      const s = pending[0]!.status!;
      const pct = Math.round((s.progress ?? 0) * 100);
      return `Processing ${s.filename} - ${s.stage} (${pct}%)`;
    }
    const err = this.openDocuments.find((d) =>
      DocumentSessionService.isErrorStatus(d.status?.status)
    );
    if (err?.status) {
      return `Processing failed: ${err.status.error ?? 'unknown error'}`;
    }
    return '';
  }

  static readonly CHAT_RAIL_MIN = CHAT_RAIL_MIN;
  static readonly CHAT_RAIL_DEFAULT = CHAT_RAIL_DEFAULT;
  static readonly PDF_MIN = 200;
  static readonly CHAT_RAIL_STORAGE_KEY = CHAT_RAIL_STORAGE_KEY;

  messageRoleLabel(role: 'user' | 'assistant'): string {
    return role === 'user' ? 'Researcher' : 'Lumen';
  }

  verdictClass(verdict?: 'pass' | 'retry' | 'reject'): string {
    switch (verdict) {
      case 'pass':
        return 'trust-badge trust-badge--pass';
      case 'retry':
        return 'trust-badge trust-badge--warn';
      case 'reject':
        return 'trust-badge trust-badge--reject';
      default:
        return 'trust-badge';
    }
  }

  setShouldScroll(v: boolean): void {
    this.shouldScroll = v;
  }

  takeShouldScrollAndClear(): boolean {
    const s = this.shouldScroll;
    this.shouldScroll = false;
    return s;
  }

  onComposerKeydown(ev: KeyboardEvent, send: () => void): void {
    if (ev.key !== 'Enter' || ev.shiftKey) {
      return;
    }
    ev.preventDefault();
    send();
  }

  /**
   * Load a PDF the user already uploaded.
   * - `append: false` (default): new session, one document, go to Home (`/app`).
   * - `append: true`: add to the open set; if there are 2+ documents, go to Research (`/app/research`).
   *   Chat history is kept when appending.
   */
  async openRemotePdf(
    documentId: string,
    filename: string,
    options?: { append?: boolean }
  ): Promise<void> {
    const append = options?.append === true;
    if (append && this.openDocuments.some((d) => d.id === documentId)) {
      this.activeDocumentId = documentId;
      this.notify.warning('That document is already open in this workspace.', 3000);
      this.onSessionChange?.();
      return;
    }
    this.uploading = true;
    this.activeRemoteOpenId = documentId;
    this.onSessionChange?.();
    try {
      const blob = await firstValueFrom(this.chatService.getDocumentFileBlob(documentId));
      const buffer = await blob.arrayBuffer();
      let status: DocumentStatus | null = null;
      try {
        status = await firstValueFrom(this.chatService.getStatus(documentId));
      } catch {
        /* poller will refresh */
      }
      const newDoc: OpenDocument = {
        id: documentId,
        filename,
        data: buffer,
        status:
          status ?? {
            document_id: documentId,
            status: 'queued',
            stage: 'queued',
            progress: 0,
            filename
          }
      };

      if (append && this.openDocuments.length > 0) {
        this.openDocuments = [...this.openDocuments, newDoc];
      } else {
        this.stopStatusPolling();
        this.shownStatusWarningKeys.clear();
        this.messages = [];
        this.messageMeta = {};
        this.userInput = '';
        this.expandedTrustFor = null;
        this.openDocuments = [newDoc];
      }
      this.activeDocumentId = documentId;
      this.startStatusPolling();
      this.onSessionChange?.();
      if (this.openDocuments.length > 1) {
        void this.router.navigate(['/app/research']);
      } else {
        void this.router.navigate(['/app']);
      }
    } catch (e: unknown) {
      if (e instanceof HttpErrorResponse) {
        if (e.status === 403) {
          this.notify.error('You do not have access to this document.', 5000);
        } else if (e.status === 404) {
          this.notify.error('Document not found.', 5000);
        } else {
          this.notify.error(e.message || 'Could not open document', 5000);
        }
      } else {
        this.notify.error('Could not open document', 5000);
      }
    } finally {
      this.uploading = false;
      if (this.activeRemoteOpenId === documentId) {
        this.activeRemoteOpenId = null;
      }
      this.onSessionChange?.();
    }
  }

  clearSession(): void {
    this.stopStatusPolling();
    this.shownStatusWarningKeys.clear();
    this.pendingSourceJump = null;
    this.activeRemoteOpenId = null;
    this.openDocuments = [];
    this.activeDocumentId = null;
    this.messages = [];
    this.userInput = '';
    this.messageMeta = {};
    this.expandedTrustFor = null;
  }

  getDocumentViewPage(id: string | null): number | undefined {
    if (!id) {
      return undefined;
    }
    return this.openDocuments.find((d) => d.id === id)?.pdfViewPage;
  }

  setDocumentViewPage(id: string, page: number): void {
    const o = this.openDocuments.find((d) => d.id === id);
    if (o && page >= 1) {
      o.pdfViewPage = page;
    }
  }

  selectDocument(id: string): void {
    this.activeDocumentId = id;
  }

  removeOpenDocument(id: string): { empty: boolean } {
    const i = this.openDocuments.findIndex((d) => d.id === id);
    if (i < 0) {
      return { empty: false };
    }
    this.openDocuments.splice(i, 1);
    if (this.activeDocumentId === id) {
      this.activeDocumentId = this.openDocuments[0]?.id ?? null;
    }
    if (this.openDocuments.length === 0) {
      this.activeDocumentId = null;
    }
    return { empty: this.openDocuments.length === 0 };
  }

  requestSourceJump(source: RetrievedSource, markAfterNav?: () => void): void {
    this.pendingSourceJump = source;
    if (source.document_id) {
      const o = this.openDocuments.find((d) => d.id === source.document_id);
      if (o) {
        this.activeDocumentId = o.id;
        markAfterNav?.();
      }
    }
    this.jumpSource$.next(source);
  }

  /**
   * If a source chip jump targets this `documentId`, return it once and clear
   * (applies after the PDF for that document is ready).
   */
  takeSourceJumpForDocument(viewerDocumentId: string | null): RetrievedSource | null {
    const p = this.pendingSourceJump;
    if (!p || !viewerDocumentId) {
      return null;
    }
    const target = p.document_id ?? this.activeDocumentId;
    if (!target || target !== viewerDocumentId) {
      return null;
    }
    this.pendingSourceJump = null;
    return p;
  }

  toggleTrust(i: number): void {
    this.expandedTrustFor = this.expandedTrustFor === i ? null : i;
  }

  persistChatRailWidth(): void {
    try {
      localStorage.setItem(CHAT_RAIL_STORAGE_KEY, String(this.chatRailWidthPx));
    } catch {
      /* ignore */
    }
  }

  clampChatRailToShell(splitShell: HTMLElement | null | undefined, onClamped: () => void): void {
    if (!this.activeDocumentId || !this.pdfData || !splitShell) {
      return;
    }
    const shellW = splitShell.getBoundingClientRect().width;
    const maxChat = Math.max(CHAT_RAIL_MIN, shellW - PDF_MIN);
    if (this.chatRailWidthPx > maxChat) {
      this.chatRailWidthPx = maxChat;
      onClamped();
    }
  }

  async uploadPdfsFromFiles(
    fileList: File[],
    opts: { mode: 'single' | 'batch'; append: boolean }
  ): Promise<void> {
    if (!fileList.length) {
      return;
    }
    let files = fileList.filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length === 0) {
      this.notify.warning('Please add PDF file(s) only (.pdf).', 5000);
      return;
    }
    if (opts.mode === 'single' && files.length > 1) {
      this.notify.warning(
        'Only the first PDF was used; use Batch upload for many files at once.',
        5000
      );
      files = [files[0]!];
    }
    this.activeRemoteOpenId = null;
    this.uploading = true;
    const wantAppend = opts.append;
    let hasUploadedInThisRun = false;
    let uploaded = 0;
    try {
      for (const file of files) {
        if (file.size > MAX_PDF_UPLOAD_BYTES) {
          this.notify.error(
            `${file.name}: each PDF must be at most ${MAX_PDF_UPLOAD_BYTES / (1024 * 1024)} MB.`,
            6000
          );
          continue;
        }
        const bufferPromise = file.arrayBuffer();
        let res: { document_id: string };
        try {
          res = await firstValueFrom(this.chatService.uploadPdf(file));
        } catch (err: unknown) {
          if (err instanceof HttpErrorResponse && err.status === 413) {
            this.notify.error(
              `${file.name}: file is too large (max ${MAX_PDF_UPLOAD_BYTES / (1024 * 1024)} MB).`,
              6000
            );
            continue;
          }
          const http = err as { error?: { detail?: string } };
          const msg =
            http?.error?.detail ?? (err instanceof Error ? err.message : 'Upload failed');
          this.notify.error(`${file.name}: ${msg}`);
          continue;
        }
        let buffer: ArrayBuffer;
        try {
          buffer = await bufferPromise;
        } catch {
          this.notify.error(`Could not read: ${file.name}`);
          continue;
        }
        if (!wantAppend && !hasUploadedInThisRun) {
          this.stopStatusPolling();
          this.messages = [];
          this.openDocuments = [];
        }
        this.openDocuments.push({
          id: res.document_id,
          filename: file.name,
          data: buffer,
          status: {
            document_id: res.document_id,
            status: 'queued',
            stage: 'queued',
            progress: 0,
            filename: file.name
          }
        });
        this.activeDocumentId = res.document_id;
        hasUploadedInThisRun = true;
        uploaded++;
        this.onSessionChange?.();
      }
      if (uploaded > 0) {
        this.notify.success(
          uploaded > 1 ? `${uploaded} PDFs uploaded. Processing…` : 'PDF uploaded. Processing…',
          3200
        );
        this.startStatusPolling();
        if (this.openDocuments.length > 1) {
          void this.router.navigate(['/app/research']);
        }
      }
    } finally {
      this.uploading = false;
      this.onSessionChange?.();
    }
  }

  send(): void {
    const text = this.userInput.trim();
    if (!text || this.sending) {
      return;
    }
    if (!this.openDocuments.length || !this.activeDocumentId) {
      return;
    }
    if (!this.isDocumentReady) {
      this.notify.warning('Wait until every document in scope has finished processing.', 5000);
      return;
    }
    this.userInput = '';
    void this.runStreamingChat(text);
  }

  private async runStreamingChat(text: string): Promise<void> {
    const ids = this.openDocuments
      .filter((d) => d.status?.status === 'ready' || d.status?.status === 'partial')
      .map((d) => d.id);
    if (!ids.length) {
      return;
    }
    this.messages.push({ role: 'user', content: text });
    const history = this.messages.slice(0, -1);
    this.messages.push({ role: 'assistant', content: '' });
    const assistantIndex = this.messages.length - 1;
    this.shouldScroll = true;
    this.sending = true;
    try {
      await this.chatService.chatStream(ids, text, history, {
        onStage: (name, detail) => {
          this.currentStage = detail || name;
          this.onSessionChange?.();
        },
        onDelta: (chunk) => {
          const prev = this.messages[assistantIndex].content;
          this.messages[assistantIndex] = { role: 'assistant', content: prev + chunk };
          this.shouldScroll = true;
          this.onSessionChange?.();
        },
        onMeta: (meta) => {
          this.messageMeta[assistantIndex] = meta;
          this.onSessionChange?.();
        }
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      this.notify.error(msg || 'Chat request failed');
      this.messages.splice(assistantIndex - 1, 2);
      this.userInput = text;
      this.onSessionChange?.();
    } finally {
      this.sending = false;
      this.currentStage = null;
      this.shouldScroll = true;
      this.onSessionChange?.();
    }
  }

  private startStatusPolling(): void {
    this.stopStatusPolling();
    const run = (): void => {
      if (this.openDocuments.length === 0) {
        return;
      }
      const toPoll = this.openDocuments.filter(
        (d) => d.status == null || !DocumentSessionService.isTerminal(d.status.status)
      );
      if (toPoll.length === 0) {
        return;
      }
      forkJoin(
        toPoll.map((d) =>
          this.chatService.getStatus(d.id).pipe(catchError(() => of(null as DocumentStatus | null)))
        )
      ).subscribe({
        next: (list) => {
          toPoll.forEach((d, i) => {
            const st = list[i];
            if (st) {
              const o = this.openDocuments.find((x) => x.id === d.id);
              if (o) {
                o.status = st;
              }
            }
          });
          this.emitNewStatusWarnings();
          this.onSessionChange?.();
          const allDone = this.openDocuments.every(
            (d) => DocumentSessionService.isTerminal(d.status?.status)
          );
          if (allDone) {
            this.stopStatusPolling();
            if (
              this.openDocuments.every(
                (d) => d.status?.status === 'ready' || d.status?.status === 'partial'
              )
            ) {
              this.notify.success('Documents ready. Ask anything.', 4000);
            }
            return;
          }
          this.statusPollTimer = setTimeout(run, STATUS_POLL_MS) as ReturnType<typeof setTimeout>;
        },
        error: () => {
          this.statusPollTimer = setTimeout(run, 5000) as ReturnType<typeof setTimeout>;
        }
      });
    };
    run();
  }

  private emitNewStatusWarnings(): void {
    for (const o of this.openDocuments) {
      const w = o.status?.warnings;
      if (!w?.length) {
        continue;
      }
      for (const text of w) {
        const key = `${o.id}::${text}`;
        if (this.shownStatusWarningKeys.has(key)) {
          continue;
        }
        this.shownStatusWarningKeys.add(key);
        this.notify.warning(
          this.openDocuments.length > 1 ? `${o.filename} — ${text}` : text,
          12_000
        );
      }
    }
  }

  private stopStatusPolling(): void {
    if (this.statusPollTimer !== null) {
      clearTimeout(this.statusPollTimer);
      this.statusPollTimer = null;
    }
  }

  ngOnDestroy(): void {
    this.stopStatusPolling();
    this.jumpSource$.complete();
  }
}
