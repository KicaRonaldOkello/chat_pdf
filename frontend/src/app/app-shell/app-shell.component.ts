import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnDestroy, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DocumentSessionService } from '../services/document-session.service';
import { MainChromeService } from '../services/main-chrome.service';

@Component({
  selector: 'app-shell',
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule
  ],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss'
})
export class AppShellComponent implements OnInit, OnDestroy {
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chrome = inject(MainChromeService);
  protected readonly session = inject(DocumentSessionService);
  readonly tokensRemainingPercent = 84;
  sidebarCollapsed = false;
  private savedSessionNotify?: () => void;

  ngOnInit(): void {
    this.chrome.registerToggleSidebar(() => this.toggleSidebar());
    this.savedSessionNotify = this.session.onSessionChange;
    this.session.onSessionChange = () => {
      this.savedSessionNotify?.();
      this.cdr.markForCheck();
    };
  }

  ngOnDestroy(): void {
    this.session.onSessionChange = this.savedSessionNotify;
    this.session.clearSession();
  }

  toggleSidebar(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
  }
}
