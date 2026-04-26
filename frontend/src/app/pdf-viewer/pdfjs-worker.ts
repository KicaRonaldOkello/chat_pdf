import * as pdfjsLib from 'pdfjs-dist';

let configured = false;

/**
 * Binds PDF.js to a real module Worker whose script URL is emitted by the bundler
 * (`new URL(..., import.meta.url)`), avoiding fragile `/assets/pdf.worker.min.mjs` fetches
 * and the fake-worker `import()` path that breaks under `ng serve`.
 */
export function ensurePdfWorker(): void {
  if (configured) {
    return;
  }
  configured = true;

  pdfjsLib.GlobalWorkerOptions.workerPort = new Worker(
    new URL('../../../node_modules/pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url),
    { type: 'module' }
  );
}
