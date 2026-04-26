import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import type { SignInProps } from 'ngx-clerk';
import { ClerkSignInComponent } from 'ngx-clerk';

@Component({
  selector: 'app-auth-page',
  imports: [RouterLink, RouterLinkActive, ClerkSignInComponent],
  templateUrl: './auth-page.component.html',
  styleUrl: './auth-page.component.scss'
})
export class AuthPageComponent {
  readonly signInProps: SignInProps = {
    forceRedirectUrl: '/app',
    withSignUp: true,
    appearance: {
      variables: {
        colorPrimary: '#000000',
        colorText: '#1a1c1c',
        colorTextSecondary: '#5e5e5e',
        colorBackground: '#ffffff',
        colorInputBackground: '#ffffff',
        colorNeutral: '#777777',
        borderRadius: '2px',
        fontFamily: 'Inter, system-ui, sans-serif'
      },
      // Keep the sign-in block flush to the Lumen column (no centered “narrow card” strip).
      elements: {
        rootBox: {
          width: '100%',
          maxWidth: '100%',
          margin: 0,
          alignItems: 'stretch',
          justifyContent: 'flex-start',
          boxSizing: 'border-box'
        },
        card: {
          width: '100%',
          maxWidth: '100%',
          margin: 0,
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06)'
        },
        cardBox: {
          width: '100%',
          maxWidth: '100%'
        },
        header: {
          alignItems: 'flex-start',
          textAlign: 'left',
          width: '100%'
        },
        headerTitle: { textAlign: 'left' },
        headerSubtitle: { textAlign: 'left' },
        main: { width: '100%' },
        footer: { width: '100%' },
        formButtonPrimary: { width: '100%' }
      }
    }
  };
}
