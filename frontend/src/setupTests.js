/**
 * Jest test setup — CRA auto-picks this up from src/setupTests.js.
 *
 * Build Pack v2 errata E1: this is the Jest analogue of the Vitest
 * setup file in §R1.4. The body lands fully in §R8 when
 * src/test/renderWithProviders is created. Until then this file just
 * enables jest-dom matchers so any incidental test runs don't break.
 */
import '@testing-library/jest-dom';
