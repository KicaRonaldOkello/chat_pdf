import { DocumentStatus } from './chat.interfaces';

export interface OpenDocument {
  id: string;
  filename: string;
  data: ArrayBuffer;
  status: DocumentStatus | null;
  /**
   * Shown in the "Uploading" column while the HTTP request is in flight.
   * Distinguishes in-flight from server-side queued/processing once an id exists.
   */
  localUploading?: boolean;
  /** Last page the user was reading; restored when switching back to this tab. */
  pdfViewPage?: number;
}
