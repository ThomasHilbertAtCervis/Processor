// Shared htm binding + small generic utilities.
//
// htm/react bundles its own React copy and breaks hooks — we bind htm to the
// SAME React instance everyone else imports. See ARCHITECTURE.md
// ("Exactly one React instance").

import React from 'react';
import htm from 'htm';

export const html = htm.bind(React.createElement);

export function debounce(fn, delayMs) {
  let timeoutId = null;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => fn(...args), delayMs);
  };
}

export function genId() {
  if (globalThis.crypto?.randomUUID) {
    return `node_${globalThis.crypto.randomUUID()}`;
  }
  return `node_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}
