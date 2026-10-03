import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { existsSync } from "node:fs";
import * as fs from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { execSync } from "node:child_process";
import * as childProcess from "node:child_process";
import { buildWithZig, SetupError } from "./zig.js";

vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:fs")>();
  return { ...actual, existsSync: vi.fn(actual.existsSync) };
});

vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return { ...actual, execFileSync: vi.fn(actual.execFileSync) };
});

const HEARTH_DIR = join(homedir(), ".hearth");

describe("source builds", () => {
  beforeEach(() => {
    vi.mocked(fs.existsSync).mockReturnValue(true);
    vi.mocked(childProcess.execFileSync).mockReturnValue("0.17.0\n");
  });

  afterEach(() => {
    vi.mocked(fs.existsSync).mockReset();
    vi.mocked(childProcess.execFileSync).mockReset();
  });

  it.each(["vmm", "agent"])("checks the pinned compiler before building %s in safe mode", (sourceDir) => {
    buildWithZig(sourceDir);

    expect(childProcess.execFileSync).toHaveBeenNthCalledWith(
      1, "zig", ["version"], { encoding: "utf8", stdio: "pipe" },
    );
    expect(childProcess.execFileSync).toHaveBeenNthCalledWith(
      2, "zig", ["build", "-Doptimize=safe"], { cwd: sourceDir, stdio: "pipe" },
    );
  });

  it.each(["0.16.0", "0.17.0-dev.1+abcdef", "0.18.0", ""])("rejects incompatible compiler output %j", (version) => {
    vi.mocked(childProcess.execFileSync).mockReturnValue(`${version}\n`);

    expect(() => buildWithZig("agent")).toThrow(
      `Source builds require Zig 0.17.0; found ${JSON.stringify(version)}`,
    );
    expect(childProcess.execFileSync).toHaveBeenCalledTimes(1);
  });

  it("reports a missing compiler with installation instructions", () => {
    const cause = Object.assign(new Error("spawnSync zig ENOENT"), { code: "ENOENT" });
    vi.mocked(childProcess.execFileSync).mockImplementation(() => { throw cause; });

    expect(() => buildWithZig("vmm")).toThrow(SetupError);
    expect(() => buildWithZig("vmm")).toThrow("Zig not found on PATH. Source builds require Zig 0.17.0.");
  });

  it("preserves a failed version probe rather than calling it a missing compiler", () => {
    const cause = new Error("zig version exited with status 1");
    vi.mocked(childProcess.execFileSync).mockImplementation(() => { throw cause; });

    try {
      buildWithZig("agent");
      expect.fail("Expected the compiler check to fail");
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(SetupError);
      expect(err).toHaveProperty("cause", cause);
      expect(err).toHaveProperty("message", "Could not check Zig version: zig version exited with status 1");
    }
    expect(childProcess.execFileSync).toHaveBeenCalledTimes(1);
  });

  it("reports missing source modules before running Zig", () => {
    vi.mocked(fs.existsSync).mockReturnValue(false);

    expect(() => buildWithZig("agent")).toThrow("Missing Zig source module at agent (build.zig not found)");
    expect(childProcess.execFileSync).not.toHaveBeenCalled();
  });

  it("retains compiler diagnostics when a source build fails", () => {
    const cause = Object.assign(new Error("build failed"), {
      stderr: Buffer.from("error: missing translated libc dependency\n"),
    });
    vi.mocked(childProcess.execFileSync).mockImplementationOnce(() => "0.17.0\n")
      .mockImplementationOnce(() => { throw cause; });

    try {
      buildWithZig("agent");
      expect.fail("Expected the source build to fail");
    } catch (err: unknown) {
      expect(err).toBeInstanceOf(SetupError);
      expect(err).toHaveProperty("cause", cause);
      expect(err).toHaveProperty(
        "message", "Zig source build failed in agent: error: missing translated libc dependency",
      );
    }
  });
});

describe("hearth setup", () => {
  it("should have installed flint", () => {
    const flintPath = join(HEARTH_DIR, "bin", "flint");
    expect(existsSync(flintPath)).toBe(true);
  });

  it("should have installed the kernel", () => {
    const hasBzImage = existsSync(join(HEARTH_DIR, "bases", "bzImage"));
    const hasVmlinux = existsSync(join(HEARTH_DIR, "bases", "vmlinux"));
    expect(hasBzImage || hasVmlinux).toBe(true);
  });

  it("should have built the rootfs", () => {
    expect(existsSync(join(HEARTH_DIR, "bases", "ubuntu-24.04.ext4"))).toBe(true);
  });

  it("should have built the hearth-agent", () => {
    expect(existsSync(join(HEARTH_DIR, "bin", "hearth-agent"))).toBe(true);
  });

  it("should have created the base snapshot", () => {
    expect(existsSync(join(HEARTH_DIR, "snapshots", "base", "vmstate.snap"))).toBe(true);
    expect(existsSync(join(HEARTH_DIR, "snapshots", "base", "memory.snap"))).toBe(true);
    expect(existsSync(join(HEARTH_DIR, "snapshots", "base", "rootfs.ext4"))).toBe(true);
  });

  it("should be idempotent", () => {
    // Running setup again should succeed and not redownload
    const output = execSync("node dist/cli/hearth.js setup", {
      stdio: "pipe",
      timeout: 10000,
    }).toString();

    expect(output).toContain("already installed");
    expect(output).toContain("already built");
    expect(output).toContain("already created");
  });
});
