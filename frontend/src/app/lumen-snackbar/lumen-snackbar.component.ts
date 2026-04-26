import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { MAT_SNACK_BAR_DATA, MatSnackBarRef } from '@angular/material/snack-bar';

export type LumenSnackVariant = 'success' | 'warning' | 'error';

export interface LumenSnackData {
  message: string;
  variant: LumenSnackVariant;
}

@Component({
  selector: 'app-lumen-snackbar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './lumen-snackbar.component.html',
  styleUrl: './lumen-snackbar.component.scss'
})
export class LumenSnackbarComponent {
  readonly data = inject(MAT_SNACK_BAR_DATA) as LumenSnackData;
  readonly snackRef = inject(MatSnackBarRef<LumenSnackbarComponent>);

  iconName(): string {
    switch (this.data.variant) {
      case 'success':
        return 'check_circle';
      case 'warning':
        return 'warning';
      case 'error':
        return 'error';
      default:
        return 'info';
    }
  }
}
