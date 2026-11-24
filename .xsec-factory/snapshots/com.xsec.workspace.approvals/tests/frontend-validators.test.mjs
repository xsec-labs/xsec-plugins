// Tests for the response validators the approvals view runs on every Host payload (AP-1).
// The decision logic itself lives in the Desktop session; this package only checks that the
// data it renders has the shape the view depends on.
import { test } from "node:test";
import assert from "node:assert/strict";
import { validateChunk, validatePage, validateStatistics } from "../com.xsec.desktop/frontend/index.js";

const SESSION = "session-1";
const REVISION = "a".repeat(64);

function row(overrides = {}) {
  return { session_id: SESSION, request_id: "req-1", id: "row-1", created_at: 1_700_000_000_000, ...overrides };
}

test("validatePage accepts rows of the current session with a null cursor", () => {
  const page = { rows: [row(), row({ id: "row-2", created_at: 1_700_000_001_000 })], nextCursor: null };
  assert.equal(validatePage(page, SESSION), page);
});

test("validatePage rejects rows that belong to another session", () => {
  const page = { rows: [row({ session_id: "session-2" })], nextCursor: null };
  assert.throws(() => validatePage(page, SESSION), /分页数据无效/);
});

test("validatePage accepts a cursor that names the last row", () => {
  const page = { rows: [row()], nextCursor: { createdAt: 1_700_000_000_000, id: "row-1" } };
  assert.equal(validatePage(page, SESSION), page);
});

test("validatePage rejects a cursor that does not name the last row", () => {
  const page = { rows: [row()], nextCursor: { createdAt: 1_700_000_000_000, id: "other" } };
  assert.throws(() => validatePage(page, SESSION), /游标无效/);
});

test("validateChunk counts the offset in UTF-8 bytes, not characters", () => {
  // "审批" is 2 characters but 6 bytes in UTF-8.
  const chunk = { data: "审批", nextOffset: 6, revision: REVISION };
  assert.equal(validateChunk(chunk, 0, REVISION), chunk);
  assert.throws(() => validateChunk({ data: "审批", nextOffset: 2, revision: REVISION }, 0, REVISION), /分片位置无效/);
});

test("validateChunk accepts the final chunk with a null nextOffset", () => {
  const chunk = { data: "done", nextOffset: null, revision: REVISION };
  assert.equal(validateChunk(chunk, 12, REVISION), chunk);
});

test("validateChunk rejects a revision that changed mid-record", () => {
  assert.throws(() => validateChunk({ data: "x", nextOffset: null, revision: "b".repeat(64) }, 0, REVISION), /分片版本无效/);
});

test("validateChunk rejects a revision that is not a SHA-256 hex digest", () => {
  assert.throws(() => validateChunk({ data: "x", nextOffset: null, revision: "not-a-digest" }, 0, undefined), /分片版本无效/);
});

test("validateStatistics accepts counts and a rate between 0 and 1", () => {
  const stats = {
    approval_request_count: 4,
    allowed_count: 2,
    denied_count: 1,
    manual_review_count: 1,
    bypass_count: 0,
    allow_rate: 0.5,
  };
  assert.doesNotThrow(() => validateStatistics(stats));
});

test("validateStatistics rejects negative counts and rates above 1", () => {
  const stats = {
    approval_request_count: 1,
    allowed_count: 0,
    denied_count: 0,
    manual_review_count: 0,
    bypass_count: 0,
    allow_rate: 1,
  };
  assert.throws(() => validateStatistics({ ...stats, denied_count: -1 }), /统计数据无效/);
  assert.throws(() => validateStatistics({ ...stats, allow_rate: 1.5 }), /统计数据无效/);
});
