/**
 * Jest test setup — CRA auto-picks this up from src/setupTests.js.
 *
 * Build Pack v2 errata E1: Jest analogue of the Vitest setup in §R1.4.
 */
import '@testing-library/jest-dom';
import { mockMatchMedia } from './test/mockMatchMedia';

mockMatchMedia(true);

afterEach(() => {
  mockMatchMedia(true);
});

// PointerEvent isn't in jsdom — stub so userEvent + dnd-kit don't blow up.
if (typeof window !== 'undefined' && !window.PointerEvent) {
  class PointerEvent extends Event {
    constructor(type, props = {}) {
      const { bubbles, cancelable, composed, ...rest } = props;
      super(type, { bubbles, cancelable, composed });
      this.pointerId = rest.pointerId ?? 1;
      this.pointerType = rest.pointerType ?? 'mouse';
      this.button = rest.button ?? 0;
      this.buttons = rest.buttons ?? 0;
      this.clientX = rest.clientX ?? 0;
      this.clientY = rest.clientY ?? 0;
    }
  }
  window.PointerEvent = PointerEvent;
}

// ResizeObserver shim — required by @radix-ui/* shadcn primitives.
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Element.prototype.scrollIntoView shim — cmdk (used by the shadcn
// command/combobox primitive in <TradePicker/>) calls this on selection
// changes, but jsdom doesn't implement it.
if (typeof window !== 'undefined'
    && typeof window.Element !== 'undefined'
    && !window.Element.prototype.scrollIntoView) {
  window.Element.prototype.scrollIntoView = function scrollIntoView() {};
}
