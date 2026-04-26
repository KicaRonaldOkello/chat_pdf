import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef
} from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { firstValueFrom } from 'rxjs';

import { UploadedFileItem } from '../interfaces';
import { ChatService } from '../services/chat.service';

export interface LibraryPickerDialogData {
  openDocumentIds: string[];
}

@Component({
  selector: 'app-library-picker-dialog',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatDialogModule, MatProgressSpinnerModule],
  templateUrl: './library-picker-dialog.component.html',
  styleUrl: './library-picker-dialog.component.scss'
})
export class LibraryPickerDialogComponent implements OnInit {
  private readonly dialogRef = inject(MatDialogRef<LibraryPickerDialogComponent, UploadedFileItem | undefined>);
  private readonly data = inject<LibraryPickerDialogData>(MAT_DIALOG_DATA);
  private readonly chat = inject(ChatService);
  private readonly cdr = inject(ChangeDetectorRef);

  loading = true;
  loadError: string | null = null;
  files: UploadedFileItem[] = [];

  ngOnInit(): void {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading = true;
    this.loadError = null;
    this.cdr.markForCheck();
    try {
      const all = await firstValueFrom(this.chat.getUploadedFiles(200));
      const open = new Set(this.data.openDocumentIds);
      this.files = all.filter((f) => !open.has(f.document_id));
    } catch {
      this.loadError = 'Could not load your library.';
      this.files = [];
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
    }
  }

  pick(f: UploadedFileItem): void {
    this.dialogRef.close(f);
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
