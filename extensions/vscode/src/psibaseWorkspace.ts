import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

/** True when a folder looks like the psibase monorepo root. */
export function isPsibaseWorkspaceFolder(folderPath: string): boolean {
  const packagesCargo = path.join(folderPath, "packages", "Cargo.toml");
  const cmake = path.join(folderPath, "CMakeLists.txt");
  if (!fs.existsSync(packagesCargo) || !fs.existsSync(cmake)) {
    return false;
  }
  try {
    const text = fs.readFileSync(cmake, "utf8");
    return /\bproject\s*\(\s*psibase\b/i.test(text);
  } catch {
    return false;
  }
}

export function findPsibaseWorkspaceFolders(): vscode.WorkspaceFolder[] {
  return (vscode.workspace.workspaceFolders ?? []).filter((folder) =>
    isPsibaseWorkspaceFolder(folder.uri.fsPath),
  );
}

export function hasPsibaseWorkspace(): boolean {
  return findPsibaseWorkspaceFolders().length > 0;
}
