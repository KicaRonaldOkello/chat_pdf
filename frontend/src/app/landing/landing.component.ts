import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss'
})
export class LandingComponent {
  protected readonly authService = inject(AuthService);
  protected readonly signInReturnParams = { returnUrl: '/app' };
  protected readonly menuOpen = signal(false);

  /** Signed-in users go to the workspace; guests go to the sign-up page first. */
  protected researchRoute(): string {
    return this.authService.isSignedIn() ? '/app' : '/sign-up';
  }

  protected researchQueryParams(): { returnUrl: string } | undefined {
    return this.authService.isSignedIn() ? undefined : this.signInReturnParams;
  }
}
