import assert from "node:assert/strict";
import http from "node:http";
import { afterEach, test } from "node:test";

import {
  createAdapterServer,
  normalizeLocalSchemaRefs,
} from "../adapter/kimi-child-adapter.mjs";

const TOKEN = "synthetic_route_token_0123456789abcdef";
const servers = [];

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (server) =>
        new Promise((resolve) => server.close(() => resolve())),
    ),
  );
});

async function listen(server) {
  servers.push(server);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  return `http://127.0.0.1:${address.port}`;
}

function fakeUpstream(handler) {
  return http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    handler({
      request,
      response,
      body: chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : null,
    });
  });
}

function adapter(upstreamUrl, options = {}) {
  return createAdapterServer({
    upstreamBase: `${upstreamUrl}/base/v1/`,
    routeToken: TOKEN,
    logger: { write() {} },
    errorLogger: { write() {} },
    ...options,
  });
}

function route(base, lane = "kimi-k3") {
  return `${base}/_kimi-child/${TOKEN}/${lane}/v1/responses`;
}

test("normalizes object-valued local refs without mutating the source schema", () => {
  const schema = {
    type: "object",
    properties: {
      "place/name": {
        type: "object",
        properties: { before: { $ref: "#/properties/place~1name" } },
      },
    },
    $defs: { __dual_lane_ref_0: { type: "string" } },
  };
  const normalized = normalizeLocalSchemaRefs(schema);
  const ref = normalized.properties["place/name"].properties.before.$ref;
  assert.equal(ref, "#/$defs/__dual_lane_ref_1");
  assert.ok(normalized.$defs.__dual_lane_ref_1);
  assert.equal(Object.getPrototypeOf(normalized), null);
  assert.equal(schema.$defs.__dual_lane_ref_1, undefined);
});

test("ignores inherited pointer targets and preserves literal __proto__ keys", () => {
  const inherited = Object.create({ inherited: { type: "string" } });
  inherited.type = "object";
  inherited.properties = {
    item: { $ref: "#/inherited" },
    literal: JSON.parse('{"__proto__":{"type":"object"}}'),
  };
  assert.equal(normalizeLocalSchemaRefs(inherited), inherited);

  const literal = JSON.parse(
    '{"type":"object","properties":{"__proto__":{"type":"object","properties":{"next":{"$ref":"#/properties/__proto__"}}}}}',
  );
  const normalized = normalizeLocalSchemaRefs(literal);
  assert.ok(Object.hasOwn(normalized.properties, "__proto__"));
  assert.equal(Object.getPrototypeOf(normalized.properties), null);
});

test("refuses a non-loopback upstream", () => {
  assert.throws(
    () =>
      createAdapterServer({
        upstreamBase: "https://example.com/v1/",
        routeToken: TOKEN,
      }),
    /must use a loopback host/,
  );
});

test("rewrites the model, keeps the configured base path, and strips secret headers", async () => {
  let observed;
  const upstreamUrl = await listen(
    fakeUpstream(({ request, response, body }) => {
      observed = { path: request.url, headers: request.headers, body };
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: true }));
    }),
  );
  const adapterUrl = await listen(adapter(upstreamUrl));

  const result = await fetch(route(adapterUrl), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
      authorization: "Bearer must-not-forward",
      cookie: "session=must-not-forward",
      "proxy-authorization": "Basic must-not-forward",
      "x-api-key": "must-not-forward",
      "x-extension-secret": "must-not-forward",
    },
    body: JSON.stringify({
      model: "gpt-5.6-sol",
      tools: [
        {
          type: "function",
          name: "recursive",
          parameters: {
            type: "object",
            properties: {
              node: {
                type: "object",
                properties: { next: { $ref: "#/properties/node" } },
              },
            },
          },
        },
      ],
    }),
  });

  assert.equal(result.status, 200);
  assert.equal(observed.path, "/base/v1/responses");
  assert.equal(observed.body.model, "kimi-oauth/k3");
  assert.equal(observed.headers.accept, "text/event-stream");
  for (const header of [
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
    "x-extension-secret",
    "transfer-encoding",
  ]) {
    assert.equal(observed.headers[header], undefined, `${header} must be stripped`);
  }
  assert.match(
    observed.body.tools[0].parameters.properties.node.properties.next.$ref,
    /^#\/\$defs\//,
  );
});

