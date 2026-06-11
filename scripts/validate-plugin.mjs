#!/usr/bin/env node
/**
 * Validate single-plugin Cursor marketplace structure.
 * Adapted from cursor/plugin-template validate-template.mjs (single-plugin mode).
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const pluginDir = repoRoot;
const errors = [];
const warnings = [];

const pluginNamePattern = /^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/;

function addError(message) {
  errors.push(message);
}

function addWarning(message) {
  warnings.push(message);
}

async function pathExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function readJsonFile(filePath, context) {
  let raw;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch {
    addError(`${context} is missing: ${filePath}`);
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    addError(`${context} contains invalid JSON (${filePath}): ${error.message}`);
    return null;
  }
}

function normalizeNewlines(content) {
  return content.replace(/\r\n/g, "\n");
}

function parseFrontmatter(content) {
  const normalized = normalizeNewlines(content);
  if (!normalized.startsWith("---\n")) {
    return null;
  }
  const closingIndex = normalized.indexOf("\n---\n", 4);
  if (closingIndex === -1) {
    return null;
  }
  const frontmatterBlock = normalized.slice(4, closingIndex);
  const fields = {};
  for (const line of frontmatterBlock.split("\n")) {
    const separator = line.indexOf(":");
    if (separator === -1) {
      continue;
    }
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    fields[key] = value;
  }
  return fields;
}

async function walkFiles(dirPath) {
  const files = [];
  const stack = [dirPath];
  while (stack.length > 0) {
    const current = stack.pop();
    const entries = await fs.readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(entryPath);
      } else if (entry.isFile()) {
        files.push(entryPath);
      }
    }
  }
  return files;
}

function isSafeRelativePath(value) {
  if (typeof value !== "string" || value.length === 0) {
    return false;
  }
  if (value.startsWith("http://") || value.startsWith("https://")) {
    return true;
  }
  if (path.isAbsolute(value)) {
    return false;
  }
  const normalized = path.posix.normalize(value.replace(/\\/g, "/"));
  return !normalized.startsWith("../") && normalized !== "..";
}

function extractPathValues(value) {
  if (typeof value === "string") {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.flatMap((entry) => extractPathValues(entry));
  }
  if (value && typeof value === "object") {
    const candidates = [];
    if (typeof value.path === "string") {
      candidates.push(value.path);
    }
    if (typeof value.file === "string") {
      candidates.push(value.file);
    }
    return candidates;
  }
  return [];
}

async function validateReferencedPath(fieldName, pathValue, pluginName) {
  if (pathValue.startsWith("http://") || pathValue.startsWith("https://")) {
    return;
  }
  if (!isSafeRelativePath(pathValue)) {
    addError(
      `${pluginName}: field "${fieldName}" has invalid path "${pathValue}". Use a relative path without ".." or absolute prefixes.`
    );
    return;
  }
  const resolved = path.resolve(pluginDir, pathValue);
  if (!(await pathExists(resolved))) {
    addError(`${pluginName}: field "${fieldName}" references missing path "${pathValue}".`);
  }
}

async function validateFrontmatterFile(filePath, componentName, requiredKeys, pluginName) {
  const content = await fs.readFile(filePath, "utf8");
  const parsed = parseFrontmatter(content);
  const relativeFile = path.relative(repoRoot, filePath);
  if (!parsed) {
    addError(`${pluginName}: ${componentName} file missing YAML frontmatter: ${relativeFile}`);
    return;
  }
  for (const key of requiredKeys) {
    if (!parsed[key] || parsed[key].length === 0) {
      addError(`${pluginName}: ${componentName} file missing "${key}" in frontmatter: ${relativeFile}`);
    }
  }
}

async function validateHookCommands(hooksJson, pluginName) {
  const hooks = hooksJson?.hooks;
  if (!hooks || typeof hooks !== "object") {
    addError(`${pluginName}: hooks/hooks.json must contain a "hooks" object.`);
    return;
  }
  for (const [eventName, entries] of Object.entries(hooks)) {
    if (!Array.isArray(entries)) {
      addError(`${pluginName}: hooks.${eventName} must be an array.`);
      continue;
    }
    for (const entry of entries) {
      if (!entry || typeof entry !== "object" || typeof entry.command !== "string") {
        addError(`${pluginName}: hooks.${eventName} entry must have a "command" string.`);
        continue;
      }
      const command = entry.command.trim();
      const scriptMatch = command.match(/(?:\.\/)?([\w./-]+\.(?:sh|py|mjs|ts|js))\b/);
      if (!scriptMatch) {
        continue;
      }
      let scriptPath = scriptMatch[1].replace(/^\.\//, "");
      if (scriptPath.includes("${CURSOR_PLUGIN_ROOT}")) {
        continue;
      }
      const resolved = path.resolve(pluginDir, scriptPath);
      if (!(await pathExists(resolved))) {
        addError(`${pluginName}: hooks.${eventName} command references missing script "${scriptPath}".`);
      }
    }
  }
}

async function main() {
  const marketplacePath = path.join(repoRoot, ".cursor-plugin", "marketplace.json");
  if (await pathExists(marketplacePath)) {
    addWarning(
      "Found marketplace.json — this validator targets single-plugin repos. Use cursor/plugin-template validate-template.mjs for multi-plugin."
    );
  }

  const manifestPath = path.join(pluginDir, ".cursor-plugin", "plugin.json");
  const manifest = await readJsonFile(manifestPath, "Plugin manifest");
  if (!manifest) {
    summarizeAndExit();
    return;
  }

  const pluginName = manifest.name ?? "agent-memory";

  if (typeof manifest.name !== "string" || !pluginNamePattern.test(manifest.name)) {
    addError(
      'Plugin "name" must be lowercase kebab-case and start/end with an alphanumeric character.'
    );
  }

  if (!manifest.description || typeof manifest.description !== "string") {
    addWarning(`${pluginName}: "description" is recommended for marketplace review.`);
  }

  if (!manifest.version || typeof manifest.version !== "string") {
    addWarning(`${pluginName}: "version" is recommended for marketplace review.`);
  }

  if (!manifest.displayName || typeof manifest.displayName !== "string") {
    addWarning(`${pluginName}: "displayName" is recommended for marketplace review.`);
  }

  const manifestFields = ["logo", "rules", "skills", "agents", "commands", "hooks", "mcpServers"];
  for (const field of manifestFields) {
    const values = extractPathValues(manifest[field]);
    for (const value of values) {
      await validateReferencedPath(field, value, pluginName);
    }
  }

  const skillsDir = path.join(pluginDir, "skills");
  if (await pathExists(skillsDir)) {
    const files = await walkFiles(skillsDir);
    let skillCount = 0;
    for (const file of files) {
      if (path.basename(file) === "SKILL.md") {
        skillCount += 1;
        await validateFrontmatterFile(file, "skill", ["name", "description"], pluginName);
      }
    }
    if (skillCount === 0) {
      addError(`${pluginName}: skills/ must contain at least one SKILL.md file.`);
    }
  } else {
    addError(`${pluginName}: skills/ directory is missing.`);
  }

  const hooksPath = path.join(pluginDir, "hooks", "hooks.json");
  const hooksJson = await readJsonFile(hooksPath, "Hooks config");
  if (hooksJson) {
    await validateHookCommands(hooksJson, pluginName);
  }

  if (!(await pathExists(path.join(pluginDir, "README.md")))) {
    addWarning(`${pluginName}: README.md is recommended for marketplace review.`);
  }

  if (!(await pathExists(path.join(pluginDir, "LICENSE")))) {
    addWarning(`${pluginName}: LICENSE is recommended for marketplace review.`);
  }

  summarizeAndExit();
}

function summarizeAndExit() {
  if (warnings.length > 0) {
    console.log("Warnings:");
    for (const warning of warnings) {
      console.log(`- ${warning}`);
    }
    console.log("");
  }

  if (errors.length > 0) {
    console.error("Plugin validation failed:");
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  console.log("Plugin validation passed.");
}

await main();
