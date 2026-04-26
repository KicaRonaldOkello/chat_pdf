import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { API_BASE } from '../constants/const';
import {
  ChatMessage,
  ChatStreamHandlers,
  DocumentStatus,
  GuardrailReport,
  JudgeReport,
  RetrievedSource,
  RouterPlan,
  UploadResult
} from '../interfaces';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly base = API_BASE;

  uploadPdf(file: File): Observable<UploadResult> {
    const fd = new FormData();
    fd.append('file', file, file.name);
    return this.http.post<UploadResult>(`${this.base}/upload`, fd);
  }

  getStatus(documentId: string): Observable<DocumentStatus> {
    return this.http.get<DocumentStatus>(`${this.base}/documents/${documentId}/status`);
  }

  searchDocument(
    documentId: string,
    query: string,
    topK = 8
  ): Observable<RetrievedSource[]> {
    return this.http
      .post<{ results: RetrievedSource[] }>(
        `${this.base}/documents/${documentId}/search`,
        { query, top_k: topK }
      )
      .pipe(map((r) => r.results ?? []));
  }

  async chatStream(
    documentIds: string[],
    message: string,
    history: ChatMessage[],
    handlers: ChatStreamHandlers
  ): Promise<void> {
    if (!documentIds.length) {
      throw new Error('At least one document is required for chat');
    }
    const compactHistory = history.map(({ role, content }) => ({ role, content }));
    const body: Record<string, unknown> = {
      message,
      history: compactHistory
    };
    if (documentIds.length === 1) {
      body['document_id'] = documentIds[0];
    } else {
      body['document_ids'] = documentIds;
    }

    const res = await fetch(`${this.base}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson'
      },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      const errText = await res.text();
      let detail = errText;
      try {
        const j = JSON.parse(errText) as { detail?: unknown };
        const d = j.detail;
        if (typeof d === 'string') {
          detail = d;
        } else if (Array.isArray(d)) {
          detail = d.map((x: { msg?: string }) => x.msg ?? '').filter(Boolean).join(', ');
        }
      } catch {
        /* use errText */
      }
      throw new Error(detail || `Request failed (${res.status})`);
    }

    const reader = res.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      buffer = this.consumeNdjsonLines(buffer, handlers);
    }
    buffer += decoder.decode();
    const tail = buffer.trim();
    if (tail) {
      this.parseNdjsonLine(tail, handlers);
    }
  }

  private consumeNdjsonLines(buffer: string, handlers: ChatStreamHandlers): string {
    while (true) {
      const nl = buffer.indexOf('\n');
      if (nl === -1) {
        return buffer;
      }
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) {
        this.parseNdjsonLine(line, handlers);
      }
    }
  }

  private parseNdjsonLine(line: string, handlers: ChatStreamHandlers): void {
    let obj: Record<string, unknown>;
    try {
      obj = JSON.parse(line) as Record<string, unknown>;
    } catch {
      throw new Error(`Invalid stream line: ${line.slice(0, 80)}`);
    }

    if (typeof obj['error'] === 'string') {
      throw new Error(obj['error'] as string);
    }

    const type = typeof obj['type'] === 'string' ? (obj['type'] as string) : 'content';
    switch (type) {
      case 'stage':
        handlers.onStage?.(
          (obj['name'] as string) ?? '',
          (obj['detail'] as string) ?? ''
        );
        break;
      case 'content':
        if (typeof obj['content'] === 'string') {
          handlers.onDelta(obj['content'] as string);
        }
        break;
      case 'meta':
        handlers.onMeta?.({
          plan: (obj['plan'] as RouterPlan) ?? null,
          guardrail: (obj['guardrail'] as GuardrailReport) ?? null,
          judge: (obj['judge'] as JudgeReport) ?? null,
          retrieved: (obj['retrieved'] as RetrievedSource[]) ?? []
        });
        break;
      case 'error':
        throw new Error((obj['message'] as string) ?? 'stream error');
      default:
        if (typeof obj['content'] === 'string') {
          handlers.onDelta(obj['content'] as string);
        }
    }
  }
}
