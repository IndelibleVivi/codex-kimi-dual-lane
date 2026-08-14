import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const DEFAULT_PORT = 4213;
export const ROUTES = new Map([
  [
    "kimi-k3-256k",
    { primary: "kimi-oauth/k3-256k", fallback: "kimi-oauth/k3" },
  ],
  ["kimi-k3", { primary: "kimi-oauth/k3" }],
]);

const EXPECTED_256K_REJECTION =
  "The 'kimi-oauth/k3-256k' model is not supported when using Codex with a ChatGPT account.";

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resolveRef(ref, root) {
  if (typeof ref !== "string" || !ref.startsWith("#/")) return undefined;
  let node = root;
  for (const rawSegment of ref.slice(2).split("/")) {
    const segment = rawSegment.replace(/~1/g, "/").replace(/~0/g, "~");
    if (Array.isArray(node)) {
      if (!/^(0|[1-9]\d*)$/.test(segment)) return undefined;
      node = node[Number(segment)];
      continue;
    }
    if (!isPlainObject(node) || !Object.hasOwn(node, segment)) return undefined;
    node = node[segment];
  }
  return isPlainObject(node) ? node : undefined;
}

function defineOwn(target, key, value) {
  Object.defineProperty(target, key, {
    value,
    enumerable: true,
    configurable: true,
    writable: true,
  });
}

// Deliberately supports object-valued JSON Pointer refs beginning with `#/`.
// Root (`#`) and boolean-schema targets remain unchanged.
export function normalizeLocalSchemaRefs(schema) {
  if (!isPlainObject(schema)) return schema;

  const refs = [];
  const seenRefs = new Set();
  const collect = (node) => {
    if (Array.isArray(node)) {
      for (const child of node) collect(child);
      return;
    }
    if (!isPlainObject(node)) return;
    if (
      typeof node.$ref === "string" &&
      node.$ref.startsWith("#/") &&
      !node.$ref.startsWith("#/$defs/") &&
      !seenRefs.has(node.$ref) &&
      resolveRef(node.$ref, schema)
    ) {
      seenRefs.add(node.$ref);
      refs.push(node.$ref);
    }
    for (const child of Object.values(node)) collect(child);
  };
  collect(schema);
  if (!refs.length) return schema;

  const occupied = new Set(
    isPlainObject(schema.$defs) ? Object.keys(schema.$defs) : [],
  );
  const names = new Map();
  let index = 0;
  for (const ref of refs) {
    let name;
    do name = `__dual_lane_ref_${index++}`;
    while (occupied.has(name));
    occupied.add(name);
    names.set(ref, name);
  }

  const rewrittenNodes = new WeakMap();
  const rewrite = (node) => {
    if (Array.isArray(node)) {
      if (rewrittenNodes.has(node)) return rewrittenNodes.get(node);
      const next = [];
      rewrittenNodes.set(node, next);
      for (const child of node) next.push(rewrite(child));
      return next;
    }
    if (!isPlainObject(node)) return node;
    if (rewrittenNodes.has(node)) return rewrittenNodes.get(node);
    const next = Object.create(null);
    rewrittenNodes.set(node, next);
    for (const [key, child] of Object.entries(node)) {
      defineOwn(
        next,
        key,
        key === "$ref" && typeof child === "string" && names.has(child)
          ? `#/$defs/${names.get(child)}`
          : rewrite(child),
      );
    }
    return next;
  };

  const rewritten = rewrite(schema);
  const defs = isPlainObject(rewritten.$defs)
    ? Object.assign(Object.create(null), rewritten.$defs)
    : Object.create(null);
  for (const [ref, name] of names) defineOwn(defs, name, rewrite(resolveRef(ref, schema)));
  defineOwn(rewritten, "$defs", defs);
  return rewritten;
}

export function normalizeRequestPayload(payload, model) {
  const next = { ...payload, model };
  if (!Array.isArray(payload.tools)) return next;
  next.tools = payload.tools.map((tool) => {
    if (!isPlainObject(tool)) return tool;
    const normalized = { ...tool };
    if (isPlainObject(tool.parameters)) {
      normalized.parameters = normalizeLocalSchemaRefs(tool.parameters);
    }
    if (isPlainObject(tool.input_schema)) {
      normalized.input_schema = normalizeLocalSchemaRefs(tool.input_schema);
    }
    return normalized;
  });
  return next;
}

function requireLoopback(url) {
  if (!["127.0.0.1", "localhost", "::1", "[::1]"].includes(url.hostname)) {
    throw new Error("codex-router base_url must use a loopback host");
  }
  return url;
}

