/**
 * 知识图谱可视化模块
 * 使用 D3.js 渲染从混合检索中获取的图谱数据
 */
console.info('[graph-visualization] loaded: 20260318-graph-ui-v5');

let currentGraphData = { nodes: [], links: [] };
let currentSelectedNodeId = null;
let graphSimulation = null;

let graphLifecycleBound = false;
let graphResizeObserver = null;
let graphRerenderTimer = null;
let graphRuntime = {
    svg: null,
    nodeGroup: null,
    linkGroup: null,
    linkLabelGroup: null,
    applyFocusState: null
};

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function parseAttributesFromContent(content) {
    if (!content || typeof content !== 'string') return {};

    const attributes = {};
    const lines = content.split('\n').map(line => line.trim()).filter(Boolean);
    lines.forEach(line => {
        const separator = line.includes('：') ? '：' : (line.includes(':') ? ':' : null);
        if (!separator) return;

        const parts = line.split(separator);
        if (parts.length < 2) return;

        const key = parts[0].trim();
        const value = parts.slice(1).join(separator).trim();
        if (!key || !value) return;

        if (key.length <= 32) {
            attributes[key] = value;
        }
    });

    return attributes;
}

function tryParseObjectLikeString(raw) {
    if (typeof raw !== 'string') return null;
    const text = raw.trim();
    if (!text.startsWith('{') || !text.endsWith('}')) return null;

    try {
        const normalized = text
            .replace(/\bNone\b/g, 'null')
            .replace(/\bTrue\b/g, 'true')
            .replace(/\bFalse\b/g, 'false')
            .replace(/'/g, '"');
        const parsed = JSON.parse(normalized);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (error) {
        return null;
    }
}

function formatDetailValue(value) {
    if (value === undefined || value === null) return '';
    if (Array.isArray(value) || typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}

function normalizeEntityId(value) {
    return String(value || '').trim().replace(/\s+/g, ' ');
}

function isNonEmpty(value) {
    return String(value || '').trim() !== '';
}

function toArray(value) {
    if (Array.isArray(value)) return value;
    if (value === undefined || value === null || value === '') return [];
    return [value];
}

function getSourceKind(source) {
    return String(source?.source || source?.type || '').trim();
}

function isGraphLikeSource(source) {
    const kind = getSourceKind(source);
    if (kind === 'graph_direct' || kind === 'graph_related') return true;

    const metadata = source?.metadata;
    if (!metadata || typeof metadata !== 'object') return false;

    return Boolean(
        metadata.entity ||
        metadata.target_entity ||
        metadata.source_entity ||
        metadata.source_entity_matched ||
        metadata.relation ||
        metadata.relations
    );
}

function resolveRelationLabels(relations, fallbackRelation) {
    const fromRelations = toArray(relations)
        .flatMap(item => {
            if (typeof item === 'string') return [item.trim()];
            if (item && typeof item === 'object') {
                return [
                    item.relation,
                    item.type,
                    item.label,
                    item.name
                ].filter(Boolean).map(v => String(v).trim());
            }
            return [];
        })
        .filter(Boolean);

    const fromFallback = toArray(fallbackRelation)
        .map(item => String(item || '').trim())
        .filter(Boolean);

    const merged = Array.from(new Set([...fromRelations, ...fromFallback]));
    return merged.length > 0 ? merged : ['关联'];
}

function getEdgeKey(sourceId, targetId, relationLabel, hop) {
    return [
        normalizeEntityId(sourceId).toLowerCase(),
        normalizeEntityId(targetId).toLowerCase(),
        String(relationLabel || '关联').trim().toLowerCase(),
        String(hop || 1)
    ].join('|');
}

function upsertNode(nodesMap, id, patch) {
    if (!nodesMap.has(id)) {
        nodesMap.set(id, {
            id,
            name: id,
            type: 'Unknown',
            labels: [],
            sourceType: 'related',
            attributes: {},
            evidenceChunks: [],
            snippets: []
        });
    }

    const prev = nodesMap.get(id);
    const merged = {
        ...prev,
        ...patch,
        labels: Array.from(new Set([...(prev.labels || []), ...((patch && patch.labels) || [])].filter(Boolean))),
        attributes: {
            ...(prev.attributes || {}),
            ...(((patch && patch.attributes) || {}))
        },
        evidenceChunks: Array.from(new Set([...(prev.evidenceChunks || []), ...((patch && patch.evidenceChunks) || [])].filter(Boolean))),
        snippets: Array.from(new Set([...(prev.snippets || []), ...((patch && patch.snippets) || [])].filter(Boolean))).slice(0, 4)
    };

    nodesMap.set(id, merged);
}

function buildNodeDetails(node) {
    const details = {
        '<id>': node.id || '',
        name: node.name || '',
        type: node.type || 'Unknown'
    };

    if (Array.isArray(node.labels) && node.labels.length > 0) {
        details.labels = node.labels;
    }

    const attrs = node.attributes || {};
    Object.entries(attrs).forEach(([key, value]) => {
        if (value === undefined || value === null || String(value).trim() === '') return;

        const parsed = typeof value === 'string' ? tryParseObjectLikeString(value) : null;
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            Object.entries(parsed).forEach(([subKey, subValue]) => {
                if (subValue === undefined || subValue === null || String(subValue).trim() === '') return;
                details[subKey] = subValue;
            });
            return;
        }

        details[key] = value;
    });

    const orderedKeys = [
        '<id>', 'name', 'type', 'canonical_name', 'labels', 'aliases',
        'confidence', 'mention_count', 'kb_id', 'chunk_ids', 'first_run_id',
        'last_run_id', 'match_stage', 'query_entity'
    ];

    const entries = Object.entries(details).filter(([, value]) => String(formatDetailValue(value)).trim() !== '');
    entries.sort((a, b) => {
        const ia = orderedKeys.indexOf(a[0]);
        const ib = orderedKeys.indexOf(b[0]);
        if (ia === -1 && ib === -1) return a[0].localeCompare(b[0], 'zh-Hans-CN');
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
    });

    return entries.map(([key, value]) => ({ key, value: formatDetailValue(value) }));
}

function isGraphPanelVisible() {
    const panel = document.getElementById('graphPanel');
    if (!panel || panel.classList.contains('hidden')) return false;

    const svgEl = document.getElementById('graphSvg');
    if (!svgEl || !svgEl.parentElement) return false;

    const rect = svgEl.parentElement.getBoundingClientRect();
    return rect.width > 120 && rect.height > 120;
}

function scheduleGraphRerender(reason = 'unknown') {
    if (!currentGraphData || !Array.isArray(currentGraphData.nodes) || currentGraphData.nodes.length === 0) return;

    if (graphRerenderTimer) {
        clearTimeout(graphRerenderTimer);
    }

    graphRerenderTimer = setTimeout(() => {
        graphRerenderTimer = null;
        if (!isGraphPanelVisible()) return;
        renderKnowledgeGraph(currentGraphData, { preserveSelection: true, reason });
    }, 120);
}

function bindGraphLifecycle() {
    if (graphLifecycleBound) return;

    const panel = document.getElementById('graphPanel');
    const svgEl = document.getElementById('graphSvg');

    if (panel && typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(() => {
            if (isGraphPanelVisible()) {
                scheduleGraphRerender('panel-visible');
            }
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class', 'style'] });
    }

    if (svgEl && svgEl.parentElement && typeof ResizeObserver !== 'undefined') {
        graphResizeObserver = new ResizeObserver(() => {
            scheduleGraphRerender('container-resize');
        });
        graphResizeObserver.observe(svgEl.parentElement);
    }

    window.addEventListener('resize', () => scheduleGraphRerender('window-resize'));
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) scheduleGraphRerender('tab-visible');
    });

    graphLifecycleBound = true;
}

function initGraphVisualization() {
    const svgElement = document.getElementById('graphSvg');
    if (!svgElement || !svgElement.parentElement) return null;

    const rect = svgElement.parentElement.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width || 0));
    const height = Math.max(320, Math.floor(rect.height || 0));

    const svg = d3.select('#graphSvg');
    svg.attr('width', width).attr('height', height);
    svg.selectAll('*').remove();

    const defs = svg.append('defs');

    const bgPattern = defs.append('pattern')
        .attr('id', 'kg-grid-pattern')
        .attr('width', 24)
        .attr('height', 24)
        .attr('patternUnits', 'userSpaceOnUse');

    bgPattern.append('path')
        .attr('d', 'M 24 0 L 0 0 0 24')
        .attr('fill', 'none')
        .attr('stroke', '#d6e4f0')
        .attr('stroke-width', 1);

    const linkGradient = defs.append('linearGradient')
        .attr('id', 'kg-link-gradient')
        .attr('x1', '0%')
        .attr('y1', '0%')
        .attr('x2', '100%')
        .attr('y2', '0%');

    linkGradient.append('stop').attr('offset', '0%').attr('stop-color', '#0ea5a4').attr('stop-opacity', 0.5);
    linkGradient.append('stop').attr('offset', '100%').attr('stop-color', '#0284c7').attr('stop-opacity', 0.9);

    defs.append('marker')
        .attr('id', 'kg-arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 18)
        .attr('refY', 0)
        .attr('markerWidth', 7)
        .attr('markerHeight', 7)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#0f766e');

    const shadow = defs.append('filter')
        .attr('id', 'kg-node-shadow')
        .attr('x', '-40%')
        .attr('y', '-40%')
        .attr('width', '180%')
        .attr('height', '180%');

    shadow.append('feDropShadow')
        .attr('dx', 0)
        .attr('dy', 2)
        .attr('stdDeviation', 2)
        .attr('flood-color', '#0f172a')
        .attr('flood-opacity', 0.18);

    svg.append('rect')
        .attr('x', 0)
        .attr('y', 0)
        .attr('width', width)
        .attr('height', height)
        .attr('fill', '#f8fbff');

    svg.append('rect')
        .attr('x', 0)
        .attr('y', 0)
        .attr('width', width)
        .attr('height', height)
        .attr('fill', 'url(#kg-grid-pattern)')
        .attr('opacity', 0.4);

    const g = svg.append('g').attr('class', 'graph-container');

    const zoom = d3.zoom()
        .scaleExtent([0.45, 3.5])
        .on('zoom', event => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity.translate(width * 0.08, height * 0.03));

    graphSimulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(d => 90 + Math.min(90, (d.relation || '').length * 6)).strength(0.7))
        .force('charge', d3.forceManyBody().strength(-360))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => (d.sourceType === 'direct' ? 36 : 30)))
        .force('x', d3.forceX(width / 2).strength(0.06))
        .force('y', d3.forceY(height / 2).strength(0.06));

    return { svg, g, simulation: graphSimulation, width, height };
}

