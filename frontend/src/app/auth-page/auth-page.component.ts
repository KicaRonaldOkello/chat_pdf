import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { environment } from '../../environments/environment';

// Google Identity Services type declarations
declare global {
  interface Window {
    google: any;
  }
}

@Component({
  selector: 'app-auth-page',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './auth-page.component.html',
  styleUrl: './auth-page.component.scss'
})
export class AuthPageComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  googleLoaded = signal(false);
  protected readonly signUpMode = this.route.snapshot.data['mode'] === 'signup';

  async ngOnInit(): Promise<void> {
    // Already signed in — redirect straight to the app
    if (this.authService.isSignedIn()) {
      await this.router.navigateByUrl(this.resolveReturnUrl());
      return;
    }

    await this.authService.loadGoogleScript();
    this.googleLoaded.set(true);

    const google = (window as any).google;
    if (google?.accounts) {
      google.accounts.id.initialize({
        client_id: environment.googleClientId,
        callback: this.handleCredentialResponse.bind(this),
        auto_select: false,
        context: this.signUpMode ? 'signup' : 'signin',
      });
      google.accounts.id.renderButton(
        document.getElementById('google-login-btn')!,
        {
          theme: 'outline',
          size: 'large',
          width: '100%',
          text: this.signUpMode ? 'signup_with' : 'signin_with',
          logo_alignment: 'left',
        }
      );
    }
  }

  private async handleCredentialResponse(response: any): Promise<void> {
    try {
      await this.authService.signInWithGoogle(response.credential);
      await this.router.navigateByUrl(this.resolveReturnUrl());
    } catch (error) {
      console.error('Sign-in failed:', error);
    }
  }

  /** Allow only same-app relative paths (blocks open redirects). */
  private resolveReturnUrl(): string {
    const raw = this.route.snapshot.queryParamMap.get('returnUrl');
    if (raw && raw.startsWith('/') && !raw.startsWith('//')) {
      return raw;
    }
    return '/app';
  }
}
