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
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';

import { LumenChatPanelComponent } from '../lumen-chat-panel/lumen-chat-panel.component';
import { PdfViewerComponent } from '../pdf-viewer/pdf-viewer.component';
import { DocumentSessionService } from '../services/document-session.service';
import { LumenNotifyService } from '../services/lumen-notify.service';
import { MainChromeService } from '../services/main-chrome.service';

@Component({
  selector: 'app-workspace',
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
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
  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;
  @ViewChild('addFileInput') addFileInput?: ElementRef<HTMLInputElement>;
  @ViewChild('splitShell') private splitShell?: ElementRef<HTMLElement>;
  dropzoneActive = false;
  splitResizerDragging = false;
  private splitDragStartX = 0;
  private splitDragStartWidth = 0;
  readonly recentDocuments: { name: string; meta: string }[] = [
    { name: 'Neural_Architectures_2024.pdf', meta: 'Uploaded 2h ago • 14.2 MB' },
    { name: 'Socio_Economic_Analysis_Final.pdf', meta: 'Uploaded Yesterday • 8.1 MB' },
    { name: 'Quantum_Entanglement_Draft.pdf', meta: 'Uploaded 3 days ago • 22.5 MB' }
  ];
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

  ngOnInit(): void {
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
    document.removeEventListener('mousemove', this.onSplitResizeMove);
    document.removeEventListener('mouseup', this.onSplitResizeEnd, true);
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
    void this.session
      .uploadPdfsFromFiles(fileArray, { mode: 'single', append: false })
      .then(() => this.cdr.markForCheck());
  }

  onAddFileSelected(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const fileArray = input.files ? Array.from(input.files) : [];
    input.value = '';
    void this.session
      .uploadPdfsFromFiles(fileArray, { mode: 'single', append: false })
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
    void this.session
      .uploadPdfsFromFiles(pdfs, { mode: 'single', append: false })
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

  clearDocument(): void {
    this.session.clearSession();
  }
}