export function routerBaseUrl({ configPath, explicitBaseUrl } = {}) {
  if (explicitBaseUrl) {
    return requireLoopback(new URL(explicitBaseUrl.replace(/\/$/, "") + "/"));
  }
  const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
  const resolvedConfig = configPath || path.join(codexHome, "config.toml");
  const config = fs.readFileSync(resolvedConfig, "utf8");
  const providerBlock = config.match(
    /\[model_providers\.codex-router\]([\s\S]*?)(?=\n\[|$)/,
  );
  const match = providerBlock?.[1].match(/^base_url\s*=\s*["']([^"']+)["']/m);
  if (!match) throw new Error("codex-router base_url not found in config.toml");
  return requireLoopback(new URL(match[1].replace(/\/$/, "") + "/"));
}

export function loadRouteToken({ token, tokenFile } = {}) {
  const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
  const value =
    token ||
    process.env.KIMI_CHILD_ADAPTER_TOKEN ||
    fs.readFileSync(
      tokenFile ||
        process.env.KIMI_CHILD_ADAPTER_TOKEN_FILE ||
        path.join(codexHome, "kimi-dual-lane", "route-token"),
      "utf8",
    ).trim();
  if (!/^[A-Za-z0-9_-]{32,}$/.test(value)) {
    throw new Error("Kimi child adapter route token is missing or invalid");
  }
  return value;
}

function matchRoute(pathname, routeToken) {
  for (const [lane, models] of ROUTES) {
    if (pathname === `/_kimi-child/${routeToken}/${lane}/v1/responses`) {
      return models;
    }
  }
  return null;
}

function requestHeaders(source) {
  const headers = {};
  for (const name of ["content-type", "accept"]) {
    if (typeof source[name] === "string") headers[name] = source[name];
  }
  return headers;
}

function responseHeaders(source) {
  const headers = Object.fromEntries(source.entries());
  delete headers.connection;
  delete headers["content-length"];
  delete headers["content-encoding"];
  delete headers["transfer-encoding"];
  return headers;
}

function isExactUnsupportedError(body) {
  try {
    const payload = JSON.parse(body.toString("utf8"));
    return (
      isPlainObject(payload) &&
      Object.keys(payload).length === 1 &&
      payload.detail === EXPECTED_256K_REJECTION
    );
  } catch {
    return false;
  }
}

async function forward({ request, payload, upstreamUrl, model, fetchImpl }) {
  const body = Buffer.from(JSON.stringify(normalizeRequestPayload(payload, model)));
  return fetchImpl(upstreamUrl, {
    method: "POST",
    headers: requestHeaders(request.headers),
    body,
    duplex: "half",
  });
}

async function writeResponse(response, upstream) {
  response.writeHead(upstream.status, responseHeaders(upstream.headers));
  if (!upstream.body) return response.end();
  for await (const chunk of upstream.body) response.write(chunk);
  response.end();
}

function validHost(request) {
  const localPort = request.socket.localPort;
  return [`127.0.0.1:${localPort}`, `localhost:${localPort}`].includes(
    request.headers.host,
  );
}

export function createAdapterServer({
  upstreamBase,
  routeToken,
  logger = process.stdout,
  errorLogger = process.stderr,
  fetchImpl = fetch,
} = {}) {
  const resolvedUpstream = upstreamBase
    ? requireLoopback(new URL(String(upstreamBase).replace(/\/$/, "") + "/"))
    : routerBaseUrl({ explicitBaseUrl: process.env.KIMI_CHILD_ROUTER_BASE_URL });
  const resolvedToken = loadRouteToken({ token: routeToken });
  const upstreamResponsesUrl = new URL("responses", resolvedUpstream);

  return http.createServer(async (request, response) => {
    if (!validHost(request) || request.headers.origin) {
      response.writeHead(403, { "content-type": "application/json" });
      return response.end(JSON.stringify({ error: "forbidden caller" }));
    }

    const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
    if (request.method === "GET" && requestUrl.pathname === "/health") {
      response.writeHead(200, { "content-type": "application/json" });
      return response.end(JSON.stringify({ ok: true }));
    }

    const models = matchRoute(requestUrl.pathname, resolvedToken);
    const contentType = request.headers["content-type"] || "";
    if (
      !models ||
      request.method !== "POST" ||
      !/^application\/json(?:\s*;|$)/i.test(contentType)
    ) {
      response.writeHead(404, { "content-type": "application/json" });
      return response.end(JSON.stringify({ error: "unsupported route" }));
    }

    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let payload;
    try {
      payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      logger.write(`${new Date().toISOString()} event=invalid_json status=400\n`);
      response.writeHead(400, { "content-type": "application/json" });
      return response.end(JSON.stringify({ error: "invalid JSON request" }));
    }

    try {
      let target = models.primary;
      let upstream = await forward({
        request,
        payload,
        upstreamUrl: upstreamResponsesUrl,
        model: target,
        fetchImpl,
      });

      if (models.fallback && upstream.status === 400) {
        const errorBody = Buffer.from(await upstream.arrayBuffer());
        if (!isExactUnsupportedError(errorBody)) {
          response.writeHead(upstream.status, responseHeaders(upstream.headers));
          return response.end(errorBody);
        }
        target = models.fallback;
        upstream = await forward({
          request,
          payload,
          upstreamUrl: upstreamResponsesUrl,
          model: target,
          fetchImpl,
        });
      }

      logger.write(
        `${new Date().toISOString()} target=${target} status=${upstream.status}\n`,
      );
      await writeResponse(response, upstream);
    } catch {
      errorLogger.write(
        `${new Date().toISOString()} event=adapter_failure status=502\n`,
      );
      if (response.headersSent) {
        response.destroy();
        return;
      }
      response.writeHead(502, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: "Kimi child adapter failed" }));
    }
  });
}

export function startAdapter() {
  const port = Number(process.env.KIMI_CHILD_ADAPTER_PORT || DEFAULT_PORT);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`invalid KIMI_CHILD_ADAPTER_PORT: ${String(port)}`);
  }
  const server = createAdapterServer();
  server.listen(port, "127.0.0.1", () => {
    process.stdout.write(
      `${new Date().toISOString()} listening=127.0.0.1:${port}\n`,
    );
  });
  return server;
}

const isMain =
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;
if (isMain) startAdapter();
