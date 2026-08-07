import * as path from "path";
import * as vscode from "vscode";
import { hasPsibaseWorkspace } from "./psibaseWorkspace";

type CursorPluginsApi = {
  registerPath: (pluginPath: string) => void;
  unregisterPath: (pluginPath: string) => void;
};

/** Optional contributor/dev rules (settings toggles). */
const TOGGLEABLE_RULES = [
  {
    id: "no-backward-compatibility",
    setting: "psibasePackage.aiRules.contributors.noBackwardCompatibility",
  },
  {
    id: "no-writable-git",
    setting: "psibasePackage.aiRules.contributors.noWritableGit",
  },
  {
    id: "package-backend-shared-types",
    setting: "psibasePackage.aiRules.contributors.packageBackendSharedTypes",
  },
  {
    id: "service-action-failures",
    setting: "psibasePackage.aiRules.devs.serviceActionFailures",
  },
] as const;

/** Always registered in a psibase workspace (no settings toggle). */
const ALWAYS_ON_RULES = ["prefer-mcp-tools"] as const;

function getCursorPlugins(): CursorPluginsApi | undefined {
  const cursor = (
    vscode as typeof vscode & {
      cursor?: { plugins?: Partial<CursorPluginsApi> };
    }
  ).cursor;
  if (
    typeof cursor?.plugins?.registerPath !== "function" ||
    typeof cursor?.plugins?.unregisterPath !== "function"
  ) {
    return undefined;
  }
  return cursor.plugins as CursorPluginsApi;
}

function pluginDir(extensionPath: string, id: string): string {
  return path.join(extensionPath, "cursor-plugins", id);
}

export function registerAiRules(context: vscode.ExtensionContext): void {
  const registered = new Set<string>();

  const clearAll = () => {
    const plugins = getCursorPlugins();
    if (!plugins) return;
    for (const dir of registered) {
      plugins.unregisterPath(dir);
    }
    registered.clear();
  };

  const ensureRegistered = (plugins: CursorPluginsApi, dir: string) => {
    if (!registered.has(dir)) {
      plugins.registerPath(dir);
      registered.add(dir);
    }
  };

  const ensureUnregistered = (plugins: CursorPluginsApi, dir: string) => {
    if (registered.has(dir)) {
      plugins.unregisterPath(dir);
      registered.delete(dir);
    }
  };

  const sync = () => {
    const plugins = getCursorPlugins();
    if (!plugins) return;

    if (!hasPsibaseWorkspace()) {
      clearAll();
      return;
    }

    for (const id of ALWAYS_ON_RULES) {
      ensureRegistered(plugins, pluginDir(context.extensionPath, id));
    }

    const config = vscode.workspace.getConfiguration();
    for (const rule of TOGGLEABLE_RULES) {
      const dir = pluginDir(context.extensionPath, rule.id);
      if (config.get<boolean>(rule.setting, true)) {
        ensureRegistered(plugins, dir);
      } else {
        ensureUnregistered(plugins, dir);
      }
    }
  };

  sync();

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("psibasePackage.aiRules")) {
        sync();
      }
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      sync();
    }),
    { dispose: clearAll },
  );
}
