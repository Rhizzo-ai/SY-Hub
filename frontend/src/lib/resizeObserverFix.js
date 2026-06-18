/**
 * ResizeObserver loop guard — B107 FIX 1.
 *
 * Radix Popover + cmdk (the cost-code combobox) drive a tight
 * measure→reposition cycle that emits the benign browser notice
 * "ResizeObserver loop completed with undelivered notifications". CRA's
 * dev error-overlay escalates that into a full-screen red overlay — which
 * must never appear on a money screen.
 *
 * Root-cause fix (primary): wrap the ResizeObserver callback in
 * requestAnimationFrame so notifications are delivered on the NEXT frame,
 * outside the observer's synchronous delivery window. This breaks the loop
 * so the notice is never produced in the first place — it is NOT a blanket
 * error swallow.
 *
 * Targeted safety net (secondary): a capture-phase listener that stops ONLY
 * the two known-benign ResizeObserver loop messages from reaching the dev
 * overlay. Every other error propagates untouched (no global hiding).
 *
 * Idempotent + environment-guarded: no-op when ResizeObserver or
 * requestAnimationFrame is unavailable (SSR / jsdom test env), so it never
 * alters behaviour under Jest.
 */
let installed = false;

const RO_BENIGN_MESSAGES = [
  'ResizeObserver loop completed with undelivered notifications.',
  'ResizeObserver loop limit exceeded',
];

function isBenignResizeObserverMessage(message) {
  return (
    typeof message === 'string'
    && RO_BENIGN_MESSAGES.some((m) => message.includes(m))
  );
}

export function installResizeObserverLoopGuard() {
  if (installed) return;
  if (typeof window === 'undefined') return;
  installed = true;

  // 1) Root cause — defer the observer callback to the next frame.
  const NativeRO = window.ResizeObserver;
  if (
    typeof NativeRO === 'function'
    && typeof window.requestAnimationFrame === 'function'
    && !NativeRO.__rafGuarded
  ) {
    class RafResizeObserver extends NativeRO {
      constructor(callback) {
        super((entries, observer) => {
          window.requestAnimationFrame(() => {
            // Guard against teardown races where entries is undefined.
            if (!entries) return;
            callback(entries, observer);
          });
        });
      }
    }
    RafResizeObserver.__rafGuarded = true;
    window.ResizeObserver = RafResizeObserver;
  }

  // 2) Targeted safety net — keep ONLY the benign RO loop notice from
  //    reaching CRA's dev overlay. Capture phase + stopImmediatePropagation
  //    so it runs before the overlay's own window 'error' listener.
  window.addEventListener(
    'error',
    (e) => {
      const msg = e?.message
        || (typeof e?.error?.message === 'string' ? e.error.message : '');
      if (isBenignResizeObserverMessage(msg)) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    true,
  );
}

installResizeObserverLoopGuard();

export default installResizeObserverLoopGuard;
