const test = require("node:test");
const assert = require("node:assert/strict");

const { downloadCurrentWorld, serializeWorld } = require("../tools/elaborate-export.js");

function makeWorld() {
  const land = { pos: { x: 0, y: 0 }, height: () => 12, isSea: () => false };
  const coast = { pos: { x: 1, y: 0 }, height: () => 0, isSea: () => true };
  const hill = { pos: { x: 0, y: 1 }, height: () => 24, isSea: () => false };
  return {
    graph: {
      all: () => [land, coast, hill],
      triangles: () => [[land, coast, hill]],
    },
  };
}

test("serializes Elaborate nodes and triangle indices into the shared v1 format", () => {
  const result = serializeWorld(makeWorld());

  assert.equal(result.format, "elaborate-island-mesh");
  assert.equal(result.version, 1);
  assert.deepEqual(result.generator, { name: "Elaborate" });
  assert.deepEqual(result.vertices, [
    { x: 0, y: 0, height: 12, is_sea: false },
    { x: 1, y: 0, height: 0, is_sea: true },
    { x: 0, y: 1, height: 24, is_sea: false },
  ]);
  assert.deepEqual(result.triangles, [[0, 1, 2]]);
});

test("reports a useful error when Elaborate's graph API is unavailable", () => {
  assert.throws(
    () => serializeWorld({}),
    /Expected window\.world\.graph with all\(\) and triangles\(\)/,
  );
});

test("rejects a triangle that refers to a node outside graph.all()", () => {
  const world = makeWorld();
  const unknownNode = { pos: { x: 3, y: 3 }, height: () => 0, isSea: () => false };
  world.graph.triangles = () => [[unknownNode, ...world.graph.all().slice(1)]];
  assert.throws(() => serializeWorld(world), /triangle 0 references an unknown node/);
});

test("downloads the current world as a JSON file without changing it", () => {
  const world = makeWorld();
  const calls = { appended: 0, clicked: 0, removed: 0, revoked: 0 };
  const fakeRoot = {
    world,
    Blob: class FakeBlob {
      constructor(parts, options) {
        this.parts = parts;
        this.options = options;
      }
    },
    URL: {
      createObjectURL(blob) {
        calls.blob = blob;
        return "blob:test";
      },
      revokeObjectURL(url) {
        assert.equal(url, "blob:test");
        calls.revoked += 1;
      },
    },
    document: {
      body: { appendChild(link) { calls.appended += 1; calls.link = link; } },
      createElement(tag) {
        assert.equal(tag, "a");
        return {
          style: {},
          click() { calls.clicked += 1; },
          remove() { calls.removed += 1; },
        };
      },
    },
    setTimeout(callback, delay) {
      assert.equal(delay, 1000);
      callback();
    },
  };

  const result = downloadCurrentWorld(fakeRoot);

  assert.ok(result);
  assert.equal(result.format, "elaborate-island-mesh");
  assert.equal(calls.blob.options.type, "application/json");
  assert.equal(calls.link.download, "elaborate-island-mesh.json");
  assert.equal(calls.appended, 1);
  assert.equal(calls.clicked, 1);
  assert.equal(calls.removed, 1);
  assert.equal(calls.revoked, 1);
  assert.deepEqual(world.graph.all().map((node) => node.pos), [
    { x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0, y: 1 },
  ]);
});
