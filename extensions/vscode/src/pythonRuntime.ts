/**
 * Self-contained Python runtime management.
 *
 * Downloads a pinned python-build-standalone CPython into the extension's
 * global storage on first use, so users need no Python (or any other tooling
 * besides `tar`) on their machine and we always run a known interpreter
 * version. Nothing is installed outside the extension's own storage.
 *
 * This module deliberately does not import `vscode` so it can be exercised
 * by plain Node test scripts; callers pass a progress callback for UI.
 */

import { execFile } from "child_process";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

// Pinned runtime. Bump these together (and refresh checksums from the
// release's SHA256SUMS file) to move to a new interpreter.
const RELEASE_TAG = "20260814";
const PYTHON_VERSION = "3.12.14";

/** Identifies the runtime layout on disk; changing it invalidates old runtimes. */
export const RUNTIME_KEY = `cpython-${PYTHON_VERSION}+${RELEASE_TAG}`;

type RuntimeTarget = {
  triple: string;
  sha256: string;
};

// SHA256SUMS from https://github.com/astral-sh/python-build-standalone/releases/tag/20260814
const TARGETS: Record<string, RuntimeTarget> = {
  "linux-x64": {
    triple: "x86_64-unknown-linux-gnu",
    sha256: "5acfa3e9ba26b51ae161c83aff278da915b590d22373a424b2ba55b8afe91fcc",
  },
  "linux-arm64": {
    triple: "aarch64-unknown-linux-gnu",
    sha256: "2d8e17dfd732102cfeb18e0e1fa6769b24caa034e159981129590fe409c7157a",
  },
  "darwin-x64": {
    triple: "x86_64-apple-darwin",
    sha256: "aec265e3cddaccdb2a3d783331596351b24d4a63c97af0a38f75f643c9451de9",
  },
  "darwin-arm64": {
    triple: "aarch64-apple-darwin",
    sha256: "dd5b76ab11451a4a4367c17c61d944dded56b425396b07f102922a7ebef7d55f",
  },
  "win32-x64": {
    triple: "x86_64-pc-windows-msvc",
    sha256: "89f18f6932917163b74339ebcec2645c8e47ae7f1c5f2ac37f2b4f4cf3beb647",
  },
  "win32-arm64": {
    triple: "aarch64-pc-windows-msvc",
    sha256: "1e1de8b5d0df73b965aa72f0c27d5c617a5d7256ce6d205228a0f9638bf6df21",
  },
};

function currentTarget(): RuntimeTarget {
  const key = `${process.platform}-${process.arch}`;
  const target = TARGETS[key];
  if (!target) {
    throw new Error(
      `Unsupported platform for the bundled Python runtime: ${key}. ` +
        "Supported: " +
        Object.keys(TARGETS).join(", "),
    );
  }
  return target;
}

function runtimeRoot(globalStorageDir: string): string {
  return path.join(globalStorageDir, "python-runtime");
}

function runtimeDir(globalStorageDir: string): string {
  return path.join(runtimeRoot(globalStorageDir), RUNTIME_KEY);
}

/** Path the managed interpreter will have once installed (may not exist yet). */
export function managedPythonPath(globalStorageDir: string): string {
  const base = path.join(runtimeDir(globalStorageDir), "python");
  return process.platform === "win32"
    ? path.join(base, "python.exe")
    : path.join(base, "bin", "python3");
}

function assetName(target: RuntimeTarget): string {
  return `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-${target.triple}-install_only_stripped.tar.gz`;
}

function assetUrl(target: RuntimeTarget): string {
  return `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/${assetName(target)}`;
}

async function download(url: string, dest: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed (HTTP ${response.status}): ${url}`);
  }
  const data = Buffer.from(await response.arrayBuffer());
  await fs.promises.writeFile(dest, data);
}

function sha256Of(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    fs.createReadStream(filePath)
      .on("error", reject)
      .on("data", (chunk) => hash.update(chunk))
      .on("end", () => resolve(hash.digest("hex")));
  });
}

/** Best-effort removal of runtimes from older pins. */
async function pruneStaleRuntimes(globalStorageDir: string): Promise<void> {
  const root = runtimeRoot(globalStorageDir);
  let entries: string[];
  try {
    entries = await fs.promises.readdir(root);
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry !== RUNTIME_KEY) {
      await fs.promises
        .rm(path.join(root, entry), { recursive: true, force: true })
        .catch(() => undefined);
    }
  }
}

/**
 * Ensure the pinned CPython is installed under global storage and return the
 * interpreter path. Downloads ~30 MB on first run; afterwards this is just a
 * stat call.
 */
export async function ensureManagedPython(
  globalStorageDir: string,
  onProgress?: (message: string) => void,
): Promise<string> {
  const python = managedPythonPath(globalStorageDir);
  if (fs.existsSync(python)) {
    return python;
  }

  const target = currentTarget();
  const destDir = runtimeDir(globalStorageDir);
  const archivePath = path.join(
    runtimeRoot(globalStorageDir),
    `${assetName(target)}.partial`,
  );

  await fs.promises.mkdir(runtimeRoot(globalStorageDir), { recursive: true });
  await pruneStaleRuntimes(globalStorageDir);

  try {
    onProgress?.(`Downloading Python ${PYTHON_VERSION} (~30 MB)...`);
    await download(assetUrl(target), archivePath);

    onProgress?.("Verifying checksum...");
    const digest = await sha256Of(archivePath);
    if (digest !== target.sha256) {
      throw new Error(
        `Checksum mismatch for ${assetName(target)}: expected ${target.sha256}, got ${digest}. ` +
          "The download may be corrupted; try again.",
      );
    }

    onProgress?.("Extracting...");
    // Extract into a staging dir, then rename into place so a half-extracted
    // tree is never mistaken for a working runtime.
    const stagingDir = `${destDir}.staging`;
    await fs.promises.rm(stagingDir, { recursive: true, force: true });
    await fs.promises.mkdir(stagingDir, { recursive: true });
    try {
      // The archive contains a single top-level `python/` directory. `tar` is
      // present on Linux, macOS, and Windows 10+ (bsdtar).
      await execFileAsync("tar", ["-xzf", archivePath, "-C", stagingDir]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Failed to extract the Python runtime (is 'tar' available?): ${message}`,
      );
    }
    await fs.promises.rm(destDir, { recursive: true, force: true });
    await fs.promises.rename(stagingDir, destDir);
  } finally {
    await fs.promises.rm(archivePath, { force: true }).catch(() => undefined);
  }

  if (!fs.existsSync(python)) {
    throw new Error(
      `Python runtime extraction did not produce the expected interpreter at ${python}`,
    );
  }
  return python;
}
