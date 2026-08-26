import { execFile } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import {
  findPsibaseWorkspaceFolders,
  hasPsibaseWorkspace,
} from "./psibaseWorkspace";
import {
  ensureManagedPython,
  managedPythonPath,
  RUNTIME_KEY,
} from "./pythonRuntime";

const execFileAsync = promisify(execFile);

export const MCP_SERVER_NAME = "psibase-mcp";
const MCP_OUTPUT_CHANNEL = "Psibase DX Tools MCP";

type CursorMcpApi = {
  registerServer: (config: {
    name: string;
    server: {
      command: string;
      args: string[];
      env: Record<string, string>;
    };
  }) => void;
  unregisterServer: (serverName: string) => void;
};

function getCursorMcp(): CursorMcpApi | undefined {
  const cursor = (
    vscode as typeof vscode & {
      cursor?: { mcp?: Partial<CursorMcpApi> };
    }
  ).cursor;
  if (
    typeof cursor?.mcp?.registerServer !== "function" ||
    typeof cursor?.mcp?.unregisterServer !== "function"
  ) {
    return undefined;
  }
  return cursor.mcp as CursorMcpApi;
}

let mcpOutputChannel: vscode.OutputChannel | undefined;

function mcpLog(message: string): void {
  mcpOutputChannel ??= vscode.window.createOutputChannel(MCP_OUTPUT_CHANNEL);
  mcpOutputChannel.appendLine(message);
}

async function notifyMcpToolsChanged(): Promise<void> {
  // Cursor listens for this after dynamic MCP registration changes.
  try {
    await vscode.commands.executeCommand("mcp.toolListChanged");
  } catch {
    // Best-effort; not all Cursor builds expose the command.
  }
}

export function resolveAiToolsPackageRoot(
  extensionPath: string,
): string | undefined {
  const bundled = path.join(extensionPath, "ai-tools");
  if (fs.existsSync(path.join(bundled, "pyproject.toml"))) {
    return bundled;
  }
  const monorepo = path.join(extensionPath, "..", "..", "ai", "tools");
  if (fs.existsSync(path.join(monorepo, "pyproject.toml"))) {
    return path.resolve(monorepo);
  }
  return undefined;
}

