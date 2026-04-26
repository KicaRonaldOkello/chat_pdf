import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, ElementRef, inject, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';

import { DocumentSessionService } from '../services/document-session.service';
import { LumenNotifyService } from '../services/lumen-notify.service';
import { MainChromeService } from '../services/main-chrome.service';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-batch-upload',
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatSnackBarModule],
  templateUrl: './batch-upload.component.html',
  styleUrl: './batch-upload.component.scss'
})
export class BatchUploadComponent {
  readonly session = inject(DocumentSessionService);
  private readonly router = inject(Router);
  private readonly notify = inject(LumenNotifyService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chrome = inject(MainChromeService);

  @ViewChild('fileInput') fileInput?: ElementRef<HTMLInputElement>;

  batchZoneActive = false;

  get canStartConversation(): boolean {
    return (
      this.session.docsReadyList.length > 0 &&
      this.session.docsInProgress.length === 0 &&
      !this.session.uploading
    );
  }

  toggleSidebar(): void {
    this.chrome.toggleSidebar();
  }

  onFileSelected(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const fileArray = input.files ? Array.from(input.files) : [];
    input.value = '';
    void this.session
      .uploadPdfsFromFiles(fileArray, {
        mode: 'batch',
        append: this.session.openDocuments.length > 0
      })
      .then(() => {
        this.cdr.markForCheck();
      });
  }

  triggerPdfUpload(): void {
    this.fileInput?.nativeElement.click();
  }

  onBatchZoneDragOver(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.batchZoneActive = true;
  }

  onBatchZoneDragLeave(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.batchZoneActive = false;
  }

  onBatchZoneDrop(ev: DragEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.batchZoneActive = false;
    const all = Array.from(ev.dataTransfer?.files ?? []);
    const pdfs = all.filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    if (all.length > 0 && pdfs.length < all.length) {
      this.notify.warning('Only PDF files are accepted; extra files were skipped.', 5000);
    }
    void this.session
      .uploadPdfsFromFiles(pdfs, {
        mode: 'batch',
        append: this.session.openDocuments.length > 0
      })
      .then(() => this.cdr.markForCheck());
  }

  openResearchWorkspace(): void {
    if (this.session.openDocuments.length === 0) {
      this.notify.warning('Add at least one PDF to the batch first.', 4000);
      return;
    }
    if (!this.canStartConversation) {
      this.notify.warning('Wait for uploads and processing to finish before opening chat.', 4000);
      return;
    }
    void this.router.navigate(['/app/research']);
  }
}
