/**
 * 知识图谱可视化模块
 * 使用D3.js渲染从混合检索中获取的图谱数据
 */

// 图谱数据存储
let currentGraphData = {
    nodes: [],
    links: []
};

// D3力导向图实例
let simulation = null;

/**
 * 初始化图谱可视化
 */
function initGraphVisualization() {
    const svgElement = document.getElementById('graphSvg');
    const svg = d3.select('#graphSvg');
    
    // 获取容器尺寸
    const rect = svgElement.parentElement.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height || 400;

    // 设置SVG尺寸
    svg.attr('width', width).attr('height', height);

    // 清空SVG
    svg.selectAll('*').remove();

    // 创建容器组
    const g = svg.append('g').attr('class', 'graph-container');

    // 添加缩放行为
    const zoom = d3.zoom()
        .scaleExtent([0.5, 3])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);

    // 创建力导向图simulation
    simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(30));

    return { svg, g, simulation };
}

/**
 * 从聊天响应中提取图谱数据
 */
function extractGraphDataFromResponse(sources) {
    if (!sources || sources.length === 0) return null;

    const nodes = new Map();
    const links = [];
    let graphSourceCount = 0;

    sources.forEach(source => {
        const metadata = source.metadata || {};
        
        // 检测graph_direct来源
        if (source.source === 'graph_direct' && metadata.entity) {
            graphSourceCount++;
            const nodeId = metadata.entity;
            
            if (!nodes.has(nodeId)) {
                nodes.set(nodeId, {
                    id: nodeId,
                    name: metadata.entity,
                    type: metadata.type || 'Unknown',
                    sourceType: 'direct',
                    content: source.content
                });
            }
        }
        
        // 检测graph_related来源
        if (source.source === 'graph_related' && metadata.source_entity && metadata.target_entity) {
            graphSourceCount++;
            const sourceId = metadata.source_entity;
            const targetId = metadata.target_entity;
            
            // 添加源节点
            if (!nodes.has(sourceId)) {
                nodes.set(sourceId, {
                    id: sourceId,
                    name: sourceId,
                    type: 'Entity',
                    sourceType: 'related'
                });
            }
            
            // 添加目标节点
            if (!nodes.has(targetId)) {
                nodes.set(targetId, {
                    id: targetId,
                    name: targetId,
                    type: metadata.target_type || 'Entity',
                    sourceType: 'related'
                });
            }
            
            // 添加关系边
            const relations = metadata.relations || [];
            relations.forEach((rel, idx) => {
                links.push({
                    source: sourceId,
                    target: targetId,
                    relation: rel,
                    hop: metadata.hop || 1
                });
            });
        }
    });

    if (graphSourceCount === 0) return null;

    return {
        nodes: Array.from(nodes.values()),
        links: links
    };
}

/**
 * 渲染知识图谱
 */
