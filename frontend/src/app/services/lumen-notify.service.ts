import { inject, Injectable } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

import { LumenSnackbarComponent, LumenSnackVariant } from '../lumen-snackbar/lumen-snackbar.component';

@Injectable({ providedIn: 'root' })
export class LumenNotifyService {
  private readonly snackBar = inject(MatSnackBar);

  private open(
    message: string,
    variant: LumenSnackVariant,
    duration: number
  ): void {
    this.snackBar.openFromComponent(LumenSnackbarComponent, {
      data: { message, variant },
      duration,
      horizontalPosition: 'start',
      verticalPosition: 'bottom',
      panelClass: ['lumen-snack-host', `lumen-snack-host--${variant}`]
    });
  }

  success(message: string, duration = 4000): void {
    this.open(message, 'success', duration);
  }

  warning(message: string, duration = 8000): void {
    this.open(message, 'warning', duration);
  }

  error(message: string, duration = 10000): void {
    this.open(message, 'error', duration);
  }
}
