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
  @ViewChild('composerField') private composerField?: ElementRef<HTMLTextAreaElement>;

  send(): void {
    this.session.send();
    this.resetTextareaHeight();
  }

  onComposerKeydown(ev: KeyboardEvent): void {
    if (ev.key === 'Enter' && !ev.shiftKey) {
      this.session.onComposerKeydown(ev, () => this.send());
      this.resetTextareaHeight();
    } else {
      setTimeout(() => this.autoResize(), 0);
    }
  }

  autoResize(): void {
    const el = this.composerField?.nativeElement;
    if (!el) {
      return;
    }
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  resetTextareaHeight(): void {
    setTimeout(() => {
      const el = this.composerField?.nativeElement;
      if (el) {
        el.style.height = 'auto';
      }
    }, 0);
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
