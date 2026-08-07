declare module "vscode" {
  export namespace cursor {
    export namespace plugins {
      export const registerPath: (path: string) => void;
      export const unregisterPath: (path: string) => void;
    }
  }
}

export {};
