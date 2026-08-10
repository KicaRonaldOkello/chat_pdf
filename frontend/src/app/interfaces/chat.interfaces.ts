export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface UploadResult {
  document_id: string;
  status: string;
  filename: string;
}

/** `GET /api/documents/recent` row */
export interface RecentDocumentItem {
  document_id: string;
  filename: string;
  uploaded_at: string;
  file_size_bytes: number | null;
}

/** `GET /api/documents/uploaded` row (Library) */
export interface UploadedFileItem {
  document_id: string;
  filename: string;
  uploaded_at: string;
  file_size_bytes: number | null;
  processing_status: string;
  display_status: 'analyzed' | 'processing' | 'error' | 'unknown';
}

export type DocumentProcessingStatus =
  | 'queued'
  | 'extracting'
  | 'tables'
  | 'images'
  | 'enriching'
  | 'embedding'
  | 'ready'
  | 'partial'
  | 'error'
  | 'failed'
  | 'invalid'
  | 'encrypted'
  | 'resource_limit'
  | 'parser_failure';

export interface DocumentStatus {
  document_id: string;
  status: DocumentProcessingStatus;
  stage: string;
  progress: number;
  filename: string;
  num_pages?: number;
  error?: string;
  /** Server-side notices (e.g. layout pipeline fell back to text-only) */
  warnings?: string[];
}

export interface RetrievedSource {
  document_id?: string;
  chunk_id?: string;
  section_path?: string;
  page?: number;
  type?: string;
  score?: number;
  preview?: string;
  /**
   * `[x0, y0, x1, y1]` in the same coordinate system as `page_size`
   * (top-left origin, units match whatever unstructured / fitz reported for
   * this page -- usually PDF points). Present when the backend was able to
   * locate the chunk's elements on the page; undefined for legacy documents.
   */
  bbox?: [number, number, number, number];
  /** `[width, height]` of the coordinate system `bbox` lives in. */
  page_size?: [number, number];
}

export interface JudgeReport {
  groundedness: number;
  relevance: number;
  completeness: number;
  concerns: string[];
  verdict: 'pass' | 'retry' | 'reject';
  threshold?: number;
  attempts_used?: number;
}

export interface GuardrailReport {
  allow: boolean;
  category: 'ok' | 'jailbreak' | 'inappropriate' | 'out_of_scope';
  reason: string;
}

export interface RouterPlan {
  route: 'structural' | 'semantic' | 'hybrid';
  section_ids: string[];
  keywords: string[];
  rewritten_query: string;
  rationale: string;
  needs_vision?: boolean;
  vision_pages?: number[];
}

/** Aggregated meta surfaced to the Trust panel at end-of-stream. */
export interface ChatStreamMeta {
  plan?: RouterPlan | null;
  guardrail?: GuardrailReport | null;
  judge?: JudgeReport | null;
  retrieved?: RetrievedSource[];
}

export interface ChatStreamHandlers {
  onStage?: (stage: string, detail?: string) => void;
  onDelta: (text: string) => void;
  onMeta?: (meta: ChatStreamMeta) => void;
}