function extractGraphDataFromResponse(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return null;

    const nodes = new Map();
    const links = [];
    const linkKeys = new Set();
    let graphSourceCount = 0;

    sources.forEach(source => {
        if (!source || typeof source !== 'object') return;
        if (!isGraphLikeSource(source)) return;

        const metadata = source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
        const sourceText = source.full_content || source.content || '';
        const snippet = sourceText ? String(sourceText).slice(0, 240) : '';
        const sourceKind = getSourceKind(source);

        const directEntity = normalizeEntityId(metadata.entity || metadata.matched_entity || '');
        if (isNonEmpty(directEntity) && (sourceKind === 'graph_direct' || !metadata.target_entity)) {
            graphSourceCount += 1;

            const labels = Array.isArray(metadata.labels) ? metadata.labels : [];
            const primaryType = metadata.type || labels[0] || 'Unknown';
            const parsedAttributes = parseAttributesFromContent(sourceText);
            const metadataAttributes = metadata.entity_attributes && typeof metadata.entity_attributes === 'object'
                ? metadata.entity_attributes
                : {};

            upsertNode(nodes, directEntity, {
                id: directEntity,
                name: directEntity,
                type: primaryType,
                labels,
                sourceType: 'direct',
                attributes: {
                    ...metadataAttributes,
                    ...parsedAttributes,
                    canonical_name: metadata.canonical_name || undefined,
                    query_entity: metadata.query_entity || undefined,
                    match_stage: metadata.match_stage || undefined,
                    source_type: metadata.source_type || undefined
                },
                evidenceChunks: metadata.evidence_chunks || [],
                snippets: snippet ? [snippet] : []
            });

            // 回退关系抽取：当 graph_related 结果较少时，直接从实体属性里补边。
            const outRelations = Array.isArray(metadataAttributes.out_relations) ? metadataAttributes.out_relations : [];
            outRelations.forEach((item, idx) => {
                if (!item || typeof item !== 'object') return;
                const targetId = normalizeEntityId(item.target || item.entity || '');
                if (!isNonEmpty(targetId) || targetId === directEntity) return;

                upsertNode(nodes, targetId, {
                    id: targetId,
                    name: targetId,
                    type: 'Entity',
                    sourceType: 'related',
                    snippets: snippet ? [snippet] : []
                });

                const relationLabel = String(item.relation || item.type || '关联').trim() || '关联';
                const linkKey = getEdgeKey(directEntity, targetId, relationLabel, 1);
                if (linkKeys.has(linkKey)) return;
                linkKeys.add(linkKey);

                links.push({
                    id: `${directEntity}-${targetId}-directout-${idx}`,
                    source: directEntity,
                    target: targetId,
                    relation: relationLabel,
                    hop: 1,
                    evidenceCount: toArray(metadata.evidence_chunks).length
                });
            });

            const inRelations = Array.isArray(metadataAttributes.in_relations) ? metadataAttributes.in_relations : [];
            inRelations.forEach((item, idx) => {
                if (!item || typeof item !== 'object') return;
                const sourceId = normalizeEntityId(item.source || item.entity || '');
                if (!isNonEmpty(sourceId) || sourceId === directEntity) return;

                upsertNode(nodes, sourceId, {
                    id: sourceId,
                    name: sourceId,
                    type: 'Entity',
                    sourceType: 'related',
                    snippets: snippet ? [snippet] : []
                });

                const relationLabel = String(item.relation || item.type || '关联').trim() || '关联';
                const linkKey = getEdgeKey(sourceId, directEntity, relationLabel, 1);
                if (linkKeys.has(linkKey)) return;
                linkKeys.add(linkKey);

                links.push({
                    id: `${sourceId}-${directEntity}-directin-${idx}`,
                    source: sourceId,
                    target: directEntity,
                    relation: relationLabel,
                    hop: 1,
                    evidenceCount: toArray(metadata.evidence_chunks).length
                });
            });
        }

        const relatedSource = normalizeEntityId(
            metadata.source_entity_matched ||
            metadata.source_entity ||
            metadata.entity ||
            ''
        );

        const relatedTarget = normalizeEntityId(
            metadata.target_entity ||
            metadata.related_entity ||
            ''
        );

        if (!isNonEmpty(relatedSource) || !isNonEmpty(relatedTarget)) return;

        graphSourceCount += 1;

        upsertNode(nodes, relatedSource, {
            id: relatedSource,
            name: relatedSource,
            type: metadata.source_type || 'Entity',
            sourceType: nodes.get(relatedSource)?.sourceType === 'direct' ? 'direct' : 'related',
            evidenceChunks: metadata.evidence_chunks || [],
            snippets: snippet ? [snippet] : []
        });

        const targetLabels = Array.isArray(metadata.target_labels) ? metadata.target_labels : [];
        upsertNode(nodes, relatedTarget, {
            id: relatedTarget,
            name: relatedTarget,
            type: metadata.target_type || targetLabels[0] || 'Entity',
            labels: targetLabels,
            sourceType: 'related',
            evidenceChunks: metadata.evidence_chunks || [],
            snippets: snippet ? [snippet] : []
        });

        const relationLabels = resolveRelationLabels(metadata.relations, metadata.relation);
        const hop = Math.max(1, Number(metadata.hop || 1));

        relationLabels.forEach((relationLabel, idx) => {
            const normalizedRelation = String(relationLabel || '关联').trim() || '关联';
            const linkKey = getEdgeKey(relatedSource, relatedTarget, normalizedRelation, hop);
            if (linkKeys.has(linkKey)) return;
            linkKeys.add(linkKey);

            links.push({
                id: `${relatedSource}-${relatedTarget}-${idx}-${hop}`,
                source: relatedSource,
                target: relatedTarget,
                relation: normalizedRelation,
                hop,
                evidenceCount: toArray(metadata.evidence_chunks).length
            });
        });
    });

    if (graphSourceCount === 0 || nodes.size === 0) return null;

    const nodeList = Array.from(nodes.values()).sort((a, b) => {
        if (a.sourceType === b.sourceType) return a.name.localeCompare(b.name, 'zh-Hans-CN');
        return a.sourceType === 'direct' ? -1 : 1;
    });

    const pairIndexMap = new Map();
    links.forEach(link => {
        const s = normalizeEntityId(typeof link.source === 'object' ? link.source.id : link.source);
        const t = normalizeEntityId(typeof link.target === 'object' ? link.target.id : link.target);
        const pairKey = s < t ? `${s}|${t}` : `${t}|${s}`;
        const slot = pairIndexMap.get(pairKey) || 0;
        pairIndexMap.set(pairKey, slot + 1);
        link.curveOffset = slot;
    });

    return {
        nodes: nodeList,
        links
    };
}

