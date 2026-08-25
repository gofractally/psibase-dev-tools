import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  findPsibaseWorkspaceFolders,
  hasPsibaseWorkspace,
} from "./psibaseWorkspace";

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

let warnedAboutLegacyRules = false;

/**
 * Earlier installers copied these rules into `<workspace>/.cursor/rules/`.
 * Now that the extension registers them itself, a workspace copy means every
 * rule is injected twice (and the stale copy wins on upgrades). Delete copies
 * that are byte-identical to the bundled rule; warn once about divergent
 * copies rather than destroying a user's customization.
 */
async function cleanupLegacyWorkspaceRules(
  extensionPath: string,
): Promise<void> {
  const ruleIds = [
    ...ALWAYS_ON_RULES,
    ...TOGGLEABLE_RULES.map((rule) => rule.id),
  ];
  const divergent: string[] = [];

  for (const folder of findPsibaseWorkspaceFolders()) {
    for (const id of ruleIds) {
      const workspaceCopy = path.join(
        folder.uri.fsPath,
        ".cursor",
        "rules",
        `${id}.mdc`,
      );
      let copyText: string;
      try {
        copyText = await fs.promises.readFile(workspaceCopy, "utf8");
      } catch {
        continue; // no leftover for this rule
      }

      let bundledText: string | undefined;
      try {
        bundledText = await fs.promises.readFile(
          path.join(pluginDir(extensionPath, id), "rules", `${id}.mdc`),
          "utf8",
        );
      } catch {
        // bundled rule missing; treat the copy as divergent
      }

      if (bundledText !== undefined && copyText === bundledText) {
        try {
          await fs.promises.unlink(workspaceCopy);
        } catch {
          divergent.push(workspaceCopy);
        }
      } else {
        divergent.push(workspaceCopy);
      }
    }
  }

  if (divergent.length > 0 && !warnedAboutLegacyRules) {
    warnedAboutLegacyRules = true;
    void vscode.window.showWarningMessage(
      "Psibase DX Tools: found workspace copies of rules this extension now provides. " +
        "They will duplicate (and may shadow) the extension's rules — please remove or merge: " +
        divergent.join(", "),
    );
  }
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

    void cleanupLegacyWorkspaceRules(context.extensionPath);

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
