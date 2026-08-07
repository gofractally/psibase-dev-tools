import * as path from "path";
import * as vscode from "vscode";

type CursorPluginsApi = {
  registerPath: (pluginPath: string) => void;
  unregisterPath: (pluginPath: string) => void;
};

const RULES = [
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

  const sync = () => {
    const plugins = getCursorPlugins();
    if (!plugins) return;

    const config = vscode.workspace.getConfiguration();
    for (const rule of RULES) {
      const dir = pluginDir(context.extensionPath, rule.id);
      const enabled = config.get<boolean>(rule.setting, true);
      if (enabled) {
        if (!registered.has(dir)) {
          plugins.registerPath(dir);
          registered.add(dir);
        }
      } else if (registered.has(dir)) {
        plugins.unregisterPath(dir);
        registered.delete(dir);
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
    {
      dispose: () => {
        const plugins = getCursorPlugins();
        if (!plugins) return;
        for (const dir of registered) {
          plugins.unregisterPath(dir);
        }
        registered.clear();
      },
    },
  );
}
