import * as pdfjsLib from 'pdfjs-dist';

/**
 * Create a fresh PDF.js worker port whose script URL is emitted by the
 * bundler (`new URL(..., import.meta.url)`).
 *
 * A new port is created for every document load on purpose: pdf.js marks a
 * worker port as `_pendingDestroy` when a loading task is destroyed, and a
 * subsequent load reusing the same port throws
 * "PDFWorker.fromPort - the worker is being destroyed". A fresh worker per
 * document avoids that race entirely (the worker is terminated with the
 * document when it is destroyed).
 */
export function createPdfWorker(): Worker {
  return new Worker(
    new URL('../../../node_modules/pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url),
    { type: 'module' }
  );
}
