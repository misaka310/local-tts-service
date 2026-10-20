const { existsSync } = require("node:fs");
const path = require("node:path");

function windowsFixturePath(drive, ...segments) {
  return path.win32.join(`${drive}:`, ...segments);
}

function resolveChromeExecutable() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;

  const installRoots = [
    process.env.ProgramFiles,
    process.env["ProgramFiles(x86)"],
    process.env.LOCALAPPDATA,
  ].filter(Boolean);

  for (const root of installRoots) {
    const candidate = path.join(root, "Google", "Chrome", "Application", "chrome.exe");
    if (existsSync(candidate)) return candidate;
  }

  return undefined;
}

module.exports = { resolveChromeExecutable, windowsFixturePath };
