import { HttpClient } from '@angular/common/http';
import { effect, inject, Injectable } from '@angular/core';
import type { ActiveSessionResource } from 'ngx-clerk';
import { ClerkService } from 'ngx-clerk';
import { firstValueFrom } from 'rxjs';

/**
 * After Clerk sign-in, upserts the user in Postgres via POST /api/users/sync (Bearer session token).
 */
@Injectable({ providedIn: 'root' })
export class UserSyncService {
  private readonly http = inject(HttpClient);
  private readonly clerk = inject(ClerkService);
  private lastSyncedSessionId: string | null = null;

  constructor() {
    effect(() => {
      if (!this.clerk.isLoaded() || !this.clerk.isSignedIn()) {
        this.lastSyncedSessionId = null;
        return;
      }
      const session = this.clerk.session();
      if (!session) {
        return;
      }
      if (session.id === this.lastSyncedSessionId) {
        return;
      }
      void this.syncSession(session);
    });
  }

  private async syncSession(session: ActiveSessionResource): Promise<void> {
    try {
      const token = await session.getToken();
      if (!token) {
        return;
      }
      await firstValueFrom(
        this.http.post<unknown>(
          '/api/users/sync',
          {},
          { headers: { Authorization: `Bearer ${token}` } }
        )
      );
      this.lastSyncedSessionId = session.id;
    } catch (err) {
      console.error('user sync to backend failed', err);
    }
  }
}
