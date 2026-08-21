import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { BillingService } from '../services/billing.service';

interface Meter {
  label: string;
  used: number;
  limit: number;
  unit: string;
  pct: number;
}

@Component({
  selector: 'app-billing-page',
  imports: [DatePipe, RouterLink],
  templateUrl: './billing-page.component.html',
  styleUrl: './billing-page.component.scss',
})
export class BillingPageComponent {
  private route = inject(ActivatedRoute);
  private billing = inject(BillingService);

  protected readonly status = this.billing.status;
  protected checkoutOutcome = signal<'success' | 'cancelled' | null>(null);
  protected loading = signal(true);
  protected error = signal<string | null>(null);

  constructor() {
    const outcome = this.route.snapshot.queryParamMap.get('checkout');
    if (outcome === 'success' || outcome === 'cancelled') {
      this.checkoutOutcome.set(outcome);
    }
    void this.load();
  }

  private async load(): Promise<void> {
    if (this.checkoutOutcome() === 'success') {
      // Bypass the page-lifetime cache: the status may have changed while
      // the user was away at Dodo's hosted checkout.
      await this.billing.refresh();
    } else {
      await this.billing.load();
    }
    if (!this.billing.status()) {
      this.error.set('Could not load billing status.');
    }
    this.loading.set(false);
  }

  protected price(): string {
    const cents = this.status()?.plan.price_cents ?? 0;
    if (cents === 0) return '$0';
    return `$${(cents / 100).toFixed(2).replace(/\.00$/, '')}`;
  }

  protected period(): string {
    const period = this.status()?.plan.billing_period;
    if (period === 'yearly') return '/ year';
    if (period === 'monthly') return '/ month';
    return '';
  }

  protected planSubtitle(): string {
    const status = this.status()?.subscription?.status;
    switch (status) {
      case 'pending':
        return 'Payment processing…';
      case 'on_hold':
        return 'On hold — update your payment method to reactivate.';
      case 'cancelled':
        return 'Cancelled — access continues until the end of your billing period.';
      case 'failed':
        return 'Payment failed — choose a plan to continue.';
      case 'expired':
        return 'Expired — choose a plan to continue.';
      default:
        return 'Active plan';
    }
  }

  protected isPlanProblem(): boolean {
    const status = this.status()?.subscription?.status;
    return status === 'failed' || status === 'expired';
  }

  protected showPeriodDate(): boolean {
    const status = this.status()?.subscription?.status;
    return (
      status === 'active' ||
      status === 'pending' ||
      status === 'on_hold' ||
      status === 'cancelled'
    );
  }

  protected periodDateLabel(): string {
    return this.status()?.subscription?.status === 'cancelled'
      ? 'Access until'
      : 'Renews';
  }

  protected meters(): Meter[] {
    const status = this.status();
    if (!status) return [];
    const { plan, usage } = status;
    const pct = (used: number, limit: number) => (limit <= 0 ? 0 : Math.min(100, Math.round((used / limit) * 100)));
    return [
      {
        label: 'AI words',
        used: usage.ai_words,
        limit: plan.words_per_day,
        unit: 'words today',
      },
      {
        label: 'Uploads',
        used: usage.uploads,
        limit: plan.uploads_per_day,
        unit: 'uploads today',
      },
      {
        label: 'Storage',
        used: usage.upload_bytes,
        limit: plan.upload_bytes_per_day,
        unit: 'uploaded today',
      },
    ].map((m) => ({ ...m, pct: pct(m.used, m.limit) }));
  }

  protected limitLabel(meter: Meter): string {
    if (meter.limit <= 0) return 'Unlimited';
    if (meter.limit >= 1024 * 1024) {
      return `${(meter.limit / (1024 * 1024)).toFixed(0)} MB`;
    }
    return meter.limit.toLocaleString();
  }

  protected usedLabel(meter: Meter): string {
    if (meter.unit === 'uploaded today' && meter.used >= 1024 * 1024) {
      return `${(meter.used / (1024 * 1024)).toFixed(1)} MB`;
    }
    return meter.used.toLocaleString();
  }
}
