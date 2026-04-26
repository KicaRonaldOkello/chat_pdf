import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, effect, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ClerkService } from 'ngx-clerk';

import { UploadedFileItem } from '../interfaces';
import { ChatService } from '../services/chat.service';
import { MainChromeService } from '../services/main-chrome.service';
import { formatBytesBase2OrDash } from '../util/format-bytes';

type SortBy = 'date' | 'size' | 'name';

@Component({
  selector: 'app-library',
  imports: [CommonModule, MatButtonModule, MatIconModule],
  templateUrl: './library.component.html',
  styleUrl: './library.component.scss'
})
export class LibraryComponent {
  private readonly chrome = inject(MainChromeService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chat = inject(ChatService);
  protected readonly clerk = inject(ClerkService);

  files: UploadedFileItem[] = [];
  sortBy: SortBy = 'date';
  loading = false;
  loadError: string | null = null;

  constructor() {
    effect(() => {
      this.clerk.isLoaded();
      this.clerk.isSignedIn();
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

  private async loadFiles(): Promise<void> {
    if (!this.clerk.isLoaded() || !this.clerk.isSignedIn()) {
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
