import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
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

  googleLoaded = signal(false);

  async ngOnInit(): Promise<void> {
    await this.authService.loadGoogleScript();
    this.googleLoaded.set(true);

    const google = (window as any).google;
    if (google?.accounts) {
      google.accounts.id.initialize({
        client_id: environment.googleClientId,
        callback: this.handleCredentialResponse.bind(this),
        auto_select: false,
      });
      google.accounts.id.renderButton(
        document.getElementById('google-login-btn')!,
        { theme: 'outline', size: 'large', width: '100%', text: 'signin_with', logo_alignment: 'left' }
      );
    }
  }

  private async handleCredentialResponse(response: any): Promise<void> {
    try {
      await this.authService.signInWithGoogle(response.credential);
      this.router.navigate(['/app']);
    } catch (error) {
      console.error('Sign-in failed:', error);
    }
  }
}