function nodeFillColor(nodeType) {
    const colors = {
        Person: '#0284c7',
        Organization: '#0f766e',
        Location: '#dc2626',
        Product: '#d97706',
        Concept: '#7c3aed',
        Event: '#db2777',
        Entity: '#2563eb',
        Unknown: '#64748b'
    };
    return colors[nodeType] || colors.Unknown;
}

function renderKnowledgeGraph(graphData, options = {}) {
    bindGraphLifecycle();

    if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length === 0) {
        document.getElementById('graphEmptyState')?.classList.remove('hidden');
        document.getElementById('graphStats')?.classList.add('hidden');
        const detailList = document.getElementById('graphDetailsList');
        if (detailList) {
            detailList.innerHTML = '<p class="text-gray-500 text-sm text-center">暂无图谱数据</p>';
        }
        return;
    }

    currentGraphData = graphData;

    const preserveSelection = Boolean(options.preserveSelection);
    const hasSelectedNode = currentSelectedNodeId !== null && graphData.nodes.some(n => n.id === currentSelectedNodeId);
    if (!preserveSelection) {
        currentSelectedNodeId = graphData.nodes.length > 0 ? graphData.nodes[0].id : null;
    } else if (currentSelectedNodeId !== null && !hasSelectedNode) {
        currentSelectedNodeId = graphData.nodes.length > 0 ? graphData.nodes[0].id : null;
    }

    if (!isGraphPanelVisible()) {
        scheduleGraphRerender('panel-not-visible');
        return;
    }

    document.getElementById('graphEmptyState')?.classList.add('hidden');
    document.getElementById('graphStats')?.classList.remove('hidden');

    const entityCountEl = document.getElementById('graphEntityCount');
    const relationCountEl = document.getElementById('graphRelationCount');
    if (entityCountEl) entityCountEl.textContent = String(graphData.nodes.length);
    if (relationCountEl) relationCountEl.textContent = String(graphData.links.length);

    const graphContext = initGraphVisualization();
    if (!graphContext) return;

    const { svg, g, simulation } = graphContext;

    const link = g.append('g')
        .attr('class', 'kg-links')
        .selectAll('path')
        .data(graphData.links)
        .join('path')
        .attr('stroke', 'url(#kg-link-gradient)')
        .attr('stroke-opacity', 0.9)
        .attr('stroke-width', d => 1.8 + Math.min(1.6, (d.evidenceCount || 0) * 0.2))
        .attr('fill', 'none')
        .attr('marker-end', 'url(#kg-arrowhead)');

    const node = g.append('g')
        .attr('class', 'kg-nodes')
        .selectAll('g')
        .data(graphData.nodes)
        .join('g')
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));

    const nodeCircles = node.append('circle')
        .attr('r', d => (d.sourceType === 'direct' ? 19 : 14))
        .attr('fill', d => nodeFillColor(d.type))
        .attr('stroke', '#ffffff')
        .attr('stroke-width', d => (d.sourceType === 'direct' ? 3 : 2))
        .style('filter', 'url(#kg-node-shadow)');

    node.append('title').text(d => `${d.name} (${d.type || 'Unknown'})`);

    node.append('text')
        .attr('class', 'kg-node-label')
        .text(d => {
            const raw = String(d.name || '');
            return raw.length > 10 ? `${raw.slice(0, 10)}...` : raw;
        })
        .attr('x', 0)
        .attr('y', d => (d.sourceType === 'direct' ? 34 : 30))
        .attr('text-anchor', 'middle')
        .attr('font-size', '11px')
        .attr('font-weight', 600)
        .attr('fill', '#1f2937');

    const linkLabel = g.append('g')
        .attr('class', 'kg-link-labels')
        .selectAll('text')
        .data(graphData.links)
        .join('text')
        .attr('font-size', '10px')
        .attr('font-weight', 600)
        .attr('fill', '#0f766e')
        .attr('text-anchor', 'middle')
        .attr('paint-order', 'stroke')
        .attr('stroke', '#ecfeff')
        .attr('stroke-width', 3)
        .text(d => {
            const rel = String(d.relation || '关联');
            return rel.length > 12 ? `${rel.slice(0, 12)}...` : rel;
        });

    const applyNodeFocusState = () => {
        const selectedId = currentSelectedNodeId;
        const neighborIds = new Set();

        if (selectedId) {
            graphData.links.forEach(item => {
                const sourceId = typeof item.source === 'object' ? item.source.id : item.source;
                const targetId = typeof item.target === 'object' ? item.target.id : item.target;
                if (sourceId === selectedId) neighborIds.add(targetId);
                if (targetId === selectedId) neighborIds.add(sourceId);
            });
        }

        nodeCircles
            .attr('stroke-width', d => (d.id === selectedId ? 4 : (d.sourceType === 'direct' ? 3 : 2)))
            .attr('stroke', d => (d.id === selectedId ? '#0f172a' : '#ffffff'))
            .attr('opacity', d => {
                if (!selectedId) return 1;
                if (d.id === selectedId) return 1;
                if (neighborIds.has(d.id)) return 0.96;
                return 0.36;
            });

        link
            .attr('opacity', d => {
                if (!selectedId) return 0.95;
                const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                return sourceId === selectedId || targetId === selectedId ? 1 : 0.38;
            })
            .attr('stroke-width', d => {
                if (!selectedId) return 1.8 + Math.min(1.6, (d.evidenceCount || 0) * 0.2);
                const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                return sourceId === selectedId || targetId === selectedId ? 3 : 1.5;
            });

        linkLabel
            .attr('opacity', d => {
                if (!selectedId) return 0.95;
                const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
                const targetId = typeof d.target === 'object' ? d.target.id : d.target;
                return sourceId === selectedId || targetId === selectedId ? 0.98 : 0.15;
            });
    };

    node.on('click', (event, d) => {
        event.stopPropagation();
        currentSelectedNodeId = d.id;
        applyNodeFocusState();
        renderGraphDetails(graphData, currentSelectedNodeId);
    });

    svg.on('click', () => {
        currentSelectedNodeId = null;
        applyNodeFocusState();
        renderGraphDetails(graphData, null);
    });

    simulation.nodes(graphData.nodes);
    simulation.force('link').links(graphData.links);
    simulation.on('tick', ticked);
    simulation.alpha(1).restart();

    function ticked() {
        link.attr('d', d => {
            const sourceX = d.source.x || 0;
            const sourceY = d.source.y || 0;
            const targetX = d.target.x || 0;
            const targetY = d.target.y || 0;

            const dx = targetX - sourceX;
            const dy = targetY - sourceY;
            const dr = Math.hypot(dx, dy) || 1;

            const offsetSlot = Number(d.curveOffset || 0);
            const offset = (offsetSlot % 2 === 0 ? 1 : -1) * Math.floor((offsetSlot + 1) / 2) * 16;

            const normalX = -dy / dr;
            const normalY = dx / dr;

            const midX = (sourceX + targetX) / 2 + normalX * offset;
            const midY = (sourceY + targetY) / 2 + normalY * offset;

            return `M ${sourceX},${sourceY} Q ${midX},${midY} ${targetX},${targetY}`;
        });

        node.attr('transform', d => `translate(${d.x || 0},${d.y || 0})`);

        linkLabel
            .attr('x', d => {
                const sx = d.source.x || 0;
                const tx = d.target.x || 0;
                return (sx + tx) / 2;
            })
            .attr('y', d => {
                const sy = d.source.y || 0;
                const ty = d.target.y || 0;
                return (sy + ty) / 2 - 6;
            });
    }

    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.25).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }

    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }

    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }

    graphRuntime = {
        svg,
        nodeGroup: node,
        linkGroup: link,
        linkLabelGroup: linkLabel,
        applyFocusState: applyNodeFocusState
    };

    applyNodeFocusState();
    renderGraphDetails(graphData, currentSelectedNodeId);
}

