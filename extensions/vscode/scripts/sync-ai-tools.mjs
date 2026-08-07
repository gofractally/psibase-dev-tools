import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoAiTools = join(extensionRoot, "..", "..", "ai", "tools");
const dest = join(extensionRoot, "ai-tools");

if (!existsSync(join(repoAiTools, "pyproject.toml"))) {
  console.error(`sync-ai-tools: missing package at ${repoAiTools}`);
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
cpSync(repoAiTools, dest, {
  recursive: true,
  filter: (src) => {
    const base = src.split(/[/\\]/).pop() ?? "";
    if (
      base === ".venv" ||
      base === "__pycache__" ||
      base === ".pytest_cache" ||
      base === "build" ||
      base === ".eggs" ||
      base.endsWith(".egg-info")
    ) {
      return false;
    }
    if (base.endsWith(".pyc")) return false;
    return true;
  },
});

console.log(`sync-ai-tools: copied ${repoAiTools} -> ${dest}`);
