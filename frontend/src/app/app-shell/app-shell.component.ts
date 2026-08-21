import { CommonModule } from '@angular/common';
import {
  ChangeDetectorRef,
  Component,
  OnDestroy,
  OnInit,
  computed,
  inject,
} from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';

import { AuthService } from '../services/auth.service';
import { BillingService } from '../services/billing.service';

import { DocumentSessionService } from '../services/document-session.service';
import { MainChromeService } from '../services/main-chrome.service';

@Component({
  selector: 'app-shell',
  imports: [
    CommonModule,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    MatTooltipModule,
    MatMenuModule
  ],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss'
})
export class AppShellComponent implements OnInit, OnDestroy {
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly chrome = inject(MainChromeService);
  private readonly billing = inject(BillingService);
  protected readonly session = inject(DocumentSessionService);
  protected readonly authService = inject(AuthService);

  /** Percentage of today's word allowance left; null while loading or unlimited. */
  protected readonly wordsRemainingPercent = computed<number | null>(() => {
    const status = this.billing.status();
    if (!status || status.plan.words_per_day < 0) {
      return null;
    }
    const used = Math.max(0, Math.min(status.plan.words_per_day, status.usage.ai_words));
    return 100 - Math.round((used / status.plan.words_per_day) * 100);
  });

  protected readonly wordsRemainingLabel = computed<string>(() => {
    const status = this.billing.status();
    if (!status) {
      return '…';
    }
    if (status.plan.words_per_day < 0) {
      return 'Unlimited';
    }
    const remaining = Math.max(0, status.plan.words_per_day - status.usage.ai_words);
    return `${remaining.toLocaleString()} words`;
  });

  sidebarCollapsed = false;
  private savedSessionNotify?: () => void;

  ngOnInit(): void {
    this.chrome.registerToggleSidebar(() => this.toggleSidebar());
    void this.billing.load();
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
