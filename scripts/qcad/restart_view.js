include("scripts/simple.js");
include("scripts/Tools/arguments.js");

function readAgentJson(path) {
    var file = new QFile(path);
    if (!file.open(QIODevice.ReadOnly)) { throw new Error("Cannot open " + path); }
    var value = JSON.parse(new QTextStream(file).readAll());
    file.close();
    return value;
}

function addAgentReference(doc, di, blockId) {
    var reference = new RBlockReferenceEntity(doc, new RBlockReferenceData(blockId, new RVector(0, 0), new RVector(1, 1, 1), 0));
    reference.setBlockId(doc.getModelSpaceBlockId());
    di.applyOperation(new RAddObjectOperation(reference, false));
}

function addAgentEntity(doc, di, item, blockId) {
    var shape;
    if (item.layer && !doc.hasLayer(item.layer)) { throw new Error("Native layer missing: " + item.layer); }
    if (item.type === "line") { shape = new RLine(new RVector(item.start[0], item.start[1]), new RVector(item.end[0], item.end[1])); }
    else if (item.type === "circle") { shape = new RCircle(new RVector(item.center[0], item.center[1]), item.radius); }
    else if (item.type === "polyline") {
        shape = new RPolyline();
        for (var vertexIndex = 0; vertexIndex < item.points.length; ++vertexIndex) { shape.appendVertex(new RVector(item.points[vertexIndex][0], item.points[vertexIndex][1])); }
        shape.setClosed(item.closed);
    }
    else if (item.type === "hatch") {
        var hatchData = new RHatchData(false, item.scale, item.angle, item.pattern);
        for (var loopIndex = 0; loopIndex < item.loops.length; ++loopIndex) {
            var boundary = new RPolyline();
            for (var vertexIndex = 0; vertexIndex < item.loops[loopIndex].length; ++vertexIndex) {
                boundary.appendVertex(new RVector(item.loops[loopIndex][vertexIndex][0], item.loops[loopIndex][vertexIndex][1]));
            }
            boundary.setClosed(true);
            hatchData.newLoop();
            hatchData.addBoundary(boundary);
        }
        if (!hatchData.order()) { throw new Error("Hatch boundary ordering failed."); }
        var hatch = new RHatchEntity(doc, hatchData);
        hatch.setBlockId(blockId);
        hatch.setLayerId(doc.getLayerId("HATCH"));
        di.applyOperation(new RAddObjectOperation(hatch, false));
        return;
    }
    else {
        shape = new RSpline();
        var points = [];
        for (var fitIndex = 0; fitIndex < item.fit_points.length; ++fitIndex) { points.push(new RVector(item.fit_points[fitIndex][0], item.fit_points[fitIndex][1])); }
        shape.setFitPoints(points);
    }
    var entity = shapeToEntity(doc, shape);
    entity.setBlockId(blockId);
    if (item.layer) { entity.setLayerId(doc.getLayerId(item.layer)); }
    di.applyOperation(new RAddObjectOperation(entity, false));
}

function describeAgentEntity(doc, entity, nativeQcad) {
    var actual = {};
    if (entity.getType() === RS.EntityLine) {
        actual.type = "line"; actual.start = [entity.getStartPoint().x, entity.getStartPoint().y]; actual.end = [entity.getEndPoint().x, entity.getEndPoint().y];
    } else if (entity.getType() === RS.EntityCircle) {
        actual.type = "circle"; actual.center = [entity.getCenter().x, entity.getCenter().y]; actual.radius = entity.getRadius();
    } else if (entity.getType() === RS.EntitySpline) {
        actual.type = "spline"; actual.fit_points = [];
        var points = entity.getFitPoints();
        for (var fitIndex = 0; fitIndex < points.length; ++fitIndex) { actual.fit_points.push([points[fitIndex].x, points[fitIndex].y]); }
    } else if (entity.getType() === RS.EntityPolyline) {
        actual.type = "polyline"; actual.points = []; actual.closed = entity.isClosed();
        for (var vertexIndex = 0; vertexIndex < entity.countVertices(); ++vertexIndex) {
            var vertex = entity.getVertexAt(vertexIndex); actual.points.push([vertex.x, vertex.y]);
        }
    } else if (entity.getType() === RS.EntityHatch) {
        actual.type = "hatch"; actual.pattern = entity.getPatternName(); actual.scale = entity.getScale(); actual.angle = entity.getAngle();
        actual.area = entity.getData().getArea(); actual.loop_count = entity.getData().getLoopCount();
        if (!(actual.area > 0)) { throw new Error("Native hatch area invalid."); }
    } else { throw new Error("Unexpected native geometry."); }
    if (nativeQcad) { actual.layer = doc.queryLayer(entity.getLayerId()).getName(); }
    return actual;
}

