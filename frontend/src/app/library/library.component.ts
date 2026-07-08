import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, effect, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { UploadedFileItem } from '../interfaces';
import { ChatService } from '../services/chat.service';
import { DocumentSessionService } from '../services/document-session.service';
import { MainChromeService } from '../services/main-chrome.service';
import { formatBytesBase2OrDash } from '../util/format-bytes';
import { AuthService } from '../services/auth.service';

type SortBy = 'date' | 'size' | 'name';

@Component({
  selector: 'app-library',
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatTooltipModule],
  templateUrl: './library.component.html',
  styleUrl: './library.component.scss'
})
export class LibraryComponent {
  private readonly chrome = inject(MainChromeService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chat = inject(ChatService);
  protected readonly session = inject(DocumentSessionService);
  protected readonly authService = inject(AuthService);

  files: UploadedFileItem[] = [];
  sortBy: SortBy = 'date';
  loading = false;
  loadError: string | null = null;

  constructor() {
    effect(() => {
      this.authService.isSignedIn();
      void this.loadFiles();
    });
  }

  toggleSidebar(): void {
    this.chrome.toggleSidebar();
  }

  get sortedFiles(): UploadedFileItem[] {
    const copy = [...this.files];
    switch (this.sortBy) {
      case 'name':
        return copy.sort((a, b) =>
          a.filename.localeCompare(b.filename, undefined, { sensitivity: 'base' })
        );
      case 'size': {
        const sz = (x: UploadedFileItem) => x.file_size_bytes ?? 0;
        return copy.sort((a, b) => sz(b) - sz(a));
      }
      case 'date':
      default:
        return copy.sort(
          (a, b) =>
            new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
        );
    }
  }

  onSortChange(event: Event): void {
    const v = (event.target as HTMLSelectElement).value;
    if (v === 'date' || v === 'size' || v === 'name') {
      this.sortBy = v;
    }
  }

  rowIcon(filename: string): string {
    const n = filename.toLowerCase();
    if (n.endsWith('.pdf')) {
      return 'description';
    }
    return 'insert_drive_file';
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  }

  formatSize = formatBytesBase2OrDash;

  openFile(f: UploadedFileItem): void {
    if (this.session.uploading) {
      return;
    }
    void this.session.openRemotePdf(f.document_id, f.filename);
  }

  /** Add this upload to the current workspace, or start a new one if nothing is open. */
  addToWorkspace(f: UploadedFileItem, ev: Event): void {
    ev.stopPropagation();
    if (this.session.uploading) {
      return;
    }
    void this.session.openRemotePdf(f.document_id, f.filename, {
      append: this.session.openDocuments.length > 0
    });
  }

  private async loadFiles(): Promise<void> {
    if (!this.authService.isSignedIn()) {
      this.files = [];
      this.loadError = null;
      this.loading = false;
      this.cdr.markForCheck();
      return;
    }
    this.loading = true;
    this.cdr.markForCheck();
    try {
      this.files = await firstValueFrom(this.chat.getUploadedFiles(200));
      this.loadError = null;
    } catch {
      this.loadError = 'Could not load your files.';
      this.files = [];
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }
  }
}
