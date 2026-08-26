import * as vscode from "vscode";
import { registerAiRules } from "./aiRules";
import { collectContentOverrides, isPackageRelevantDocument } from "./buffers";
import { PackageGraphService } from "./graph";
import { registerMcpServer } from "./mcpServer";
import { findPsibaseWorkspaceFolders } from "./psibaseWorkspace";
import {
  findCorrelated,
  registerCodeActions,
  registerDiagnostics,
  registerHover,
  registerInlayHints,
  registerRenameProvider,
  registerSemanticTokens,
  registerStatusBar,
  renameEntity,
} from "./providers";

const EXTENSION_ID = "psibase.psibase";

let disposeExtensionServices: (() => void) | undefined;

function disposeAllExtensionServices(): void {
  if (!disposeExtensionServices) return;
  disposeExtensionServices();
  disposeExtensionServices = undefined;
}

function watchForExtensionRemoval(): void {
  // Cursor can remove an extension from the profile without deactivating the
  // extension host first; unregister MCP/plugins when our id disappears.
  const disposable = vscode.extensions.onDidChange(() => {
    if (!vscode.extensions.getExtension(EXTENSION_ID)) {
      disposeAllExtensionServices();
      disposable.dispose();
    }
  });
}

export function activate(context: vscode.ExtensionContext): void {
  const disposeAiRules = registerAiRules(context);
  const disposeMcp = registerMcpServer(context);
  disposeExtensionServices = () => {
    disposeMcp();
    disposeAiRules();
  };
  watchForExtensionRemoval();

  const graphs = new PackageGraphService();

  const refreshAll = () => {
    for (const folder of findPsibaseWorkspaceFolders()) {
      graphs.refresh(folder.uri.fsPath, collectContentOverrides());
    }
  };

  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  const scheduleRefresh = () => {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => refreshAll(), 150);
  };

  refreshAll();

  registerDiagnostics(context, graphs);
  registerHover(context, graphs);
  registerInlayHints(context, graphs);
  registerCodeActions(context, graphs);
  registerSemanticTokens(context, graphs);
  registerRenameProvider(context, graphs);
  registerStatusBar(context, graphs);

  context.subscriptions.push(
    vscode.commands.registerCommand("psibasePackage.renameEntity", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      await renameEntity(graphs, editor, refreshAll);
    }),
    vscode.commands.registerCommand(
      "psibasePackage.findCorrelated",
      async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;
        await findCorrelated(graphs, editor);
      },
    ),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (isPackageRelevantDocument(event.document)) {
        scheduleRefresh();
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      if (isPackageRelevantDocument(doc)) {
        scheduleRefresh();
      }
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (isPackageRelevantDocument(doc)) {
        refreshAll();
      }
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => refreshAll()),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("psibasePackage")) {
        refreshAll();
      }
    }),
    {
      dispose: () => {
        if (refreshTimer) clearTimeout(refreshTimer);
      },
    },
  );
}

export function deactivate(): void {
  disposeAllExtensionServices();
}