function agentBlockSignature(doc, name, nativeQcad) {
    var ids = doc.queryBlockEntities(doc.getBlockId(name));
    var values = [];
    for (var index = 0; index < ids.length; ++index) { values.push(JSON.stringify(describeAgentEntity(doc, doc.queryEntity(ids[index]), nativeQcad))); }
    values.sort();
    return JSON.stringify(values);
}

function agentComponentBlocks(doc) {
    var names = doc.getBlockNames();
    var result = [];
    for (var index = 0; index < names.length; ++index) {
        if (names[index].indexOf("*") !== 0) { result.push(names[index]); }
    }
    return result.sort();
}

function applyAgentEdit(doc, di, edit, nativeQcad) {
    if (di.importFile(edit.base_native) !== RDocumentInterface.IoErrorNoError) { throw new Error("Base DXF import failed."); }
    if (doc.getUnit() !== RS.Millimeter) { throw new Error("Base DXF units differ."); }
    var preserved = {};
    for (var preservedIndex = 0; preservedIndex < edit.preserved.length; ++preservedIndex) {
        var preservedName = edit.preserved[preservedIndex];
        if (!doc.hasBlock(preservedName)) { throw new Error("Base DXF lacks preserved component: " + preservedName); }
        preserved[preservedName] = agentBlockSignature(doc, preservedName, nativeQcad);
    }
    for (var operationIndex = 0; operationIndex < edit.operations.length; ++operationIndex) {
        var operation = edit.operations[operationIndex];
        var name = operation.component;
        if (operation.op === "add") {
            if (doc.hasBlock(name)) { throw new Error("Added component already exists in base DXF: " + name); }
            di.applyOperation(new RAddObjectOperation(new RBlock(doc, name, new RVector(0, 0)), false));
            addAgentReference(doc, di, doc.getBlockId(name));
        } else if (!doc.hasBlock(name)) { throw new Error("Base DXF lacks component: " + name); }
        var blockId = doc.getBlockId(name);
        if (operation.op === "remove" || operation.op === "replace") {
            var deletion = new RDeleteObjectsOperation(false);
            var ids = doc.queryBlockEntities(blockId);
            for (var index = 0; index < ids.length; ++index) { deletion.deleteObject(doc.queryEntity(ids[index])); }
            if (operation.op === "remove") {
                var references = doc.queryBlockReferences(blockId);
                for (var index = 0; index < references.length; ++index) { deletion.deleteObject(doc.queryEntity(references[index])); }
            }
            di.applyOperation(deletion);
            if (operation.op === "remove") {
                var blockDeletion = new RDeleteObjectsOperation(false);
                blockDeletion.deleteObject(doc.queryBlock(blockId));
                di.applyOperation(blockDeletion);
                if (doc.hasBlock(name)) { throw new Error("Removed component still present: " + name); }
                continue;
            }
            if (doc.queryBlockEntities(blockId).length !== 0) { throw new Error("Replaced component was not cleared: " + name); }
        }
        for (var entityIndex = 0; entityIndex < operation.entities.length; ++entityIndex) {
            addAgentEntity(doc, di, operation.entities[entityIndex], blockId);
        }
    }
    return preserved;
}

