import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class MainChromeService {
  private toggleSidebarRef?: () => void;

  registerToggleSidebar(fn: () => void): void {
    this.toggleSidebarRef = fn;
  }

  toggleSidebar(): void {
    this.toggleSidebarRef?.();
  }
}
