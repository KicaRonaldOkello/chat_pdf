import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import type { RetrievedSource } from '../../interfaces';
import { ChatService } from '../../services/chat.service';
import type { SearchState } from '../interfaces/pdf-viewer.types';

/**
 * Service responsible for PDF search functionality.
 * Handles semantic search queries and result management.
 */
@Injectable({
  providedIn: 'root'
})
export class PdfSearchManager {
  private searchState: SearchState = {
    query: '',
    results: [],
    activeIndex: -1,
    loading: false,
    error: null,
    ran: false,
    hidden: false
  };
  private searchGeneration = 0;
  private documentId: string | null = null;

  constructor(private readonly chatService: ChatService) {}

  /**
   * Set the document ID for search operations.
   * @param id - Document ID
   */
  setDocumentId(id: string | null): void {
    this.documentId = id;
  }

  /**
   * Get the current document ID.
   */
  getDocumentId(): string | null {
    return this.documentId;
  }

  /**
   * Run a semantic search query.
   * @param query - Search query string
   * @returns Promise resolving when search completes
   */
  async runSearch(query: string): Promise<void> {
    const q = query.trim();
    this.searchState.ran = true;
    this.searchState.error = null;
    this.searchState.hidden = false;
    this.searchState.query = q;

    if (!q) {
      this.searchState.results = [];
      this.searchState.activeIndex = -1;
      return;
    }

    if (!this.documentId) {
      this.searchState.results = [];
      this.searchState.error = 'Document is not ready for search yet.';
      return;
    }

    this.searchGeneration++;
    const gen = this.searchGeneration;
    this.searchState.loading = true;

    try {
      const results = await firstValueFrom(
        this.chatService.searchDocument(this.documentId, q, 10)
      );
      if (gen !== this.searchGeneration) {
        return;
      }
      this.searchState.results = results;
      this.searchState.activeIndex = -1;
    } catch (e) {
      if (gen !== this.searchGeneration) {
        return;
      }
      this.searchState.results = [];
      this.searchState.error =
        e instanceof Error ? e.message : 'Search failed; try again in a moment.';
    } finally {
      if (gen === this.searchGeneration) {
        this.searchState.loading = false;
      }
    }
  }

  /**
   * Select a search result by index.
   * @param index - Index of result to select
   * @returns Selected result or null if invalid
   */
  selectResult(index: number): RetrievedSource | null {
    const hit = this.searchState.results[index];
    if (!hit) {
      return null;
    }
    this.searchState.activeIndex = index;
    return hit;
  }

  /**
   * Clear all search results and state.
   */
  clearResults(): void {
    this.searchState = {
      query: '',
      results: [],
      activeIndex: -1,
      loading: false,
      error: null,
      ran: false,
      hidden: false
    };
    this.searchGeneration++;
  }

  /**
   * Hide the search results dropdown without clearing state.
   */
  hideResults(): void {
    this.searchState.hidden = true;
  }

  /**
   * Show the search results dropdown if results exist.
   */
  showResults(): void {
    if (this.searchState.results.length > 0) {
      this.searchState.hidden = false;
    }
  }

  /**
   * Get the current search state.
   */
  getState(): SearchState {
    return { ...this.searchState };
  }

  /**
   * Get the current search query.
   */
  getQuery(): string {
    return this.searchState.query;
  }

  /**
   * Get the search results.
   */
  getResults(): RetrievedSource[] {
    return this.searchState.results;
  }

  /**
   * Get the active search result index.
   */
  getActiveIndex(): number {
    return this.searchState.activeIndex;
  }

  /**
   * Check if search is currently loading.
   */
  isLoading(): boolean {
    return this.searchState.loading;
  }

  /**
   * Check if search has been run.
   */
  hasRun(): boolean {
    return this.searchState.ran;
  }

  /**
   * Check if results are hidden.
   */
  areResultsHidden(): boolean {
    return this.searchState.hidden;
  }

  /**
   * Get the search error message.
   */
  getError(): string | null {
    return this.searchState.error;
  }
}