function main() {
    var model = readAgentJson(getArgument(args, "-m", "-model"));
    var output = getArgument(args, "-o", "-output");
    var editPath = getArgument(args, "-e", "-edit");
    var edit = editPath ? readAgentJson(editPath) : null;
    var doc = new RDocument(new RMemoryStorage(), new RSpatialIndexNavel());
    var di = new RDocumentInterface(doc);
    var groups = {};
    var preserved = {};
    if (edit) {
        preserved = applyAgentEdit(doc, di, edit, model.native_qcad);
        for (var index = 0; index < model.entities.length; ++index) { groups[model.entities[index].component] = true; }
    } else {
        doc.setUnit(RS.Millimeter);
        if (model.native_qcad) {
            var layerNames = ["OUTLINE", "CENTERLINE", "HIDDEN", "HATCH"];
            for (var layerIndex = 0; layerIndex < layerNames.length; ++layerIndex) {
                var layer = new RLayer(doc, layerNames[layerIndex]);
                layer.setLineweight(layerNames[layerIndex] === "OUTLINE" ? RLineweight.Weight025 : RLineweight.Weight013);
                di.applyOperation(new RAddObjectOperation(layer, false));
            }
        }
        for (var index = 0; index < model.entities.length; ++index) {
            var name = model.entities[index].component;
            if (!groups[name]) {
                di.applyOperation(new RAddObjectOperation(new RBlock(doc, name, new RVector(0, 0)), false));
                groups[name] = doc.getBlockId(name);
            }
        }
        for (var index = 0; index < model.entities.length; ++index) {
            addAgentEntity(doc, di, model.entities[index], groups[model.entities[index].component]);
        }
        for (var name in groups) { addAgentReference(doc, di, groups[name]); }
    }
    if (!di.exportFile(output, "R2013 DXF")) { throw new Error("Export failed."); }
    di.destroy();
    var reopened = new RDocument(new RMemoryStorage(), new RSpatialIndexNavel());
    var reader = new RDocumentInterface(reopened);
    if (reader.importFile(output) !== RDocumentInterface.IoErrorNoError) { throw new Error("Import failed."); }
    if (JSON.stringify(agentComponentBlocks(reopened)) !== JSON.stringify(Object.keys(groups).sort())) { throw new Error("Native component blocks differ from compiled model."); }
    var report = [];
    for (var name in groups) {
        var ids = reopened.queryBlockEntities(reopened.getBlockId(name));
        var expected = model.entities.filter(function(item) { return item.component === name; });
        if (ids.length !== expected.length) { throw new Error("Block entity count differs: " + name); }
        var unmatched = expected.slice();
        for (var index = 0; index < ids.length; ++index) {
            var actual = describeAgentEntity(reopened, reopened.queryEntity(ids[index]), model.native_qcad);
            function matches(item) {
                if (item.type !== actual.type) { return false; }
                if (model.native_qcad && item.layer !== actual.layer) { return false; }
                if (actual.type === "hatch") {
                    return actual.layer === "HATCH" && actual.pattern === item.pattern && actual.loop_count === item.loops.length && Math.abs(actual.scale-item.scale)<1e-7 && Math.abs(actual.angle-item.angle)<1e-7 && Math.abs(actual.area-item.area)<1e-5;
                }
                function equalValues(first, second) {
                    if (typeof first === "number" && typeof second === "number") { return Math.abs(first - second) <= 1e-7; }
                    if (!Array.isArray(first) || !Array.isArray(second) || first.length !== second.length) { return false; }
                    for (var valueIndex = 0; valueIndex < first.length; ++valueIndex) {
                        if (!equalValues(first[valueIndex], second[valueIndex])) { return false; }
                    }
                    return true;
                }
                if (actual.type === "polyline" && actual.closed !== item.closed) { return false; }
                var fields = actual.type === "line" ? ["start", "end"] : actual.type === "circle" ? ["center", "radius"] : actual.type === "polyline" ? ["points"] : ["fit_points"];
                for (var fieldIndex = 0; fieldIndex < fields.length; ++fieldIndex) {
                    if (!equalValues(actual[fields[fieldIndex]], item[fields[fieldIndex]])) { return false; }
                }
                return true;
            }
            var matchIndex = -1;
            for (var candidateIndex = 0; candidateIndex < unmatched.length; ++candidateIndex) {
                if (matches(unmatched[candidateIndex])) { matchIndex = candidateIndex; break; }
            }
            if (matchIndex < 0) { throw new Error("Reopened native coordinates or spline fit points differ."); }
            actual.id = unmatched[matchIndex].id;
            unmatched.splice(matchIndex, 1);
            report.push(actual);
        }
    }
    if (reopened.getUnit() !== RS.Millimeter || reopened.queryAllEntities().length !== Object.keys(groups).length) { throw new Error("Units or references differ."); }
    var result = {status: "passed", reopened: true, entities: report, blocks: Object.keys(groups), review_status: "needs_review"};
    if (edit) {
        for (var preservedName in preserved) {
            if (agentBlockSignature(reopened, preservedName, model.native_qcad) !== preserved[preservedName]) { throw new Error("Preserved component changed during native edit: " + preservedName); }
        }
        var operations = [];
        for (var operationIndex = 0; operationIndex < edit.operations.length; ++operationIndex) {
            var operation = edit.operations[operationIndex];
            operations.push({op: operation.op, component: operation.component, entities: operation.entities ? operation.entities.length : 0});
        }
        result.edit = {base_native: edit.base_native, base_attempt: edit.base_attempt, operations: operations,
                       preserved_components: Object.keys(preserved).sort(), preserved_verified: true,
                       evidence: "Preserved blocks compared after base import and after edited DXF export/reimport: entity type, coordinates, layer and hatch data."};
    }
    reader.destroy();
    print("CAD_AGENT_REPORT=" + JSON.stringify(result));
}
try { main(); }
catch (error) { print("CAD_AGENT_REPORT=" + JSON.stringify({status: "failed", error: String(error)})); }
