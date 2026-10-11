"use strict";

(function installExporter(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ElaborateIslandExporter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createExporter(root) {
  const FORMAT = "elaborate-island-mesh";
  const VERSION = 1;

  function fail(message) {
    throw new Error(message);
  }

  function finiteNumber(value, label) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      fail(`${label} must be a finite number`);
    }
    return value;
  }

  function serializeWorld(world) {
    const graph = world && world.graph;
    if (!graph || typeof graph.all !== "function" || typeof graph.triangles !== "function") {
      fail("Expected window.world.graph with all() and triangles(); generate an island before exporting.");
    }

    let nodes;
    let rawTriangles;
    try {
      nodes = Array.from(graph.all());
      rawTriangles = Array.from(graph.triangles());
    } catch (error) {
      fail(`Could not read Elaborate's graph: ${error.message}`);
    }
    if (nodes.length < 3) fail("Elaborate's graph has fewer than three vertices.");
    if (rawTriangles.length === 0) fail("Elaborate's graph has no triangles to export.");

    const indices = new Map();
    const vertices = nodes.map((node, index) => {
      if (!node || !node.pos) fail(`Elaborate vertex ${index} is missing pos.`);
      if (typeof node.height !== "function" || typeof node.isSea !== "function") {
        fail(`Elaborate vertex ${index} is missing height() or isSea().`);
      }
      const isSea = node.isSea();
      if (typeof isSea !== "boolean") fail(`Elaborate vertex ${index}.isSea() did not return a boolean.`);
      indices.set(node, index);
      return {
        x: finiteNumber(node.pos.x, `vertex ${index}.x`),
        y: finiteNumber(node.pos.y, `vertex ${index}.y`),
        height: finiteNumber(node.height(), `vertex ${index}.height`),
        is_sea: isSea,
      };
    });

    const triangles = rawTriangles.map((triangle, triangleIndex) => {
      let corners;
      try {
        corners = Array.from(triangle);
      } catch {
        fail(`Elaborate triangle ${triangleIndex} is not iterable.`);
      }
      if (corners.length !== 3) fail(`Elaborate triangle ${triangleIndex} does not have three vertices.`);
      const triangleIds = corners.map((node) => indices.get(node));
      if (triangleIds.some((index) => index === undefined)) {
        fail(`Elaborate triangle ${triangleIndex} references an unknown node.`);
      }
      if (new Set(triangleIds).size !== 3) fail(`Elaborate triangle ${triangleIndex} is degenerate.`);
      return triangleIds;
    });

    return {
      format: FORMAT,
      version: VERSION,
      generator: { name: "Elaborate" },
      vertices,
      triangles,
    };
  }

  function downloadCurrentWorld(environment = root) {
    if (!environment || !environment.world) {
      fail("window.world is unavailable; open an island in Elaborate before exporting.");
    }
    if (!environment.document || typeof environment.Blob !== "function" ||
        !environment.URL || typeof environment.URL.createObjectURL !== "function") {
      fail("This page does not support downloading the exported mesh.");
    }

    const data = serializeWorld(environment.world);
    const blob = new environment.Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = environment.URL.createObjectURL(blob);
    const link = environment.document.createElement("a");
    link.href = url;
    link.download = "elaborate-island-mesh.json";
    link.style.display = "none";
    environment.document.body.appendChild(link);
    try {
      link.click();
    } finally {
      link.remove();
    }
    const defer = environment.setTimeout || (typeof setTimeout === "function" && setTimeout);
    if (defer) defer(() => environment.URL.revokeObjectURL(url), 1000);
    return data;
  }

  return { serializeWorld, downloadCurrentWorld };
});
