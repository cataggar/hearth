import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { HearthError, isNodeError } from "../errors.js";
import { errorMessage } from "../util.js";

export class SetupError extends HearthError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "SetupError";
  }
}

export function buildWithZig(sourceDir: string): void {
  if (!existsSync(join(sourceDir, "build.zig"))) {
    throw new SetupError(
      `Missing Zig source module at ${sourceDir} (build.zig not found). Run setup from the hearth repo root.`,
    );
  }

  let version: string;
  try {
    version = execFileSync("zig", ["version"], { encoding: "utf8", stdio: "pipe" }).trim();
  } catch (err: unknown) {
    if (isNodeError(err) && err.code === "ENOENT") {
      throw new SetupError(
        "Zig not found on PATH. Source builds require Zig 0.17.0. Install it from https://github.com/cataggar/zig/releases/tag/v0.17.0.",
        { cause: err },
      );
    }
    throw new SetupError(`Could not check Zig version: ${errorMessage(err)}`, { cause: err });
  }
  if (version !== "0.17.0") {
    throw new SetupError(
      `Source builds require Zig 0.17.0; found ${JSON.stringify(version)}. Install the pinned compiler from https://github.com/cataggar/zig/releases/tag/v0.17.0 and check your PATH.`,
    );
  }

  try {
    execFileSync("zig", ["build", "-Doptimize=safe"], { cwd: sourceDir, stdio: "pipe" });
  } catch (err: unknown) {
    const stderr = err && typeof err === "object" && "stderr" in err ? err.stderr : undefined;
    const detail = Buffer.isBuffer(stderr)
      ? stderr.toString().trim()
      : typeof stderr === "string" ? stderr.trim() : errorMessage(err);
    throw new SetupError(`Zig source build failed in ${sourceDir}: ${detail || errorMessage(err)}`, { cause: err });
  }
}
