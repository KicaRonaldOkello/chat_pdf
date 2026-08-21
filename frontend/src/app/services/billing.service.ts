import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';

import { environment } from '../../environments/environment';
import { ChatUsageEvent } from '../interfaces/chat.interfaces';
import { AuthService } from './auth.service';

export interface BillingPlan {
  slug: string;
  name: string;
  billing_period: string | null;
  price_cents: number | null;
  words_per_day: number;
  uploads_per_day: number;
  upload_bytes_per_day: number;
  max_upload_bytes_per_import: number;
  files_in_scope: number;
}

export interface BillingUsage {
  usage_date: string;
  ai_words: number;
  uploads: number;
  upload_bytes: number;
}

export interface BillingSubscription {
  status: string;
  plan_slug: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

export interface BillingStatus {
  plan: BillingPlan;
  usage: BillingUsage;
  subscription: BillingSubscription | null;
}

@Injectable({ providedIn: 'root' })
export class BillingService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  private readonly _status = signal<BillingStatus | null>(null);
  readonly status = this._status.asReadonly();

  private loadPromise: Promise<BillingStatus | null> | null = null;

  /** Fetch billing status once per page load; call refresh() to re-fetch. */
  async load(): Promise<BillingStatus | null> {
    if (!this.auth.isSignedIn()) {
      return null;
    }
    if (!this.loadPromise) {
      this.loadPromise = this.fetchStatus().finally(() => {
        this.loadPromise = null;
      });
    }
    return this.loadPromise;
  }

  async refresh(): Promise<BillingStatus | null> {
    this.loadPromise = null;
    return this.load();
  }

  /** Apply the authoritative usage totals reported at the end of a chat stream. */
  applyUsageEvent(event: ChatUsageEvent): void {
    const status = this._status();
    if (!status) {
      return;
    }
    this._status.set({
      ...status,
      usage: {
        usage_date: event.usage_date,
        ai_words: event.ai_words,
        uploads: event.uploads,
        upload_bytes: event.upload_bytes,
      },
    });
  }

  private async fetchStatus(): Promise<BillingStatus | null> {
    try {
      const response = await this.http
        .get<BillingStatus>(`${environment.apiBaseUrl}/api/billing/status`, {
          headers: this.auth.getAuthHeaders(),
        })
        .toPromise();
      this._status.set(response ?? null);
      return response ?? null;
    } catch {
      return null;
    }
  }
}
