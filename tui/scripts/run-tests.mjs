import { readdir } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import process from "node:process";

async function collectTests(root) {
  const files = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const target = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectTests(target));
    } else if (/\.test\.tsx?$/.test(entry.name)) {
      files.push(target);
    }
  }
  return files;
}

// Node 20's test runner does not expand the recursive glob strings that were
// previously passed by package.json. Discover files ourselves so local and CI
// runs execute the same suite on every supported platform.
const files = [
  ...await collectTests("src"),
  ...await collectTests("tests")
].sort();

if (files.length === 0) {
  console.error("No TUI test files were discovered.");
  process.exit(1);
}

const result = spawnSync(
  process.execPath,
  ["--import", "tsx", "--test", ...files],
  {
    stdio: "inherit",
    // Ink intentionally suppresses dynamic frames when CI=true and debug=false,
    // but the physical stdout contract exercises the interactive terminal path.
    // Normalize only the test child so local and hosted runners cover that same path.
    env: { ...process.env, CI: "false" }
  }
);

if (result.error) {
  console.error(`Could not start the TUI test runner: ${result.error.message}`);
}
process.exit(result.status ?? 1);
