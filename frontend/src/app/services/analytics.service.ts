import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

import { environment } from '../../environments/environment';

declare global {
  interface Window {
    dataLayer: unknown[];
    gtag: (...args: unknown[]) => void;
  }
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly document = inject(DOCUMENT);
  private readonly router = inject(Router);
  private readonly measurementId = environment.googleAnalyticsId;

  init(): void {
    if (!this.measurementId) {
      return;
    }

    this.loadGtag();
    this.trackPageViews();
  }

  event(action: string, params: Record<string, unknown> = {}): void {
    if (window.gtag) {
      window.gtag('event', action, params);
    }
  }

  private loadGtag(): void {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function (...args: unknown[]) {
      window.dataLayer.push(args);
    };

    window.gtag('js', new Date());
    window.gtag('config', this.measurementId);

    const script = this.document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${this.measurementId}`;
    this.document.head.appendChild(script);
  }

  private trackPageViews(): void {
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => {
        window.gtag('config', this.measurementId, {
          page_path: event.urlAfterRedirects,
        });
      });
  }
}
