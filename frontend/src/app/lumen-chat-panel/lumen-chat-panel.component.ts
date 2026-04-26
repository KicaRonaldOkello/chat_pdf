import { CommonModule } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, inject, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { MarkdownPipe } from '../pipes/markdown.pipe';
import { DocumentSessionService } from '../services/document-session.service';

@Component({
  selector: 'app-lumen-chat-panel',
  imports: [CommonModule, FormsModule, MatProgressSpinnerModule, MatTooltipModule, MarkdownPipe],
  templateUrl: './lumen-chat-panel.component.html',
  styleUrl: './lumen-chat-panel.component.scss'
})
export class LumenChatPanelComponent implements AfterViewChecked {
  readonly session = inject(DocumentSessionService);
  @ViewChild('messagesAnchor') private messagesEnd?: ElementRef<HTMLDivElement>;
  @ViewChild('messagesScroll') private messagesScroll?: ElementRef<HTMLDivElement>;

  send(): void {
    this.session.send();
  }

  onComposerKeydown(ev: KeyboardEvent): void {
    this.session.onComposerKeydown(ev, () => this.send());
  }

  ngAfterViewChecked(): void {
    if (!this.session.takeShouldScrollAndClear()) {
      return;
    }
    const container = this.messagesScroll?.nativeElement;
    if (container) {
      container.scrollTop = container.scrollHeight;
      return;
    }
    this.messagesEnd?.nativeElement.scrollIntoView({ behavior: 'auto', block: 'end' });
  }
}