function renderGraphDetails(graphData, selectedNodeId = null) {
    const container = document.getElementById('graphDetailsList');
    if (!container) return;

    if (selectedNodeId) {
        const selectedNode = graphData.nodes.find(n => n.id === selectedNodeId);
        if (selectedNode) {
            const connectedLinks = graphData.links.filter(link => {
                const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
                const targetId = typeof link.target === 'object' ? link.target.id : link.target;
                return sourceId === selectedNodeId || targetId === selectedNodeId;
            });

            const detailRows = buildNodeDetails(selectedNode);
            const detailHtml = detailRows.length > 0
                ? detailRows.map(item => `
                    <div class="kg-detail-row">
                        <div class="kg-detail-key">${escapeHtml(item.key)}</div>
                        <div class="kg-detail-value">${escapeHtml(item.value)}</div>
                    </div>
                `).join('')
                : '<div class="kg-detail-empty">暂无可展示属性</div>';

            const relHtml = connectedLinks.length > 0
                ? connectedLinks.map(link => {
                    const sourceName = typeof link.source === 'object' ? link.source.name : link.source;
                    const targetName = typeof link.target === 'object' ? link.target.name : link.target;
                    return `
                        <div class="kg-relation-item">
                            <span class="kg-rel-entity">${escapeHtml(sourceName)}</span>
                            <span class="kg-rel-label">${escapeHtml(link.relation || '关联')}</span>
                            <span class="kg-rel-entity">${escapeHtml(targetName)}</span>
                        </div>
                    `;
                }).join('')
                : '<div class="kg-detail-empty">暂无关联边</div>';

            container.innerHTML = `
                <div class="kg-detail-card">
                    <div class="kg-detail-header">
                        <div class="kg-detail-title">实体详情</div>
                        <div class="kg-type-chip">${escapeHtml(selectedNode.type || 'Unknown')}</div>
                    </div>
                    <div class="kg-name-chip">${escapeHtml(selectedNode.name)}</div>
                    <div class="kg-detail-table">${detailHtml}</div>
                    <div class="kg-rel-section">
                        <div class="kg-rel-title">关联关系 (${connectedLinks.length})</div>
                        <div class="kg-rel-list">${relHtml}</div>
                    </div>
                </div>
            `;
            return;
        }
    }

    const simpleList = graphData.nodes.map(node => `
        <button data-node-id="${escapeHtml(node.id)}" class="kg-node-item">
            <span class="kg-node-name">${escapeHtml(node.name)}</span>
            <span class="kg-node-type">${escapeHtml(node.type || 'Unknown')}</span>
        </button>
    `).join('');

    container.innerHTML = `
        <div class="kg-detail-empty">点击下方实体查看详情</div>
        <div class="kg-node-list">${simpleList}</div>
    `;

    container.querySelectorAll('[data-node-id]').forEach(button => {
        button.addEventListener('click', () => {
            const nodeId = button.getAttribute('data-node-id');
            if (!nodeId) return;
            currentSelectedNodeId = nodeId;

            if (typeof graphRuntime.applyFocusState === 'function') {
                graphRuntime.applyFocusState();
            }

            renderGraphDetails(graphData, nodeId);
        });
    });
}

