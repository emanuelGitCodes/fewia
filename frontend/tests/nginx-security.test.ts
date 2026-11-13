import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const config = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");
const api = config.match(/location \/api\/ \{([\s\S]*?)\n    \}/)?.[1];

test("API forwards signed claims and exact Origin and strips unsigned identity", () => {
  assert.ok(api);
  assert.match(api, /proxy_set_header x-amzn-oidc-data \$http_x_amzn_oidc_data;/);
  assert.match(api, /proxy_set_header Origin \$http_origin;/);
  assert.match(api, /proxy_set_header x-amzn-oidc-identity "";/);
  assert.match(api, /proxy_set_header x-amzn-oidc-accesstoken "";/);
  assert.doesNotMatch(api, /\$http_x_amzn_oidc_(?:identity|accesstoken)/);
});

test("access logs contain only the allowed fields on every route", () => {
  const format = config.match(/log_format fewia\s+([^;]+);/)?.[1];
  assert.ok(format);
  assert.deepEqual(format.match(/\$[a-z_]+/g), [
    "$request_method",
    "$uri",
    "$status",
    "$request_time",
    "$request_id",
  ]);
  assert.equal(
    format.trim(),
    "'$request_method $uri $status $request_time $request_id'",
  );
  assert.match(
    config,
    /server \{[^{}]*access_log \/var\/log\/nginx\/access\.log fewia;/,
  );
  assert.equal((config.match(/log_format\s/g) ?? []).length, 1);
  assert.equal((config.match(/access_log\s/g) ?? []).length, 1);
  assert.doesNotMatch(
    config,
    /\$(?:request_uri|request|args|query_string|http_referer)\b/,
  );
});

test("access log fields exclude query and Referer sentinels", () => {
  const format = config.match(/log_format fewia\s+'([^']+)';/)?.[1];
  assert.ok(format);
  for (const uri of [
    "/api/auth/callback",
    "/api/auth/start",
    "/prototype",
    "/assets/app.js",
    "/",
  ]) {
    const requestUri = `${uri}?code=QUERY_SENTINEL&state=STATE_SENTINEL`;
    const fields: Record<string, string> = {
      request_method: "GET",
      uri,
      status: "200",
      request_time: "0.001",
      request_id: "a".repeat(32),
      request_uri: requestUri,
      request: `GET ${requestUri} HTTP/1.1`,
      args: "code=QUERY_SENTINEL&state=STATE_SENTINEL",
      query_string: "code=QUERY_SENTINEL&state=STATE_SENTINEL",
      http_referer: "https://example.test/REFERER_SENTINEL?code=QUERY_SENTINEL",
    };
    const entry = format.replace(/\$([a-z_]+)/g, (_, name: string) => {
      assert.ok(Object.hasOwn(fields, name), `Unexpected log field: ${name}`);
      return fields[name];
    });
    assert.equal(entry, `GET ${uri} 200 0.001 ${"a".repeat(32)}`);
    assert.doesNotMatch(entry, /QUERY_SENTINEL|STATE_SENTINEL|REFERER_SENTINEL/);
    assert.match(entry, / [a-f0-9]{32}$/);
  }
});

test("API host checks, upstream, and local callback routing remain present", () => {
  assert.ok(api);
  assert.match(api, /if \(\$fewia_host_denied\)/);
  assert.match(api, /return 421;/);
  assert.match(api, /set \$api_upstream \$\{FEWIA_API_UPSTREAM\};/);
  assert.match(api, /rewrite \^\/api\/\(\.\*\) \/\$1 break;/);
  assert.match(api, /proxy_pass http:\/\/\$api_upstream;/);
  assert.match(config, /include \/etc\/nginx\/security-headers\.conf;/);
  assert.match(config, /location \/ \{\s+try_files \$uri \$uri\/ \/index\.html;/);
});
