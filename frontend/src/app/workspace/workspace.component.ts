import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  effect,
  ElementRef,
  HostListener,
  inject,
  OnDestroy,
  OnInit,
  ViewChild
} from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatMenuModule } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { LumenChatPanelComponent } from '../lumen-chat-panel/lumen-chat-panel.component';
import {
  LibraryPickerDialogComponent,
  LibraryPickerDialogData
} from '../library-picker-dialog/library-picker-dialog.component';
import { RecentDocumentItem, UploadedFileItem } from '../interfaces';
import { formatBytesBase2 } from '../util/format-bytes';
import { ChatService } from '../services/chat.service';
import { PdfViewerComponent } from '../pdf-viewer/pdf-viewer.component';
import { DocumentSessionService } from '../services/document-session.service';
import { LumenNotifyService } from '../services/lumen-notify.service';
import { MainChromeService } from '../services/main-chrome.service';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-workspace',
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatMenuModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    LumenChatPanelComponent,
    PdfViewerComponent
  ],
  templateUrl: './workspace.component.html',
  styleUrl: './workspace.component.scss'
})
export class WorkspaceComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly session = inject(DocumentSessionService);
  private readonly router = inject(Router);
  private readonly notify = inject(LumenNotifyService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chrome = inject(MainChromeService);
  private readonly chat = inject(ChatService);
  private readonly dialog = inject(MatDialog);
  protected readonly authService = inject(AuthService);
  /** Prior `DocumentSessionService.onSessionChange` (e.g. app shell), restored on destroy. */
  private previousSessionChange?: () => void;
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;
  @ViewChild('addFileInput') addFileInput?: ElementRef<HTMLInputElement>;
  @ViewChild('splitShell') private splitShell?: ElementRef<HTMLElement>;
  dropzoneActive = false;
  splitResizerDragging = false;
  private splitDragStartX = 0;
  private splitDragStartWidth = 0;
  recentDocuments: { documentId: string; name: string; meta: string }[] = [];
  private readonly onSplitResizeMove = (ev: MouseEvent): void => {
    const shell = this.splitShell?.nativeElement;
    if (!shell) {
      return;
    }
    const shellW = shell.getBoundingClientRect().width;
    const maxChat = Math.max(
      DocumentSessionService.CHAT_RAIL_MIN,
      shellW - DocumentSessionService.PDF_MIN
    );
    const dx = ev.clientX - this.splitDragStartX;
    let next = this.splitDragStartWidth - dx;
    next = Math.min(maxChat, Math.max(DocumentSessionService.CHAT_RAIL_MIN, next));
    if (next !== this.session.chatRailWidthPx) {
      this.session.chatRailWidthPx = next;
      this.cdr.markForCheck();
    }
  };
  private readonly onSplitResizeEnd = (): void => {
    document.removeEventListener('mousemove', this.onSplitResizeMove);
    document.removeEventListener('mouseup', this.onSplitResizeEnd, true);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    this.splitResizerDragging = false;
    this.session.persistChatRailWidth();
    this.cdr.markForCheck();
  };

  get mainTitle(): string {
    if (this.session.openDocuments.length > 0 && this.session.activeFileName) {
      return this.session.activeFileName;
    }
    return 'Home';
  }

  constructor() {
    effect(() => {
      this.authService.isSignedIn();
      void this.refreshRecentDocuments();
    });
  }

  ngOnInit(): void {
    this.previousSessionChange = this.session.onSessionChange;
    this.session.onSessionChange = () => {
      this.previousSessionChange?.();
      void this.refreshRecentDocuments();
    };
    if (this.session.openDocuments.length > 1) {
      void this.router.navigate(['/app/research']);
      return;
    }
  }

  ngAfterViewInit(): void {
    queueMicrotask(() => {
      this.session.clampChatRailToShell(this.splitShell?.nativeElement ?? null, () =>
        this.cdr.markForCheck()
      );
    });
  }

  ngOnDestroy(): void {
    this.session.onSessionChange = this.previousSessionChange;
    document.removeEventListener('mousemove', this.onSplitResizeMove);
    document.removeEventListener('mouseup', this.onSplitResizeEnd, true);
  }

  private async refreshRecentDocuments(): Promise<void> {
    if (!this.authService.isSignedIn()) {
      this.recentDocuments = [];
      this.cdr.markForCheck();
      return;
    }
    try {
      const items = await firstValueFrom(this.chat.getRecentDocuments(3));
      this.recentDocuments = items.map((r) => ({
        documentId: r.document_id,
        name: r.filename,
        meta: this.recentRowMeta(r)
      }));
    } catch {
      this.recentDocuments = [];
    }
    this.cdr.markForCheck();
  }

  private recentRowMeta(r: RecentDocumentItem): string {
    const t = this.relativeTime(r.uploaded_at);
    if (r.file_size_bytes != null) {
      return `Uploaded ${t} · ${formatBytesBase2(r.file_size_bytes)}`;
    }
    return `Uploaded ${t}`;
  }

  private relativeTime(iso: string): string {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const m = Math.floor(diff / 60_000);
    if (m < 1) {
      return 'just now';
    }
    if (m < 60) {
      return `${m}m ago`;
    }
    const h = Math.floor(m / 60);
    if (h < 24) {
      return `${h}h ago`;
    }
    const day = Math.floor(h / 24);
    if (day < 7) {
      return `${day}d ago`;
    }
    return d.toLocaleDateString();
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    this.session.clampChatRailToShell(this.splitShell?.nativeElement ?? null, () =>
      this.cdr.markForCheck()
    );
  }

  toggleSidebar(): void {
    this.chrome.toggleSidebar();
  }

  onFileSelected(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    // Snapshot before clearing: `input.files` is a live list emptied by `input.value = ''`.
    const fileArray = input.files ? Array.from(input.files) : [];
    input.value = '';
    const hasOpen = this.session.openDocuments.length > 0;
    void this.session
      .uploadPdfsFromFiles(fileArray, { mode: 'batch', append: hasOpen })
      .then(() => this.cdr.markForCheck());
  }

  onAddFileSelected(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const fileArray = input.files ? Array.from(input.files) : [];
    input.value = '';
    void this.session
      .uploadPdfsFromFiles(fileArray, {
        mode: 'batch',
        append: this.session.openDocuments.length > 0
      })
      .then(() => this.cdr.markForCheck());
  }

  triggerPdfUpload(): void {
    this.fileInput?.nativeElement.click();
  }

  triggerAddPdf(): void {
    this.addFileInput?.nativeElement.click();
  }

  onDropzoneDragOver(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.dropzoneActive = true;
  }

  onDropzoneDragLeave(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.dropzoneActive = false;
  }

  onDropzoneDrop(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.dropzoneActive = false;
    this.handleDraggedFileList(ev.dataTransfer?.files ?? null);
  }

  private handleDraggedFileList(fileList: FileList | null): void {
    const all = Array.from(fileList ?? []);
    const pdfs = all.filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    if (all.length > 0 && pdfs.length < all.length) {
      this.notify.warning('Only PDF files are accepted; extra files were skipped.', 5000);
    }
    const hasOpen = this.session.openDocuments.length > 0;
    void this.session
      .uploadPdfsFromFiles(pdfs, { mode: 'batch', append: hasOpen })
      .then(() => this.cdr.markForCheck());
  }

  onSplitResizeStart(ev: MouseEvent): void {
    ev.preventDefault();
    const shell = this.splitShell?.nativeElement;
    if (!shell) {
      return;
    }
    this.splitDragStartX = ev.clientX;
    this.splitDragStartWidth = this.session.chatRailWidthPx;
    this.splitResizerDragging = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', this.onSplitResizeMove);
    document.addEventListener('mouseup', this.onSplitResizeEnd, true);
  }

  openRecentDocument(doc: { documentId: string; name: string }): void {
    if (this.session.uploading) {
      return;
    }
    void this.session.openRemotePdf(doc.documentId, doc.name);
  }

  clearDocument(): void {
    this.session.clearSession();
    void this.router.navigate(['/app']);
  }

  openLibraryDialog(): void {
    if (!this.authService.isSignedIn()) {
      return;
    }
    const data: LibraryPickerDialogData = {
      openDocumentIds: this.session.openDocuments.map((d) => d.id)
    };
    this.dialog
      .open<LibraryPickerDialogComponent, LibraryPickerDialogData, UploadedFileItem | undefined>(
        LibraryPickerDialogComponent,
        {
          data,
          width: 'min(420px, 92vw)',
          maxWidth: '95vw',
          autoFocus: 'first-heading',
          panelClass: 'lumen-library-dialog-panel'
        }
      )
      .afterClosed()
      .subscribe((f) => {
        if (f) {
          this.addFromLibrary(f);
        }
      });
  }

  addFromLibrary(f: UploadedFileItem): void {
    const append = this.session.openDocuments.length > 0;
    void this.session
      .openRemotePdf(f.document_id, f.filename, { append })
      .then(() => this.cdr.markForCheck());
  }
}
