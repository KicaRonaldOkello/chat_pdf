import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { environment } from '../../environments/environment';
import { AuthService } from '../services/auth.service';

type BillingPeriod = 'monthly' | 'yearly';

interface Tier {
  name: string;
  tagline: string;
  monthly: number;
  yearly: number;
  cta: string;
  popular?: boolean;
  features: string[];
}

@Component({
  selector: 'app-pricing',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './pricing.component.html',
  styleUrl: './pricing.component.scss'
})
export class PricingComponent {
  private http = inject(HttpClient);
  private router = inject(Router);
  private auth = inject(AuthService);

  protected readonly billing = signal<BillingPeriod>('monthly');
  protected readonly checkingOut = signal<string | null>(null);
  protected readonly checkoutError = signal<string | null>(null);

  protected readonly tiers: Tier[] = [
    {
      name: 'Free',
      tagline: 'Use Understanding Notes for free',
      monthly: 0,
      yearly: 0,
      cta: 'Start for free',
      features: [
        '2,000 AI words / day',
        '5 uploads / day',
        '5 MB total uploads / day',
        '2 files in scope per chat',
        'OCR for scanned PDFs',
        'Table & figure analysis',
        'Chat with your documents',
        'Cited answers with trust scores',
        'Smart summaries',
      ],
    },
    {
      name: 'Plus',
      tagline: 'Everything in Free, and',
      monthly: 12,
      yearly: 9.6,
      cta: 'Choose Plus',
      features: [
        '10,000 AI words / day',
        '10 uploads / day',
        '100 MB or 600 pages per import',
        '10 files in scope per chat',
        'AI text to speech',
        'Multi-document research workspace',
      ],
    },
    {
      name: 'Pro',
      tagline: 'Everything in Plus, and',
      monthly: 24,
      yearly: 19.2,
      cta: 'Choose Pro',
      popular: true,
      features: [
        'Unlimited AI words',
        'Unlimited imports & files in scope',
        '300 MB or 10,000 pages per import',
        'Deep research across your library',
        'Advanced models & early access',
        'Priority support',
      ],
    },
  ];

  protected price(tier: Tier): string {
    const value = this.billing() === 'yearly' ? tier.yearly : tier.monthly;
    return value === 0 ? '$0' : `$${value.toFixed(2).replace(/\.00$/, '')}`;
  }

  protected isFree(tier: Tier): boolean {
    return tier.name === 'Free';
  }

  protected async choose(tier: Tier): Promise<void> {
    if (tier.name === 'Free') {
      this.router.navigate(['/sign-up'], { queryParams: { returnUrl: '/app' } });
      return;
    }
    if (!this.auth.isSignedIn()) {
      this.router.navigate(['/sign-up'], { queryParams: { returnUrl: '/pricing' } });
      return;
    }

    this.checkoutError.set(null);
    this.checkingOut.set(tier.name);
    try {
      const response = await this.http
        .post<{ checkout_url: string }>(
          `${environment.apiBaseUrl}/api/billing/checkout`,
          { tier: tier.name.toLowerCase(), period: this.billing() },
          { headers: this.auth.getAuthHeaders() },
        )
        .toPromise();
      if (!response?.checkout_url) {
        throw new Error('No checkout URL returned');
      }
      window.location.href = response.checkout_url;
    } catch (error: unknown) {
      console.error('Checkout error:', error);
      const detail =
        (error as { error?: { detail?: string } })?.error?.detail ??
        'Could not start checkout. Please try again.';
      this.checkoutError.set(detail);
      this.checkingOut.set(null);
    }
  }
}
