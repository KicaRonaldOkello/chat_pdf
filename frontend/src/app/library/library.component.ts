import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { MainChromeService } from '../services/main-chrome.service';

@Component({
  selector: 'app-library',
  imports: [CommonModule, MatButtonModule, MatIconModule],
  templateUrl: './library.component.html',
  styleUrl: './library.component.scss'
})
export class LibraryComponent {
  private readonly chrome = inject(MainChromeService);

  toggleSidebar(): void {
    this.chrome.toggleSidebar();
  }
}
