import { Routes } from '@angular/router';

import { AppShellComponent } from './app-shell/app-shell.component';
import { AuthPageComponent } from './auth-page/auth-page.component';
import { BatchUploadComponent } from './batch-upload/batch-upload.component';
import { BatchWorkspaceComponent } from './batch-workspace/batch-workspace.component';
import { BillingPageComponent } from './billing-page/billing-page.component';
import { LandingComponent } from './landing/landing.component';
import { LegalComponent } from './legal/legal.component';
import { PricingComponent } from './pricing/pricing.component';
import { LibraryComponent } from './library/library.component';
import { WorkspaceComponent } from './workspace/workspace.component';
import { authGuard } from './services/auth.guard';

export const routes: Routes = [
  { path: '', component: LandingComponent },
  { path: 'sign-in', component: AuthPageComponent, title: 'Understanding Notes | Sign In' },
  { path: 'sign-up', component: AuthPageComponent, data: { mode: 'signup' }, title: 'Understanding Notes | Create Account' },
  { path: 'pricing', component: PricingComponent, title: 'Understanding Notes | Pricing' },
  { path: 'privacy', component: LegalComponent, data: { legal: 'privacy' }, title: 'Understanding Notes | Privacy Policy' },
  { path: 'terms', component: LegalComponent, data: { legal: 'terms' }, title: 'Understanding Notes | Terms of Service' },
  {
    path: 'app',
    component: AppShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', component: WorkspaceComponent },
      { path: 'batch', component: BatchUploadComponent },
      { path: 'research', component: BatchWorkspaceComponent },
      { path: 'library', component: LibraryComponent },
      { path: 'billing', component: BillingPageComponent }
    ]
  }
];
