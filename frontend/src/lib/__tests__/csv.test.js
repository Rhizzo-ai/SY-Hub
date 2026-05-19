/**
 * csv.test.js — Chat 23 §R7.4.
 *
 * Pins the inline RFC-4180 toCsv contract:
 *   - Plain values are emitted unquoted.
 *   - Cells containing `,`, `"`, `\n`, or `\r` are quoted; inner
 *     double-quotes are escaped by doubling.
 *   - Row separator is CRLF.
 *   - `null` / `undefined` → empty cell.
 */
import { toCsv, downloadCsv } from '../csv';

describe('toCsv (RFC-4180)', () => {
  test('plain values are unquoted, CRLF row separator', () => {
    expect(toCsv([
      ['a', 'b', 'c'],
      [1, 2, 3],
    ])).toBe('a,b,c\r\n1,2,3');
  });

  test('cells with comma are quoted', () => {
    expect(toCsv([['a,b', 'c']])).toBe('"a,b",c');
  });

  test('cells with double-quote are quoted; inner quotes doubled', () => {
    expect(toCsv([['he said "hi"', 'x']]))
      .toBe('"he said ""hi""",x');
  });

  test('cells with newline are quoted', () => {
    expect(toCsv([['a\nb', 'c']])).toBe('"a\nb",c');
  });

  test('cells with CR are quoted', () => {
    expect(toCsv([['a\rb', 'c']])).toBe('"a\rb",c');
  });

  test('null/undefined cells emit empty string', () => {
    expect(toCsv([['a', null, undefined, 0]])).toBe('a,,,0');
  });

  test('numbers and booleans are stringified verbatim', () => {
    expect(toCsv([[1.5, true, false]])).toBe('1.5,true,false');
  });

  test('empty rows produce empty line', () => {
    expect(toCsv([[]])).toBe('');
    expect(toCsv([[], []])).toBe('\r\n');
  });

  test('every special-char case in a single row', () => {
    expect(toCsv([
      ['name', 'desc', 'amount'],
      ['Line, with comma', 'q"u"ote', 1234.5],
      ['multi\nline', 'plain', 0],
    ])).toBe(
      'name,desc,amount\r\n'
      + '"Line, with comma","q""u""ote",1234.5\r\n'
      + '"multi\nline",plain,0',
    );
  });
});

describe('downloadCsv', () => {
  test('creates a Blob URL, clicks an anchor, then revokes', () => {
    const created = jest.fn(() => 'blob:fake-url');
    const revoked = jest.fn();
    global.URL.createObjectURL = created;
    global.URL.revokeObjectURL = revoked;

    const clickSpy = jest.fn();
    const origCreateEl = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = origCreateEl(tag);
      if (tag === 'a') el.click = clickSpy;
      return el;
    });

    const name = downloadCsv('a,b\r\n1,2', 'test.csv');

    expect(created).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revoked).toHaveBeenCalledWith('blob:fake-url');
    expect(name).toBe('test.csv');

    document.createElement.mockRestore();
  });
});
