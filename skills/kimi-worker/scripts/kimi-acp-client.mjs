#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { writeFileSync } from "node:fs";

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

const options = {
  cwd: process.cwd(),
  model: "kimi-code/k3-256k",
  effort: "high",
  outputFormat: "text",
  addDirs: [],
  sessionIdFile: undefined,
  resumeSession: undefined,
  continueMode: false,
  prompt: undefined,
};

const args = process.argv.slice(2);
for (let index = 0; index < args.length; index += 1) {
  const arg = args[index];
  const value = () => {
    index += 1;
    if (index >= args.length) fail(`Missing value for ${arg}`);
    return args[index];
  };
  if (arg === "--cwd") options.cwd = value();
  else if (arg === "--model") options.model = value();
  else if (arg === "--effort") options.effort = value();
  else if (arg === "--output-format") options.outputFormat = value();
  else if (arg === "--add-dir") options.addDirs.push(value());
  else if (arg === "--session-id-file") options.sessionIdFile = value();
  else if (arg === "--session") options.resumeSession = value();
  else if (arg === "--continue") options.continueMode = true;
  else if (arg === "--") {
    options.prompt = args.slice(index + 1).join(" ");
    break;
  } else fail(`Unknown option: ${arg}`);
}

if (!options.prompt) fail("A non-empty prompt is required after --");
if (options.resumeSession && options.continueMode) fail("Choose only one of --continue or --session");
if (!new Set(["text", "stream-json"]).has(options.outputFormat)) fail("Unsupported output format");

const kimiBin = process.env.KIMI_WORKER_CLI || "kimi";
const child = spawn(kimiBin, ["acp"], {
  cwd: options.cwd,
  env: process.env,
  stdio: ["pipe", "pipe", "pipe"],
});

child.stderr.pipe(process.stderr);

let nextId = 1;
const pending = new Map();
let assistantText = "";

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function request(method, params) {
  const id = nextId;
  nextId += 1;
  send({ jsonrpc: "2.0", id, method, params });
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function replyToClientRequest(message) {
  if (message.method === "session/request_permission") {
    const optionsList = message.params?.options ?? [];
    const selected =
      optionsList.find((item) => item.kind === "allow_always") ??
      optionsList.find((item) => item.kind === "allow_once");
    const result = selected
      ? { outcome: { outcome: "selected", optionId: selected.optionId } }
      : { outcome: { outcome: "cancelled" } };
    send({ jsonrpc: "2.0", id: message.id, result });
    return;
  }
  send({
    jsonrpc: "2.0",
    id: message.id,
    error: { code: -32601, message: `Unsupported client method: ${message.method}` },
  });
}

function handleNotification(message) {
  if (options.outputFormat === "stream-json") process.stdout.write(`${JSON.stringify(message)}\n`);
  if (message.method !== "session/update") return;
  const update = message.params?.update;
  if (update?.sessionUpdate !== "agent_message_chunk") return;
  if (update.content?.type === "text" && typeof update.content.text === "string") {
    assistantText += update.content.text;
  }
}

const lines = createInterface({ input: child.stdout });
lines.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    process.stderr.write(`Invalid ACP JSON from Kimi Code: ${line.slice(0, 200)}\n`);
    return;
  }
  if (message.id !== undefined && message.method !== undefined) {
    replyToClientRequest(message);
    return;
  }
  if (message.id !== undefined) {
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(`${message.error.code}: ${message.error.message}`));
    else waiter.resolve(message.result ?? {});
    return;
  }
  if (message.method !== undefined) handleNotification(message);
});

const childExit = new Promise((resolve) =>
  child.once("exit", (code, signal) => {
    const exit = { code, signal };
    for (const waiter of pending.values()) {
      waiter.reject(new Error(`Kimi ACP server exited with ${code ?? signal}`));
    }
    pending.clear();
    resolve(exit);
  }),
);
child.once("error", (error) => {
  process.stderr.write(`Failed to start Kimi ACP server: ${error.message}\n`);
});

function stopChild(signal) {
  if (!child.killed) child.kill(signal);
}
process.once("SIGINT", () => stopChild("SIGINT"));
process.once("SIGTERM", () => stopChild("SIGTERM"));
process.once("SIGHUP", () => stopChild("SIGHUP"));

async function run() {
  await request("initialize", {
    protocolVersion: 1,
    clientCapabilities: {
      fs: { readTextFile: false, writeTextFile: false },
      terminal: false,
    },
    clientInfo: { name: "codex-kimi-dual-lane", version: "0.1.0" },
  });

  let sessionId = options.resumeSession;
  if (!sessionId && options.continueMode) {
    const listed = await request("session/list", { cwd: options.cwd });
    sessionId = listed.sessions?.[0]?.sessionId;
  }

  if (sessionId) {
    await request("session/resume", {
      sessionId,
      cwd: options.cwd,
      additionalDirectories: options.addDirs,
      mcpServers: [],
    });
  } else {
    const created = await request("session/new", {
      cwd: options.cwd,
      additionalDirectories: options.addDirs,
      mcpServers: [],
    });
    sessionId = created.sessionId;
  }

  if (!sessionId) throw new Error("Kimi ACP did not return a session id");
  if (options.sessionIdFile) writeFileSync(options.sessionIdFile, `${sessionId}\n`, { mode: 0o600 });

  await request("session/set_config_option", {
    sessionId,
    configId: "model",
    value: options.model,
  });
  await request("session/set_config_option", {
    sessionId,
    configId: "thinking",
    value: options.effort,
  });
  await request("session/set_mode", { sessionId, modeId: "auto" });

  const completed = await request("session/prompt", {
    sessionId,
    prompt: [{ type: "text", text: options.prompt }],
  });

  if (options.outputFormat === "stream-json") {
    process.stdout.write(`${JSON.stringify({ role: "assistant", content: assistantText })}\n`);
  } else {
    process.stdout.write(assistantText.endsWith("\n") ? assistantText : `${assistantText}\n`);
  }

  child.stdin.end();
  const exit = await childExit;
  if (exit.code !== 0) throw new Error(`Kimi ACP server exited with ${exit.code ?? exit.signal}`);
  if (["cancelled", "refusal", "max_turn_requests"].includes(completed.stopReason)) {
    throw new Error(`Kimi prompt stopped with reason: ${completed.stopReason}`);
  }
}

run().catch(async (error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  stopChild("SIGTERM");
  await childExit;
  process.exitCode = 1;
});