function renderKnowledgeGraph(graphData) {
    if (!graphData || graphData.nodes.length === 0) {
        // 显示空状态
        document.getElementById('graphEmptyState').classList.remove('hidden');
        document.getElementById('graphStats').classList.add('hidden');
        document.getElementById('graphDetailsList').innerHTML = '<p class="text-gray-500 text-sm text-center">暂无图谱数据</p>';
        return;
    }

    // 隐藏空状态
    document.getElementById('graphEmptyState').classList.add('hidden');
    document.getElementById('graphStats').classList.remove('hidden');

    // 更新统计信息
    document.getElementById('graphEntityCount').textContent = graphData.nodes.length;
    document.getElementById('graphRelationCount').textContent = graphData.links.length;

    // 更新全局数据
    currentGraphData = graphData;

    // 初始化D3图谱
    const { svg, g, simulation } = initGraphVisualization();
    
    // 创建连线
    const link = g.append('g')
        .attr('class', 'links')
        .selectAll('line')
        .data(graphData.links)
        .join('line')
        .attr('stroke', '#86efac')
        .attr('stroke-width', 2)
        .attr('marker-end', 'url(#arrowhead)');

    // 添加箭头定义
    svg.append('defs').append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#86efac');

    // 创建节点组
    const node = g.append('g')
        .attr('class', 'nodes')
        .selectAll('g')
        .data(graphData.nodes)
        .join('g')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));

    // 节点圆圈
    node.append('circle')
        .attr('r', d => d.sourceType === 'direct' ? 20 : 15)
        .attr('fill', d => {
            const colors = {
                'Person': '#3b82f6',
                'Organization': '#8b5cf6', 
                'Location': '#ef4444',
                'Product': '#f59e0b',
                'Concept': '#10b981',
                'Event': '#ec4899',
                'Unknown': '#6b7280'
            };
            return colors[d.type] || colors['Unknown'];
        })
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer');

    // 节点标签
    node.append('text')
        .text(d => d.name.length > 8 ? d.name.substring(0, 8) + '...' : d.name)
        .attr('x', 0)
        .attr('y', 30)
        .attr('text-anchor', 'middle')
        .attr('font-size', '11px')
        .attr('fill', '#374151');

    // 关系标签
    const linkLabel = g.append('g')
        .attr('class', 'link-labels')
        .selectAll('text')
        .data(graphData.links)
        .join('text')
        .attr('font-size', '10px')
        .attr('fill', '#059669')
        .attr('text-anchor', 'middle')
        .text(d => d.relation);

    // 更新simulation
    simulation.nodes(graphData.nodes);
    simulation.force('link').links(graphData.links);
    simulation.on('tick', ticked);
    simulation.alpha(1).restart();

    function ticked() {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x},${d.y})`);

        linkLabel
            .attr('x', d => (d.source.x + d.target.x) / 2)
            .attr('y', d => (d.source.y + d.target.y) / 2);
    }

    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
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

    // 渲染详情列表
    renderGraphDetails(graphData);
}

/**
 * 渲染图谱详情列表
 */
function renderGraphDetails(graphData) {
    const container = document.getElementById('graphDetailsList');
    if (!container) return;

    let html = '';

    // 按类型分组实体
    const entityTypes = {};
    graphData.nodes.forEach(node => {
        if (!entityTypes[node.type]) {
            entityTypes[node.type] = [];
        }
        entityTypes[node.type].push(node);
    });

    // 渲染实体
    Object.keys(entityTypes).forEach(type => {
        const typeColors = {
            'Person': 'blue',
            'Organization': 'purple',
            'Location': 'red',
            'Product': 'yellow',
            'Concept': 'green',
            'Event': 'pink'
        };
        const color = typeColors[type] || 'gray';

        html += `<div class="mb-3">
            <div class="text-xs font-bold text-${color}-600 mb-1">${type} (${entityTypes[type].length})</div>`;
        
        entityTypes[type].forEach(node => {
            html += `<div class="pl-2 text-xs text-gray-700 border-l-2 border-${color}-300 py-1">
                • ${node.name}
            </div>`;
        });

        html += `</div>`;
    });

    // 渲染关系
    if (graphData.links.length > 0) {
        html += `<div class="mb-3">
            <div class="text-xs font-bold text-green-600 mb-1">关系 (${graphData.links.length})</div>`;
        
        graphData.links.forEach(link => {
            const sourceName = typeof link.source === 'object' ? link.source.name : link.source;
            const targetName = typeof link.target === 'object' ? link.target.name : link.target;
            html += `<div class="pl-2 text-xs text-gray-700 border-l-2 border-green-300 py-1">
                ${sourceName} → <span class="text-green-600 font-medium">${link.relation}</span> → ${targetName}
            </div>`;
        });

        html += `</div>`;
    }

    container.innerHTML = html || '<p class="text-gray-500 text-sm text-center">暂无图谱数据</p>';
}

/**
 * 自动展开图谱面板（如果有图谱数据）
 */
function autoShowGraphPanelIfNeeded(sources) {
    if (!sources || sources.length === 0) return;

    const hasGraphData = sources.some(s => 
        s.source === 'graph_direct' || s.source === 'graph_related'
    );

    if (hasGraphData) {
        const panel = document.getElementById('graphPanel');
        const toggleBtn = document.getElementById('toggleGraphPanel');
        if (panel && panel.classList.contains('hidden')) {
            panel.classList.remove('hidden');
            // 自动展开面板时隐藏切换按钮
            if (toggleBtn) {
                toggleBtn.classList.add('hidden');
            }
        }
    }
}
