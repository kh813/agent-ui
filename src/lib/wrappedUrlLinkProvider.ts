import type { IBufferLine, IDisposable, ILink, ILinkProvider, Terminal } from "@xterm/xterm";

// Same default URL pattern as @xterm/addon-web-links.
const DEFAULT_URL_REGEX =
  /(https?):\/\/[^\s"'!*(){}|\\^<>`]*[^\s"':,.!?{}|\\^~[\]`()<>]/;

// Ported from @xterm/addon-web-links's LinkComputer: guards against the
// parsed URL's host differing from the matched text (e.g. via decoding),
// which could otherwise be used to disguise a link's real destination.
function isValidMatch(candidate: string): boolean {
  try {
    const url = new URL(candidate);
    const authority =
      url.username && url.password
        ? `${url.protocol}//${url.username}:${url.password}@${url.host}`
        : url.username
        ? `${url.protocol}//${url.username}@${url.host}`
        : `${url.protocol}//${url.host}`;
    return candidate.toLocaleLowerCase().startsWith(authority.toLocaleLowerCase());
  } catch {
    return false;
  }
}

// A row is treated as a continuation of the row before it either because
// xterm's own auto-wrap flagged it (`isWrapped`), or because the previous
// row's text runs flush to the last column with no trailing whitespace.
// The latter covers CLIs/TUIs that word-wrap their own long tokens (like
// URLs) using cursor positioning instead of relying on terminal auto-wrap -
// xterm never marks those continuation rows as `isWrapped`, so the stock
// WebLinksAddon (which only follows `isWrapped`) can't detect a URL that
// wraps that way, even though visually it looks identical to a real wrap.
function isContinuationRow(term: Terminal, row: number, line: IBufferLine): boolean {
  if (line.isWrapped) return true;
  const prev = term.buffer.active.getLine(row - 1);
  if (!prev) return false;
  return prev.translateToString(true).length >= term.cols;
}

// Builds the logical line containing row `y` by joining it with any
// preceding/following rows that look like continuations, up to a 2048
// character budget. Mirrors addon-web-links' windowing so a single matched
// token (like a URL) can span an arbitrary number of wrapped rows.
function getWindowedLineStrings(term: Terminal, y: number): [string[], number] {
  const rows: string[] = [];
  let startRow = y;
  let endRow = y;

  const curLine = term.buffer.active.getLine(y);
  if (!curLine) return [rows, startRow];
  const curText = curLine.translateToString(true);

  if (isContinuationRow(term, y, curLine) && curText[0] !== " ") {
    let len = 0;
    let line: IBufferLine | undefined;
    while ((line = term.buffer.active.getLine(--startRow)) && len < 2048) {
      const str = line.translateToString(true);
      len += str.length;
      rows.push(str);
      if (!(isContinuationRow(term, startRow, line) && str.indexOf(" ") === -1)) break;
    }
    rows.reverse();
  }

  rows.push(curText);

  {
    let len = 0;
    let line: IBufferLine | undefined;
    while ((line = term.buffer.active.getLine(++endRow)) && isContinuationRow(term, endRow, line) && len < 2048) {
      const str = line.translateToString(true);
      len += str.length;
      rows.push(str);
      if (str.indexOf(" ") !== -1) break;
    }
  }

  return [rows, startRow];
}

// Maps a character offset within the joined multi-row string back to a
// {row, col} buffer position, accounting for wide (double-width) cells.
function mapStrIdx(term: Terminal, row: number, col: number, offset: number): [number, number] {
  const buffer = term.buffer.active;
  const nullCell = buffer.getNullCell();
  let c = col;
  while (offset) {
    const line = buffer.getLine(row);
    if (!line) return [-1, -1];
    for (let n = c; n < line.length; n++) {
      line.getCell(n, nullCell);
      const chars = nullCell.getChars();
      if (nullCell.getWidth()) {
        offset -= chars.length || 1;
        if (n === line.length - 1 && chars === "") {
          const nextLine = buffer.getLine(row + 1);
          if (nextLine?.isWrapped) {
            nextLine.getCell(0, nullCell);
            if (nullCell.getWidth() === 2) offset += 1;
          }
        }
      }
      if (offset < 0) return [row, n];
    }
    row++;
    c = 0;
  }
  return [row, c];
}

function computeLinks(term: Terminal, bufferLineNumber: number, handler: (event: MouseEvent, uri: string) => void): ILink[] {
  const regex = new RegExp(DEFAULT_URL_REGEX.source, "g");
  const [rowStrings, startRow] = getWindowedLineStrings(term, bufferLineNumber - 1);
  const joined = rowStrings.join("");

  const links: ILink[] = [];
  let match: RegExpExecArray | null;
  while ((match = regex.exec(joined))) {
    const text = match[0];
    if (!isValidMatch(text)) continue;

    const [startLineIdx, startCol] = mapStrIdx(term, startRow, 0, match.index);
    const [endLineIdx, endCol] = mapStrIdx(term, startLineIdx, startCol, text.length);
    if (startLineIdx === -1 || startCol === -1 || endLineIdx === -1 || endCol === -1) continue;

    links.push({
      range: {
        start: { x: startCol + 1, y: startLineIdx + 1 },
        end: { x: endCol, y: endLineIdx + 1 },
      },
      text,
      activate: handler,
    });
  }
  return links;
}

// Registers a link provider equivalent to @xterm/addon-web-links's default
// WebLinksAddon, except it also detects URLs wrapped by the underlying
// program itself (not just xterm's own auto-wrap). See isContinuationRow.
export function registerWrappedUrlLinkProvider(
  term: Terminal,
  handler: (event: MouseEvent, uri: string) => void
): IDisposable {
  const provider: ILinkProvider = {
    provideLinks(bufferLineNumber, callback) {
      callback(computeLinks(term, bufferLineNumber, handler));
    },
  };
  return term.registerLinkProvider(provider);
}
