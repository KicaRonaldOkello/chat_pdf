import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';

export interface UserProfile {
  user_id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
}

export interface UserSyncResponse {
  user_id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  session_token: string;
  created_at: string;
  last_seen_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);
  
  private readonly SESSION_TOKEN_KEY = 'session_token';
  private readonly USER_PROFILE_KEY = 'user_profile';

  // Signals for reactive state
  private _sessionToken = signal<string | null>(this.loadSessionToken());
  private _userProfile = signal<UserProfile | null>(this.loadUserProfile());

  // Public readonly signals
  isSignedIn = computed(() => this._sessionToken() !== null);
  currentUser = computed(() => this._userProfile());
  isLoaded = signal(false);

  // Google GIS script loading
  private googleScriptLoaded = false;
  private googleScriptPromise: Promise<void> | null = null;

  constructor() {
    if (this._sessionToken()) {
      this.validateSession().finally(() => this.isLoaded.set(true));
    } else {
      this.isLoaded.set(true);
    }
  }

  private loadSessionToken(): string | null {
    return localStorage.getItem(this.SESSION_TOKEN_KEY);
  }

  private loadUserProfile(): UserProfile | null {
    const stored = localStorage.getItem(this.USER_PROFILE_KEY);
    return stored ? JSON.parse(stored) : null;
  }

  private saveSessionToken(token: string): void {
    localStorage.setItem(this.SESSION_TOKEN_KEY, token);
    this._sessionToken.set(token);
  }

  private saveUserProfile(profile: UserProfile): void {
    localStorage.setItem(this.USER_PROFILE_KEY, JSON.stringify(profile));
    this._userProfile.set(profile);
  }

  private clearSession(): void {
    localStorage.removeItem(this.SESSION_TOKEN_KEY);
    localStorage.removeItem(this.USER_PROFILE_KEY);
    this._sessionToken.set(null);
    this._userProfile.set(null);
  }

  private async validateSession(): Promise<void> {
    try {
      const token = this._sessionToken();
      if (!token) return;
      const resp = await fetch('/api/users/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        this.clearSession();
        return;
      }
      const profile: UserProfile = await resp.json();
      this.saveUserProfile(profile);
    } catch {
      // Network error — keep existing session, will retry next time
    }
  }

  getAuthHeaders(): HttpHeaders {
    const token = this._sessionToken();
    if (!token) {
      return new HttpHeaders();
    }
    return new HttpHeaders().set('Authorization', `Bearer ${token}`);
  }

  async loadGoogleScript(): Promise<void> {
    if (this.googleScriptLoaded) {
      return;
    }
    if (this.googleScriptPromise) {
      return this.googleScriptPromise;
    }

    this.googleScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.onload = () => {
        this.googleScriptLoaded = true;
        resolve();
      };
      script.onerror = () => {
        this.googleScriptPromise = null;
        reject(new Error('Failed to load Google sign-in script'));
      };
      document.head.appendChild(script);
    });

    return this.googleScriptPromise;
  }

  async signInWithGoogle(credential: string): Promise<UserSyncResponse> {
    try {
      const response = await this.http.post<UserSyncResponse>(
        '/api/users/sync',
        {},
        {
          headers: new HttpHeaders().set('Authorization', `Bearer ${credential}`)
        }
      ).toPromise();

      if (!response) {
        throw new Error('No response from server');
      }

      // Save session token and user profile
      this.saveSessionToken(response.session_token);
      this.saveUserProfile({
        user_id: response.user_id,
        email: response.email,
        name: response.name,
        picture: response.picture,
      });

      return response;
    } catch (error) {
      console.error('Google sign-in error:', error);
      throw error;
    }
  }

  signOut(): void {
    const google = (window as any).google;
    if (google?.accounts?.id) {
      google.accounts.id.disableAutoSelect();
    }
    this.clearSession();
    this.router.navigate(['/']);
  }

  getSessionToken(): string | null {
    return this._sessionToken();
  }
}
