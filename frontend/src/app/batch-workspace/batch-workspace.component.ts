import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  HostListener,
  inject,
  OnDestroy,
  OnInit,
  ViewChild
} from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LumenChatPanelComponent } from '../lumen-chat-panel/lumen-chat-panel.component';
import {
  LibraryPickerDialogComponent,
  LibraryPickerDialogData
} from '../library-picker-dialog/library-picker-dialog.component';
import { PdfViewerComponent } from '../pdf-viewer/pdf-viewer.component';
import { UploadedFileItem } from '../interfaces';
import { DocumentSessionService } from '../services/document-session.service';
import { MainChromeService } from '../services/main-chrome.service';
import { ClerkService } from 'ngx-clerk';

@Component({
  selector: 'app-batch-workspace',
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
    LumenChatPanelComponent,
    PdfViewerComponent
  ],
  templateUrl: './batch-workspace.component.html',
  styleUrl: './batch-workspace.component.scss'
})
export class BatchWorkspaceComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly session = inject(DocumentSessionService);
  private readonly router = inject(Router);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chrome = inject(MainChromeService);
  private readonly dialog = inject(MatDialog);
  protected readonly clerk = inject(ClerkService);
  @ViewChild('splitShell') private splitShell?: ElementRef<HTMLElement>;
  @ViewChild('addFileInput') private addFileInput?: ElementRef<HTMLInputElement>;
  splitResizerDragging = false;
  private splitDragStartX = 0;
  private splitDragStartWidth = 0;
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
    if (this.session.openDocuments.length > 1) {
      return `${this.session.openDocuments.length} documents`;
    }
    return this.session.activeFileName ?? 'Research';
  }

  ngOnInit(): void {
    if (this.session.openDocuments.length === 0) {
      void this.router.navigate(['/app/batch']);
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
    document.removeEventListener('mousemove', this.onSplitResizeMove);
    document.removeEventListener('mouseup', this.onSplitResizeEnd, true);
  }

  @HostListener('window:resize')
  onWindowResize(): void {
    this.session.clampChatRailToShell(
      this.splitShell?.nativeElement as HTMLElement,
      () => this.cdr.markForCheck()
    );
  }

  toggleSidebar(): void {
    this.chrome.toggleSidebar();
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

  selectTab(id: string): void {
    this.session.selectDocument(id);
  }

  removeDocument(id: string, ev: Event): void {
    ev.stopPropagation();
    const { empty } = this.session.removeOpenDocument(id);
    if (empty) {
      void this.router.navigate(['/app/batch']);
    }
  }

  triggerAddPdf(): void {
    this.addFileInput?.nativeElement.click();
  }

  onAddFileSelected(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const fileArray = input.files ? Array.from(input.files) : [];
    input.value = '';
    void this.session
      .uploadPdfsFromFiles(fileArray, { mode: 'batch', append: true })
      .then(() => this.cdr.markForCheck());
  }

  openLibraryDialog(): void {
    if (!this.clerk.isLoaded() || !this.clerk.isSignedIn()) {
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
    void this.session
      .openRemotePdf(f.document_id, f.filename, { append: true })
      .then(() => this.cdr.markForCheck());
  }

  clearAll(): void {
    this.session.clearSession();
    void this.router.navigate(['/app']);
  }
}
