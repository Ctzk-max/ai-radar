// The existing Altare Node container can run the Python app without replacing its domain.
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const runtime = join(root, ".altare-runtime");
const uv = join(runtime, "bin", "uv");
const packages = join(runtime, "packages");
const requirements = join(root, "requirements.txt");
const version = "0.13.10";
const platforms = {
  x64: ["x86_64", "bf65ac1a0af10f92c522d91ac096c7c0a39657647b155577e7836c2cbbb4526c"],
  arm64: ["aarch64", "14590f644805a6234ffe071154340669e38137f38e60aa9629690119704107d2"],
};
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const env = {
  ...process.env, UV_PYTHON_INSTALL_DIR: join(runtime, "python"), UV_PYTHON_BIN_DIR: join(runtime, "bin"),
  UV_CACHE_DIR: join(runtime, "cache"), UV_LINK_MODE: "copy", UV_NO_PROGRESS: "1",
  UV_REQUEST_TIMEOUT: "45", PYTHONUNBUFFERED: "1", PYTHONPATH: packages,
};

function run(file, args, capture = false) {
  const result = spawnSync(file, args, { cwd: root, env, encoding: "utf8", stdio: capture ? "pipe" : "inherit", timeout: 180_000 });
  if (result.status !== 0) throw new Error(`Runtime step failed: ${args.slice(0, 2).join(" ")}`);
  return capture ? result.stdout.trim() : "";
}

async function prepare() {
  const architecture = platforms[process.arch];
  if (process.platform !== "linux" || !architecture) throw new Error("The Altare compatibility launcher expects Linux x64 or arm64");
  mkdirSync(join(runtime, "bin"), { recursive: true });
  if (!existsSync(uv)) {
    const [cpu, digest] = architecture;
    const name = `uv-${cpu}-unknown-linux-gnu`;
    const url = `https://github.com/astral-sh/uv/releases/download/${version}/${name}.tar.gz`;
    const response = await fetch(url, { signal: AbortSignal.timeout(45_000) });
    if (!response.ok) throw new Error(`Runtime download returned HTTP ${response.status}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (hash(bytes) !== digest) throw new Error("Runtime archive SHA256 mismatch");
    const archive = join(runtime, "uv.tar.gz");
    writeFileSync(archive, bytes);
    run("tar", ["-xzf", archive, "-C", join(runtime, "bin"), "--strip-components=1", `${name}/uv`]);
    rmSync(archive);
  }
  const installed = spawnSync(uv, ["python", "find", "--managed-python", "3.13"], { cwd: root, env, encoding: "utf8" });
  if (installed.status !== 0) run(uv, ["python", "install", "3.13"]);
  const python = run(uv, ["python", "find", "--managed-python", "3.13"], true);
  const marker = join(packages, ".requirements-sha256");
  const fingerprint = hash(readFileSync(requirements));
  if (!existsSync(marker) || readFileSync(marker, "utf8") !== fingerprint) {
    const staging = join(runtime, "packages.new");
    rmSync(staging, { recursive: true, force: true });
    run(uv, ["pip", "install", "--python", python, "--target", staging, "--only-binary", ":all:", "-r", requirements]);
    writeFileSync(join(staging, ".requirements-sha256"), fingerprint);
    rmSync(packages, { recursive: true, force: true });
    renameSync(staging, packages);
  }
  return python;
}

try {
  const python = await prepare();
  if (process.argv[2] !== "prepare") {
    const application = spawn(python, ["serve.py"], { cwd: root, env, stdio: "inherit" });
    for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => application.kill(signal));
    application.on("exit", code => { process.exitCode = code ?? 1; });
    application.on("error", () => { process.exitCode = 1; });
  }
} catch (error) {
  console.error(`AI Radar compatibility launcher: ${error.message}`);
  process.exitCode = 1;
}
