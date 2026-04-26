import { clerkPublishableKey } from './environment.autogen';
// `environment.autogen.ts` is gitignored and created by `npm run clerk:env` (also postinstall, prestart, prebuild).

export const environment = {
  production: false,
  /** Clerk publishable key (from `.env` via `scripts/clerk-env.mjs` before serve/build). */
  clerkPublishableKey
};
