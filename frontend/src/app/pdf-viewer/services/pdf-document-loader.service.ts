import { Injectable } from '@angular/core';
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';

import { createPdfWorker } from '../pdfjs-worker';
import { PDF_PDFJS_VERSION } from '../const';
import type { DocumentLoaderState } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for PDF document lifecycle management.
 * Handles loading, destroying, and managing PDF.js worker interactions.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfDocumentLoader {
  private pdf: PDFDocumentProxy | null = null;
  private inFlightLoad: PDFDocumentLoadingTask | null = null;
  private loadGeneration = 0;
  private pdfWorkQueue: Promise<void> = Promise.resolve();

  /**
   * Load a PDF document from ArrayBuffer data.
   * @param data - PDF data as ArrayBuffer
   * @returns Promise resolving to PDF document proxy
   */
  async loadDocument(data: ArrayBuffer): Promise<PDFDocumentProxy> {
    this.loadGeneration++;
    const myGen = this.loadGeneration;

    this.pdfWorkQueue = this.pdfWorkQueue
      .then(() => this.runLoadForGeneration(myGen, data))
      .catch((e) => {
        console.error('PDF document loader error', e);
        throw e;
      });

    await this.pdfWorkQueue;
    
    if (!this.pdf) {
      throw new Error('Failed to load PDF document');
    }

    return this.pdf;
  }

  /**
   * Destroy the current PDF document and clean up resources.
   */
  async destroyDocument(): Promise<void> {
    await this.cancelInFlightLoad();
    const doc = this.pdf;
    this.pdf = null;
    if (doc) {
      await doc.destroy();
    }
  }

  /**
   * Cancel an in-flight document load operation.
   */
  async cancelInFlightLoad(): Promise<void> {
    const task = this.inFlightLoad;
    if (!task) {
      return;
    }
    this.inFlightLoad = null;
    try {
      await task.destroy();
    } catch {
      // Idempotent / already torn down
    }
  }

  /**
   * Get the current loaded PDF document.
   */
  getPdf(): PDFDocumentProxy | null {
    return this.pdf;
  }

  /**
   * Get the current load generation number.
   */
  getLoadGeneration(): number {
    return this.loadGeneration;
  }

  /**
   * Get the current state of the document loader.
   */
  getState(): DocumentLoaderState {
    return {
      loading: this.inFlightLoad !== null,
      error: null,
      pdf: this.pdf,
      inFlightLoad: this.inFlightLoad,
      loadGeneration: this.loadGeneration
    };
  }

  /**
   * Internal method to load a document for a specific generation.
   * Prevents stale loads from completing after newer loads start.
   */
  private async runLoadForGeneration(
    myGen: number,
    sourceData: ArrayBuffer
  ): Promise<void> {
    if (!sourceData?.byteLength) {
      throw new Error('Invalid PDF data: empty buffer');
    }

    await this.destroyDocument();

    if (myGen !== this.loadGeneration) {
      return;
    }

    try {
      // pdf.js may transfer `data` to the worker thread and detach the buffer.
      // Always pass a copy so the session-stored ArrayBuffer remains reusable.
      const data = sourceData.slice(0);
      // One worker per document: see createPdfWorker() for why reusing a
      // shared worker port across loads breaks under rapid document swaps.
      pdfjsLib.GlobalWorkerOptions.workerPort = createPdfWorker();
      const loadingTask = pdfjsLib.getDocument({
        data,
        cMapUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDF_PDFJS_VERSION}/cmaps/`,
        cMapPacked: true
      });
      this.inFlightLoad = loadingTask;
      const pdf = await loadingTask.promise;
      
      if (this.inFlightLoad === loadingTask) {
        this.inFlightLoad = null;
      }

      if (myGen !== this.loadGeneration) {
        await pdf.destroy();
        return;
      }

      this.pdf = pdf;
    } catch (e) {
      await this.cancelInFlightLoad();
      throw e;
    }
  }
}
