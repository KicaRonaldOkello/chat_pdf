import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { UserSyncService } from './services/user-sync.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  // Ensures `UserSyncService` runs and syncs the Clerk user to Postgres after login.
  private readonly _userSync = inject(UserSyncService);
}