function autoShowGraphPanelIfNeeded(sources) {
    if (!Array.isArray(sources) || sources.length === 0) return;

    const hasGraphData = sources.some(source => isGraphLikeSource(source));
    if (!hasGraphData) return;

    const panel = document.getElementById('graphPanel');
    const toggleBtn = document.getElementById('toggleGraphPanel');
    if (!panel) return;

    const wasHidden = panel.classList.contains('hidden');
    if (wasHidden) {
        panel.classList.remove('hidden');
        if (toggleBtn) toggleBtn.classList.add('hidden');
    }

    scheduleGraphRerender('auto-show');
}

function renderGraphDiagnostics(diagnostics) {
    const container = document.getElementById('graphDiagnostics');
    if (!container) return;

    if (!diagnostics) {
        container.innerHTML = '<p class="text-gray-500 text-xs">暂无图检索诊断信息</p>';
        return;
    }

    const kbDiagnostics = Array.isArray(diagnostics.kb_diagnostics) ? diagnostics.kb_diagnostics : [];
    if (kbDiagnostics.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-xs">当前检索未返回诊断详情</p>';
        return;
    }

    const extracted = [];
    const matched = [];
    const unmatched = [];
    const stages = {};

    kbDiagnostics.forEach(item => {
        (item.extracted_entities || []).forEach(entity => {
            if (entity && !extracted.includes(entity)) extracted.push(entity);
        });
        (item.matched_entities || []).forEach(entity => {
            if (entity && !matched.includes(entity)) matched.push(entity);
        });
        (item.unmatched_entities || []).forEach(entity => {
            if (entity && !unmatched.includes(entity)) unmatched.push(entity);
        });
        (item.match_details || []).forEach(detail => {
            const stage = detail.match_stage || 'none';
            stages[stage] = (stages[stage] || 0) + 1;
        });
    });

    const stageText = Object.keys(stages).length > 0
        ? Object.entries(stages).map(([key, value]) => `${key}:${value}`).join(' / ')
        : '无';

    container.innerHTML = `
        <div class="bg-emerald-50 border border-emerald-100 rounded-lg p-3 space-y-2">
            <div class="text-xs font-semibold text-emerald-700">图检索诊断</div>
            <div class="text-xs text-gray-700">抽取实体: ${extracted.length > 0 ? extracted.map(escapeHtml).join('、') : '无'}</div>
            <div class="text-xs text-green-700">命中实体: ${matched.length > 0 ? matched.map(escapeHtml).join('、') : '无'}</div>
            <div class="text-xs text-amber-700">未命中实体: ${unmatched.length > 0 ? unmatched.map(escapeHtml).join('、') : '无'}</div>
            <div class="text-xs text-gray-600">命中阶段分布: ${escapeHtml(stageText)}</div>
        </div>
    `;
}
