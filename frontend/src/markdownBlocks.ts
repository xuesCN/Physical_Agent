/**
 * Splits a Markdown document into top-level blocks that can be rendered
 * independently, so finished blocks stop re-parsing while a message streams.
 *
 * The splitter is deliberately conservative: it only cuts at a blank line when
 * the next line starts an unambiguous new top-level block. Anything that could
 * be a continuation — indentation, a list marker, a blockquote marker, or the
 * inside of a fenced code block — keeps the text in the current block. Merging
 * too much only costs a little re-parsing; splitting too much would change what
 * the user sees (a loose list cut in half restarts its numbering).
 *
 * Contract: `splitMarkdownBlocks(md).join("") === md`. Blank separator lines
 * stay attached to the block they follow, so a growing message keeps every
 * completed block byte-identical — that stability is what lets `React.memo`
 * skip them.
 *
 * Reference-style links are document-scoped in CommonMark. When a definition
 * is present, the whole document stays in one block so independent
 * ReactMarkdown instances cannot break link resolution. This conservative
 * fallback trades a little re-parsing for exact rendered semantics.
 */

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/;
const BULLET_ITEM = /^([-*+])(\s|$)/;
const ORDERED_ITEM = /^\d{1,9}[.)](\s|$)/;
// Every CommonMark reference definition contains an adjacent `]:`, including
// definitions nested in containers and labels continued across lines. Treat
// any such token as a possible definition: a false positive only disables the
// optimization for that message, while a false negative changes rendering.
const POSSIBLE_REFERENCE_DEFINITION = /\]:/;

function isBlank(line: string): boolean {
  return line.trim() === "";
}

/**
 * A line may start a new block only when it cannot continue the previous one:
 * column 0, and not a list or blockquote marker.
 */
function startsNewBlock(line: string): boolean {
  if (/^[ \t]/.test(line)) {
    return false;
  }
  if (BULLET_ITEM.test(line) || ORDERED_ITEM.test(line)) {
    return false;
  }
  return !line.startsWith(">");
}

function closesFence(line: string, marker: string): boolean {
  const match = FENCE_CLOSE.exec(line);
  if (!match) {
    return false;
  }
  const candidate = match[1];
  return candidate[0] === marker[0] && candidate.length >= marker.length;
}

export function splitMarkdownBlocks(markdown: string): string[] {
  if (!markdown) {
    return [];
  }
  if (POSSIBLE_REFERENCE_DEFINITION.test(markdown)) {
    return [markdown];
  }

  const lines = markdown.split("\n");
  const blocks: string[] = [];
  let current: string[] = [];
  let openFence: string | null = null;
  let sawBlank = false;

  const flush = () => {
    if (current.length) {
      blocks.push(current.join(""));
      current = [];
    }
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const raw = index < lines.length - 1 ? `${line}\n` : line;

    if (openFence !== null) {
      current.push(raw);
      if (closesFence(line, openFence)) {
        openFence = null;
      }
      continue;
    }

    if (isBlank(line)) {
      current.push(raw);
      sawBlank = true;
      continue;
    }

    if (sawBlank) {
      sawBlank = false;
      if (startsNewBlock(line)) {
        flush();
      }
    }

    current.push(raw);

    const fence = FENCE_OPEN.exec(line);
    if (fence) {
      openFence = fence[1];
    }
  }

  flush();
  return blocks;
}