function venvPython(venvDir: string): string {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function installMarkerPath(globalStorage: string): string {
  return path.join(globalStorage, "ai-tools-install.json");
}

/** True when the first-run work (runtime download / venv build) is pending. */
function needsFirstRunSetup(globalStorage: string): boolean {
  return (
    !fs.existsSync(managedPythonPath(globalStorage)) ||
    !fs.existsSync(venvPython(path.join(globalStorage, "ai-tools-venv")))
  );
}

async function ensureVenv(
  context: vscode.ExtensionContext,
  packageRoot: string,
  onProgress?: (message: string) => void,
): Promise<{ python: string; stateDir: string }> {
  const globalStorage = context.globalStorageUri.fsPath;
  await fs.promises.mkdir(globalStorage, { recursive: true });

  // Self-contained pinned CPython; never touches the user's environment and
  // never depends on a python3 already being on PATH.
  const basePython = await ensureManagedPython(globalStorage, onProgress);

  const venvDir = path.join(globalStorage, "ai-tools-venv");
  const python = venvPython(venvDir);
  const markerPath = installMarkerPath(globalStorage);
  const extensionVersion = String(
    context.extension.packageJSON.version ?? "0.0.0",
  );

  let needsInstall = !fs.existsSync(python);
  if (!needsInstall && fs.existsSync(markerPath)) {
    try {
      const marker = JSON.parse(
        await fs.promises.readFile(markerPath, "utf8"),
      ) as {
        extensionVersion?: string;
        packageRoot?: string;
        runtime?: string;
      };
      if (
        marker.extensionVersion !== extensionVersion ||
        marker.packageRoot !== packageRoot ||
        marker.runtime !== RUNTIME_KEY
      ) {
        needsInstall = true;
      }
    } catch {
      needsInstall = true;
    }
  } else if (!fs.existsSync(markerPath)) {
    needsInstall = true;
  }

  if (needsInstall) {
    onProgress?.("Installing psibase ai-tools...");
    // Rebuild from scratch: the venv hard-links to the base interpreter's
    // install path, so a runtime bump silently breaks an existing venv.
    await fs.promises.rm(venvDir, { recursive: true, force: true });
    await execFileAsync(basePython, ["-m", "venv", venvDir]);
    await execFileAsync(python, ["-m", "pip", "install", packageRoot]);
    await fs.promises.writeFile(
      markerPath,
      JSON.stringify(
        {
          extensionVersion,
          packageRoot,
          runtime: RUNTIME_KEY,
          installedAt: new Date().toISOString(),
        },
        null,
        2,
      ),
      "utf8",
    );
  }

  const workspaceStorage = context.storageUri?.fsPath;
  const stateDir = workspaceStorage
    ? path.join(workspaceStorage, "ai-tools-state")
    : path.join(globalStorage, "ai-tools-state");
  await fs.promises.mkdir(stateDir, { recursive: true });

  return { python, stateDir };
}

/** Unregister the dynamic MCP server from Cursor (safe to call multiple times). */
export function unregisterMcpServer(): void {
  const mcp = getCursorMcp();
  if (!mcp) return;
  try {
    // Always attempt unregister so extension upgrades replace a prior session registration.
    mcp.unregisterServer(MCP_SERVER_NAME);
  } catch {
    // Best-effort; Cursor may not have this server registered.
  }
}

export function registerMcpServer(context: vscode.ExtensionContext): () => void {
  let disposed = false;
  let syncGeneration = 0;

  const unregister = () => {
    unregisterMcpServer();
    if (mcpOutputChannel) {
      mcpOutputChannel.dispose();
      mcpOutputChannel = undefined;
    }
  };

  const dispose = () => {
    if (disposed) return;
    disposed = true;
    syncGeneration += 1;
    unregister();
  };

  const sync = async () => {
    if (disposed) return;
    const generation = syncGeneration;

    const mcp = getCursorMcp();
    if (!mcp) {
      mcpLog(
        "Cursor MCP API unavailable; psibase-mcp was not registered. Use a Cursor build that supports vscode.cursor.mcp.",
      );
      return;
    }

    if (!hasPsibaseWorkspace()) {
      unregister();
      return;
    }

    const packageRoot = resolveAiToolsPackageRoot(context.extensionPath);
    if (!packageRoot) {
      if (!disposed) {
        void vscode.window.showWarningMessage(
          "Psibase DX Tools: bundled ai-tools package not found. Run npm run compile in the extension (syncs ai/tools).",
        );
      }
      unregister();
      return;
    }

    try {
      const globalStorage = context.globalStorageUri.fsPath;
      const setup = needsFirstRunSetup(globalStorage)
        ? vscode.window.withProgress(
            {
              location: vscode.ProgressLocation.Notification,
              title: "Psibase DX Tools: setting up Python environment",
            },
            (progress) =>
              ensureVenv(context, packageRoot, (message) =>
                progress.report({ message }),
              ),
          )
        : ensureVenv(context, packageRoot);
      const { python, stateDir } = await setup;
      if (disposed || generation !== syncGeneration) return;

      const workspaceRoots = findPsibaseWorkspaceFolders().map(
        (folder) => folder.uri.fsPath,
      );
      // Re-register so extension upgrades replace prior command/env.
      unregister();
      if (disposed || generation !== syncGeneration) return;

      mcp.registerServer({
        name: MCP_SERVER_NAME,
        server: {
          command: python,
          args: ["-m", "psibase_ai_tools.mcp"],
          env: {
            AI_TOOLS_STATE_DIR: stateDir,
            // Binds this window's server to its psibase folder(s); the Python
            // side (detect_workspace_root) reads this ahead of WORKSPACE_ROOT
            // and CWD, so parallel worktrees / windows stay isolated.
            MCP_WORKSPACE_ROOTS: JSON.stringify(workspaceRoots),
            // Bust Cursor's MCP config cache so a window reload reconnects and
            // re-runs tools/list instead of reusing a stale "connected" session
            // with zero tools registered (seen after extension host restarts).
            PSIBASE_MCP_REGISTRATION_EPOCH: String(Date.now()),
          },
        },
      });
      mcpLog(
        `Registered ${MCP_SERVER_NAME} (${python}) for workspace roots: ${workspaceRoots.join(", ")}`,
      );
      await notifyMcpToolsChanged();
    } catch (err) {
      if (disposed) return;
      const message = err instanceof Error ? err.message : String(err);
      void vscode.window.showErrorMessage(
        `Psibase DX Tools: failed to prepare MCP server: ${message}`,
      );
      unregister();
    }
  };

  void sync();

  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      void sync();
    }),
    { dispose },
  );

  return dispose;
}