test("rejects doubled-slash routes, browser origins, and non-JSON content", async () => {
  const upstreamUrl = await listen(
    fakeUpstream(({ response }) => {
      response.writeHead(500).end();
    }),
  );
  const adapterUrl = await listen(adapter(upstreamUrl));

  const doubled = await fetch(
    `${adapterUrl}/_kimi-child/${TOKEN}/kimi-k3/v1//responses`,
    { method: "POST", headers: { "content-type": "application/json" }, body: "{}" },
  );
  assert.equal(doubled.status, 404);

  const originated = await fetch(route(adapterUrl), {
    method: "POST",
    headers: { "content-type": "application/json", origin: "https://example.com" },
    body: "{}",
  });
  assert.equal(originated.status, 403);

  const text = await fetch(route(adapterUrl), {
    method: "POST",
    headers: { "content-type": "text/plain" },
    body: "{}",
  });
  assert.equal(text.status, 404);
});

test("falls back from 256K only for the exact known error envelope", async () => {
  const models = [];
  const upstreamUrl = await listen(
    fakeUpstream(({ response, body }) => {
      models.push(body.model);
      if (body.model === "kimi-oauth/k3-256k") {
        response.writeHead(400, { "content-type": "application/json" });
        response.end(
          JSON.stringify({
            detail:
              "The 'kimi-oauth/k3-256k' model is not supported when using Codex with a ChatGPT account.",
          }),
        );
        return;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: true }));
    }),
  );
  const adapterUrl = await listen(adapter(upstreamUrl));

  const result = await fetch(route(adapterUrl, "kimi-k3-256k"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model: "gpt-5.6-terra" }),
  });

  assert.equal(result.status, 200);
  assert.deepEqual(models, ["kimi-oauth/k3-256k", "kimi-oauth/k3"]);
});

for (const [name, errorBody] of [
  ["near match", { detail: "The 'other' model is not supported when using Codex with a ChatGPT account." }],
  [
    "extra field",
    {
      detail:
        "The 'kimi-oauth/k3-256k' model is not supported when using Codex with a ChatGPT account.",
      request_id: "synthetic",
    },
  ],
  ["message in another field", { message: "not supported when using Codex with a ChatGPT account" }],
]) {
  test(`preserves a non-exact 400: ${name}`, async () => {
    const models = [];
    const upstreamUrl = await listen(
      fakeUpstream(({ response, body }) => {
        models.push(body.model);
        response.writeHead(400, { "content-type": "application/json" });
        response.end(JSON.stringify(errorBody));
      }),
    );
    const adapterUrl = await listen(adapter(upstreamUrl));
    const result = await fetch(route(adapterUrl, "kimi-k3-256k"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ model: "gpt-5.6-terra" }),
    });
    assert.equal(result.status, 400);
    assert.deepEqual(models, ["kimi-oauth/k3-256k"]);
    assert.deepEqual(await result.json(), errorBody);
  });
}

test("preserves a malformed upstream 400 without fallback", async () => {
  const models = [];
  const upstreamUrl = await listen(
    fakeUpstream(({ response, body }) => {
      models.push(body.model);
      response.writeHead(400, { "content-type": "text/plain" });
      response.end("not-json");
    }),
  );
  const adapterUrl = await listen(adapter(upstreamUrl));
  const result = await fetch(route(adapterUrl, "kimi-k3-256k"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model: "gpt-5.6-terra" }),
  });
  assert.equal(result.status, 400);
  assert.equal(await result.text(), "not-json");
  assert.deepEqual(models, ["kimi-oauth/k3-256k"]);
});

test("returns a fixed 400 for malformed client JSON without logging the fragment", async () => {
  const logs = [];
  const upstreamUrl = await listen(
    fakeUpstream(({ response }) => response.writeHead(500).end()),
  );
  const adapterUrl = await listen(
    adapter(upstreamUrl, { logger: { write: (value) => logs.push(value) } }),
  );
  const result = await fetch(route(adapterUrl), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: '{"input":"PRIVATE_FRAGMENT"',
  });
  assert.equal(result.status, 400);
  assert.deepEqual(await result.json(), { error: "invalid JSON request" });
  assert.doesNotMatch(logs.join(""), /PRIVATE_FRAGMENT/);
});

test("survives an upstream stream failure after headers are sent", async () => {
  const failures = [];
  const failingFetch = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("data: first\n\n"));
          queueMicrotask(() => controller.error(new Error("synthetic stream failure")));
        },
      }),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    );
  const adapterUrl = await listen(
    createAdapterServer({
      upstreamBase: "http://127.0.0.1:9/base/v1/",
      routeToken: TOKEN,
      logger: { write() {} },
      errorLogger: { write: (value) => failures.push(value) },
      fetchImpl: failingFetch,
    }),
  );
  await assert.rejects(
    fetch(route(adapterUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    }).then((response) => response.text()),
  );
  const health = await fetch(`${adapterUrl}/health`);
  assert.equal(health.status, 200);
  assert.match(failures.join(""), /event=adapter_failure/);
});
