import { Routes } from '@angular/router';

import { AppShellComponent } from './app-shell/app-shell.component';
import { AuthPageComponent } from './auth-page/auth-page.component';
import { BatchUploadComponent } from './batch-upload/batch-upload.component';
import { BatchWorkspaceComponent } from './batch-workspace/batch-workspace.component';
import { LandingComponent } from './landing/landing.component';
import { LibraryComponent } from './library/library.component';
import { WorkspaceComponent } from './workspace/workspace.component';
import { authGuard } from './services/auth.guard';

export const routes: Routes = [
  { path: '', component: LandingComponent },
  { path: 'sign-in', component: AuthPageComponent, title: 'Lumen | Authentication' },
  {
    path: 'app',
    component: AppShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', component: WorkspaceComponent },
      { path: 'batch', component: BatchUploadComponent },
      { path: 'research', component: BatchWorkspaceComponent },
      { path: 'library', component: LibraryComponent }
    ]
  }
];
