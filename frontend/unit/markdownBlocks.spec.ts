import { expect, test } from "@playwright/test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import { splitMarkdownBlocks } from "../src/markdownBlocks";

const SAMPLES = [
  "",
  "single paragraph",
  "one\n\ntwo\n\nthree",
  "# Heading\n\ntext after heading",
  "para\n\n```python\nprint(1)\n\nprint(2)\n```\n\ntail",
  "1. first\n\n2. second\n\n3. third",
  "- alpha\n\n- beta\n\nclosing paragraph",
  "> quoted\n\n> still quoted\n\nafter quote",
  "text\n\n    indented code\n\n    more code\n\nafter",
  "trailing newlines\n\n\n"
];

test("splitter is lossless: blocks always rejoin to the original document", () => {
  for (const sample of SAMPLES) {
    expect(splitMarkdownBlocks(sample).join("")).toBe(sample);
  }
});

test("a fenced code block containing blank lines stays in one block", () => {
  const blocks = splitMarkdownBlocks("intro\n\n```js\nconst a = 1;\n\nconst b = 2;\n```\n\nouttro");
  const fenceBlocks = blocks.filter((block) => block.includes("```"));
  expect(fenceBlocks).toHaveLength(1);
  expect(fenceBlocks[0]).toContain("const a = 1;");
  expect(fenceBlocks[0]).toContain("const b = 2;");
});

test("a loose list is never cut apart, so its numbering cannot restart", () => {
  const blocks = splitMarkdownBlocks("1. first\n\n2. second\n\n3. third");
  expect(blocks).toHaveLength(1);

  const bullets = splitMarkdownBlocks("- alpha\n\n- beta");
  expect(bullets).toHaveLength(1);
});

test("blockquotes and indented code are not split away from their opener", () => {
  expect(splitMarkdownBlocks("> line one\n\n> line two")).toHaveLength(1);
  expect(splitMarkdownBlocks("text\n\n    indented code\n\n    still code")).toHaveLength(1);
});

test("unambiguous top-level blocks are separated", () => {
  expect(splitMarkdownBlocks("one\n\ntwo\n\nthree")).toHaveLength(3);
  expect(splitMarkdownBlocks("# Title\n\nbody\n\n## Sub\n\nmore")).toHaveLength(4);
});

test("an unterminated fence keeps the tail in a single growing block", () => {
  // Mid-stream the closing fence has not arrived yet; everything after the
  // opener must stay together rather than being cut at the blank line.
  const blocks = splitMarkdownBlocks("intro\n\n```js\nconst a = 1;\n\nconst b = 2;");
  expect(blocks).toHaveLength(2);
  expect(blocks[1]).toContain("const b = 2;");
});

test("streaming append keeps every completed block byte-identical", () => {
  // This is the property React.memo relies on: as the message grows, only the
  // last block may change. Any churn in earlier blocks would silently disable
  // the optimization.
  const full = "# Title\n\nfirst paragraph\n\n```js\nconst a = 1;\n```\n\nlast paragraph here";
  let previous = splitMarkdownBlocks(full.slice(0, 1));

  for (let size = 2; size <= full.length; size += 1) {
    const current = splitMarkdownBlocks(full.slice(0, size));
    const stable = Math.min(previous.length, current.length) - 1;
    for (let index = 0; index < stable; index += 1) {
      expect(current[index]).toBe(previous[index]);
    }
    expect(current.length).toBeGreaterThanOrEqual(previous.length);
    previous = current;
  }

  expect(previous.join("")).toBe(full);
});

test("document-wide reference links keep resolving after block optimization", () => {
  const source = "See [the guide][guide].\n\n[guide]: https://example.com/guide";
  const rendered = splitMarkdownBlocks(source)
    .map((block) => renderToStaticMarkup(createElement(ReactMarkdown, null, block)))
    .join("");

  expect(rendered).toContain('<a href="https://example.com/guide">the guide</a>');
});

test("reference definitions inside containers remain document-wide", () => {
  const source = "> [guide]: https://example.com/guide\n\nSee [the guide][guide].";
  const rendered = splitMarkdownBlocks(source)
    .map((block) => renderToStaticMarkup(createElement(ReactMarkdown, null, block)))
    .join("");

  expect(rendered).toContain('<a href="https://example.com/guide">the guide</a>');
});

test("multiline reference labels remain document-wide", () => {
  const source = "See [the guide][guide docs].\n\n[guide\n docs]: https://example.com/guide";
  const rendered = splitMarkdownBlocks(source)
    .map((block) => renderToStaticMarkup(createElement(ReactMarkdown, null, block)))
    .join("");

  expect(rendered).toContain('<a href="https://example.com/guide">the guide</a>');
});
