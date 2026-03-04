"""Neo4j图数据库服务"""
import json
import re
import unicodedata
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase, Driver, Session
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jGraphService:
    """Neo4j图谱服务"""
    
    def __init__(self, uri: str = None, username: str = None, password: str = None):
        """
        初始化Neo4j连接
        
        Args:
            uri: Neo4j连接URI
            username: 用户名
            password: 密码
        """
        # 从配置读取或使用参数
        self.uri = uri or settings.neo4j.uri
        self.username = username or settings.neo4j.username
        self.password = password or settings.neo4j.password
        
        try:
            self.driver: Driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                max_connection_lifetime=settings.neo4j.max_connection_lifetime,
                max_connection_pool_size=settings.neo4j.max_connection_pool_size,
                connection_timeout=settings.neo4j.connection_timeout
            )
            
            # 验证连接
            self.driver.verify_connectivity()
            logger.info(f"Neo4j连接成功: uri={self.uri}")
            
            # 确保索引存在
            self._ensure_indexes()
            
        except Exception as e:
            logger.error(f"Neo4j连接失败: {str(e)}")
            raise
    
    def _ensure_indexes(self) -> None:
        """创建必要的索引以提升查询性能"""
        try:
            with self.driver.session() as session:
                # 实体名称索引
                session.run(
                    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)"
                )
                # 知识库ID索引
                session.run(
                    "CREATE INDEX entity_kb IF NOT EXISTS FOR (e:Entity) ON (e.kb_id)"
                )
                # 实体类型索引
                session.run(
                    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
                )
                # 复合索引（知识库+名称）
                session.run(
                    "CREATE INDEX entity_kb_name IF NOT EXISTS FOR (e:Entity) ON (e.kb_id, e.name)"
                )
                session.run(
                    "CREATE INDEX entity_kb_canonical IF NOT EXISTS FOR (e:Entity) ON (e.kb_id, e.canonical_name)"
                )
                session.run(
                    "CREATE INDEX entity_kb_normalized IF NOT EXISTS FOR (e:Entity) ON (e.kb_id, e.normalized_name)"
                )
                session.run(
                    "CREATE INDEX chunk_kb_chunk IF NOT EXISTS FOR (c:Chunk) ON (c.kb_id, c.chunk_id)"
                )
                session.run(
                    "CREATE INDEX chunk_file IF NOT EXISTS FOR (c:Chunk) ON (c.file_id)"
                )
                session.run(
                    "CREATE INDEX fact_kb_pred IF NOT EXISTS FOR (f:Fact) ON (f.kb_id, f.predicate)"
                )
                session.run(
                    "CREATE INDEX fact_key IF NOT EXISTS FOR (f:Fact) ON (f.fact_key)"
                )
                
            logger.info("Neo4j索引创建完成")
            
        except Exception as e:
            logger.warning(f"创建索引失败（可能已存在）: {str(e)}")

    def _normalize_lookup_key(self, value: str) -> str:
        """归一化实体匹配键：大小写折叠+全半角兼容+去除常见分隔符。"""
        if not value:
            return ""

        text = unicodedata.normalize("NFKC", str(value)).strip().lower()
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"[\s\-_/\\|·•,，。！？!?:：;；'\"“”‘’()（）\[\]{}<>《》、]+", "", text)
        return text

    def _build_match_candidates(self, name: str, candidates: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """构建实体匹配候选（原始+标准化）。"""
        raw_candidates: List[str] = []
        for item in [name, *(candidates or [])]:
            current = str(item or "").strip()
            if current and current not in raw_candidates:
                raw_candidates.append(current)

        normalized_candidates: List[str] = []
        for item in raw_candidates:
            normalized = self._normalize_lookup_key(item)
            if normalized and normalized not in normalized_candidates:
                normalized_candidates.append(normalized)

        return {
            "raw": raw_candidates,
            "normalized": normalized_candidates
        }

    def _query_entity_with_relations(self, session: Session, kb_id: int, where_clause: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        query = f"""
         MATCH (e:Entity {{kb_id: $kb_id}})
         WHERE {where_clause}
        OPTIONAL MATCH (e)-[r_out:RELATES]->(target:Entity)
        OPTIONAL MATCH (source:Entity)-[r_in:RELATES]->(e)
        RETURN e.name as name,
             e.canonical_name as canonical_name,
             e.normalized_name as normalized_name,
               e.type as type,
             e.labels as labels,
               properties(e) as attributes,
               collect(DISTINCT {{target: target.name, relation: r_out.type}}) as out_relations,
               collect(DISTINCT {{source: source.name, relation: r_in.type}}) as in_relations
        LIMIT 1
        """

        record = session.run(query, kb_id=kb_id, **params).single()
        if not record:
            return None

        out_relations = [r for r in record['out_relations'] if r['target'] is not None]
        in_relations = [r for r in record['in_relations'] if r['source'] is not None]

        return {
            'name': record['name'],
            'canonical_name': record.get('canonical_name'),
            'normalized_name': record.get('normalized_name'),
            'type': record['type'],
            'labels': record.get('labels', []),
            'attributes': dict(record['attributes']),
            'out_relations': out_relations,
            'in_relations': in_relations
        }
    
    def is_available(self) -> bool:
        """
        检查Neo4j服务是否可用
        
        Returns:
            是否可用
        """
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            return True
        except Exception as e:
            logger.warning(f"Neo4j服务不可用: {str(e)}")
            return False
    
    def batch_import_entities(
        self,
        kb_id: int,
        entities: List[Dict[str, Any]],
        run_id: Optional[str] = None
    ) -> int:
        """
        批量导入实体（性能优化）
        
        Args:
            kb_id: 知识库ID
            entities: 实体列表 [{'name': '...', 'type': '...', 'attributes': {...}}, ...]
            
        Returns:
            成功导入的数量
        """
        try:
            prepared_entities: List[Dict[str, Any]] = []
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                copied = dict(entity)
                copied['normalized_name'] = self._normalize_lookup_key(
                    copied.get('canonical_name') or copied.get('name') or ''
                )
                prepared_entities.append(copied)

            if not prepared_entities:
                return 0

            query = """
            UNWIND $entities AS entity
            MERGE (e:Entity {canonical_name: coalesce(entity.canonical_name, entity.name), kb_id: $kb_id})
            SET e.name = coalesce(entity.name, e.name),
                e.type = entity.type,
                e.labels = coalesce(entity.labels, e.labels, [entity.type]),
                e.aliases = coalesce(entity.attributes.aliases, e.aliases, []),
                e.normalized_name = coalesce(entity.normalized_name, e.normalized_name),
                e.confidence = coalesce(entity.confidence, e.confidence, 0.7),
                e.mention_count = coalesce(entity.attributes.mention_count, e.mention_count, 0),
                e.last_run_id = $run_id,
                e.updated_at = datetime()
            """
            
            # 处理属性
            has_attrs = any('attributes' in e for e in prepared_entities)
            if has_attrs:
                query += """
                SET e += CASE 
                    WHEN entity.attributes IS NOT NULL THEN entity.attributes 
                    ELSE {} 
                END
                """
            
            count = 0
            batch_size = 1000
            
            with self.driver.session() as session:
                # 分批处理,避免单次处理过多数据
                for i in range(0, len(prepared_entities), batch_size):
                    batch = prepared_entities[i:i + batch_size]
                    # 使用显式事务确保提交
                    tx = session.begin_transaction()
                    try:
                        result = tx.run(query, entities=batch, kb_id=kb_id, run_id=run_id)
                        # 消费结果确保查询执行完成
                        summary = result.consume()

                        mention_query = """
                        UNWIND $entities AS entity
                        UNWIND coalesce(entity.attributes.chunk_ids, []) AS chunk_id
                        MATCH (e:Entity {canonical_name: coalesce(entity.canonical_name, entity.name), kb_id: $kb_id})
                        MERGE (c:Chunk {chunk_id: chunk_id, kb_id: $kb_id})
                        MERGE (c)-[m:MENTIONS]->(e)
                        ON CREATE SET m.count = 1, m.first_run_id = $run_id, m.updated_at = datetime()
                        ON MATCH SET m.count = coalesce(m.count, 0) + 1, m.updated_at = datetime(), m.last_run_id = $run_id
                        """
                        mention_result = tx.run(mention_query, entities=batch, kb_id=kb_id, run_id=run_id)
                        mention_result.consume()

                        tx.commit()
                        count += len(batch)
                        logger.debug(f"实体批次 {i//batch_size + 1} 提交: {len(batch)} 个")
                    except Exception as e:
                        tx.rollback()
                        logger.error(f"实体批次 {i//batch_size + 1} 失败: {str(e)}")
                        raise
            
            # 验证导入结果
            with self.driver.session() as session:
                verify_query = "MATCH (e:Entity {kb_id: $kb_id}) RETURN count(e) as cnt"
                result = session.run(verify_query, kb_id=kb_id)
                actual_count = result.single()["cnt"]
                logger.info(f"批量导入实体成功: kb_id={kb_id}, 声称导入={count}, Neo4j实际={actual_count}")
            return count
            
        except Exception as e:
            logger.error(f"批量导入实体失败: {str(e)}")
            return 0
    
    def batch_import_relations(
        self,
        kb_id: int,
        relations: List[Dict[str, Any]],
        run_id: Optional[str] = None,
        include_fact_nodes: bool = True
    ) -> int:
        """
        批量导入关系（性能优化）
        
        Args:
            kb_id: 知识库ID
            relations: 关系列表 [{'source': '...', 'target': '...', 'relation': '...'}, ...]
            
        Returns:
            成功导入的数量
        """
        try:
            normalized_relations: List[Dict[str, Any]] = []
            for relation in relations:
                if not isinstance(relation, dict):
                    continue

                source = str(relation.get('source', '')).strip()
                target = str(relation.get('target', '')).strip()
                relation_type = str(relation.get('relation', '')).strip()
                if not source or not target or not relation_type:
                    continue

                attributes = relation.get('attributes')
                if not isinstance(attributes, dict):
                    attributes = {}

                chunk_ids = relation.get('chunk_ids', [])
                if isinstance(chunk_ids, list):
                    normalized_chunk_ids = [str(item) for item in chunk_ids if item is not None and str(item).strip()]
                else:
                    normalized_chunk_ids = []

                normalized_relations.append({
                    'source': source,
                    'target': target,
                    'relation': relation_type,
                    'confidence': relation.get('confidence', 0.6),
                    'evidence_count': relation.get('evidence_count', 1),
                    'chunk_ids': normalized_chunk_ids,
                    'attributes_json': json.dumps(attributes, ensure_ascii=False)
                })

            if not normalized_relations:
                return 0

            relation_query = """
            UNWIND $relations AS rel
            MATCH (s:Entity {kb_id: $kb_id})
            WHERE s.name = rel.source OR s.canonical_name = rel.source OR rel.source IN coalesce(s.aliases, [])
            MATCH (t:Entity {kb_id: $kb_id})
            WHERE t.name = rel.target OR t.canonical_name = rel.target OR rel.target IN coalesce(t.aliases, [])
            MERGE (s)-[r:RELATES {type: rel.relation}]->(t)
            SET r.updated_at = datetime(),
                r.confidence = coalesce(rel.confidence, r.confidence, 0.6),
                r.evidence_count = coalesce(r.evidence_count, 0) + coalesce(rel.evidence_count, 1),
                r.chunk_ids = coalesce(rel.chunk_ids, r.chunk_ids, []),
                r.attributes_json = coalesce(rel.attributes_json, r.attributes_json, '{}'),
                r.last_run_id = $run_id
            """

            fact_query = """

            MERGE (f:Fact {fact_key: coalesce(s.canonical_name, s.name) + '|' + rel.relation + '|' + coalesce(t.canonical_name, t.name), kb_id: $kb_id})
            SET f.subject = rel.source,
                f.predicate = rel.relation,
                f.object = rel.target,
                f.confidence = coalesce(rel.confidence, f.confidence, 0.6),
                f.evidence_count = coalesce(f.evidence_count, 0) + coalesce(rel.evidence_count, 1),
                f.attributes_json = coalesce(rel.attributes_json, f.attributes_json, '{}'),
                f.updated_at = datetime(),
                f.last_run_id = $run_id

            MERGE (f)-[:SUBJECT]->(s)
            MERGE (f)-[:OBJECT]->(t)

            WITH rel, f
            UNWIND coalesce(rel.chunk_ids, []) AS chunk_id
            MERGE (c:Chunk {chunk_id: chunk_id, kb_id: $kb_id})
            MERGE (f)-[sb:SUPPORTED_BY]->(c)
            ON CREATE SET sb.weight = 1, sb.first_run_id = $run_id, sb.updated_at = datetime()
            ON MATCH SET sb.weight = coalesce(sb.weight, 0) + 1, sb.last_run_id = $run_id, sb.updated_at = datetime()
            """

            query = relation_query + (fact_query if include_fact_nodes else "")
            
            count = 0
            batch_size = 1000
            
            with self.driver.session() as session:
                for i in range(0, len(normalized_relations), batch_size):
                    batch = normalized_relations[i:i + batch_size]
                    # 使用显式事务确保提交
                    tx = session.begin_transaction()
                    try:
                        result = tx.run(query, relations=batch, kb_id=kb_id, run_id=run_id)
                        # 消费结果确保查询执行完成
                        summary = result.consume()
                        tx.commit()
                        count += len(batch)
                        logger.debug(f"关系批次 {i//batch_size + 1} 提交: {len(batch)} 个")
                    except Exception as e:
                        tx.rollback()
                        logger.error(f"关系批次 {i//batch_size + 1} 失败: {str(e)}")
                        raise
            
            # 验证导入结果
            with self.driver.session() as session:
                verify_query = "MATCH (:Entity {kb_id: $kb_id})-[r:RELATES]->(:Entity {kb_id: $kb_id}) RETURN count(r) as cnt"
                result = session.run(verify_query, kb_id=kb_id)
                actual_count = result.single()["cnt"]
                logger.info(f"批量导入关系成功: kb_id={kb_id}, 声称导入={count}, Neo4j实际={actual_count}")
            
            return count
            
        except Exception as e:
            logger.error(f"批量导入关系失败: {str(e)}")
            return 0

    def batch_import_chunks(
        self,
        kb_id: int,
        chunks: List[Dict[str, Any]],
        run_id: Optional[str] = None
    ) -> int:
        """批量导入文本块节点，用于关系证据溯源。"""
        if not chunks:
            return 0

        try:
            query = """
            UNWIND $chunks AS chunk
            MERGE (c:Chunk {chunk_id: chunk.chunk_id, kb_id: $kb_id})
            SET c.file_id = chunk.file_id,
                c.chunk_index = chunk.chunk_index,
                c.updated_at = datetime(),
                c.last_run_id = $run_id
            """

            count = 0
            batch_size = 1000
            with self.driver.session() as session:
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]
                    tx = session.begin_transaction()
                    try:
                        result = tx.run(query, chunks=batch, kb_id=kb_id, run_id=run_id)
                        result.consume()
                        tx.commit()
                        count += len(batch)
                    except Exception as e:
                        tx.rollback()
                        logger.error(f"文本块批次 {i//batch_size + 1} 失败: {str(e)}")
                        raise

            logger.info(f"批量导入文本块成功: kb_id={kb_id}, chunks={count}")
            return count
        except Exception as e:
            logger.error(f"批量导入文本块失败: {str(e)}")
            return 0
    
    def find_related_entities(
        self,
        kb_id: int,
        entity: str,
        max_hops: int = 2,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        图遍历：查找与实体相关的实体
        
        Args:
            kb_id: 知识库ID
            entity: 起始实体
            max_hops: 最大跳数
            max_results: 最大返回数量
            
        Returns:
            相关实体列表
        """
        try:
            query = f"""
             MATCH (e:Entity {{kb_id: $kb_id}})
             WHERE e.name = $name OR e.canonical_name = $name OR $name IN coalesce(e.aliases, [])
             MATCH path = (e)
                         -[r:RELATES*1..{max_hops}]-
                         (related:Entity)
             WHERE related.name <> e.name
            WITH DISTINCT related, 
                 [rel in relationships(path) | rel.type] as relations,
                                 reduce(chunks = [], rel IN relationships(path) | chunks + coalesce(rel.chunk_ids, [])) as evidence_chunks,
                 length(path) as hop
            RETURN related.name as entity,
                   related.type as type,
                 related.labels as labels,
                   relations,
                                     evidence_chunks,
                   hop
            ORDER BY hop ASC, entity ASC
            LIMIT $limit
            """
            
            with self.driver.session() as session:
                result = session.run(
                    query,
                    name=entity,
                    kb_id=kb_id,
                    limit=max_results
                )
                
                entities = []
                for record in result:
                    entities.append({
                        'entity': record['entity'],
                        'type': record['type'],
                        'labels': record.get('labels', []),
                        'relations': record['relations'],
                        'evidence_chunks': list(dict.fromkeys(record.get('evidence_chunks') or []))[:5],
                        'hop': record['hop']
                    })
                
                logger.debug(f"图遍历完成: entity={entity}, found={len(entities)}")
                return entities
            
        except Exception as e:
            logger.error(f"图遍历失败: {str(e)}")
            return []

    def cleanup_fact_nodes(self, kb_id: Optional[int] = None) -> int:
        """清理Fact节点及其关联关系。"""
        try:
            if kb_id is None:
                query = """
                MATCH (f:Fact)
                WITH collect(f) as facts, count(f) as cnt
                FOREACH (fact IN facts | DETACH DELETE fact)
                RETURN cnt as deleted
                """
                params: Dict[str, Any] = {}
            else:
                query = """
                MATCH (f:Fact {kb_id: $kb_id})
                WITH collect(f) as facts, count(f) as cnt
                FOREACH (fact IN facts | DETACH DELETE fact)
                RETURN cnt as deleted
                """
                params = {"kb_id": kb_id}

            with self.driver.session() as session:
                record = session.run(query, **params).single()
                deleted = int(record["deleted"]) if record and record.get("deleted") is not None else 0
                logger.info("Fact节点清理完成: kb_id=%s, deleted=%s", kb_id, deleted)
                return deleted
        except Exception as error:
            logger.error("Fact节点清理失败: %s", str(error))
            return 0
    
    def get_entity_info(
        self,
        kb_id: int,
        entity: str,
        candidates: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取实体详细信息
        
        Args:
            kb_id: 知识库ID
            entity: 实体名称
            
        Returns:
            实体信息字典
        """
        try:
            candidate_pack = self._build_match_candidates(entity, candidates)

            with self.driver.session() as session:
                exact = self._query_entity_with_relations(
                    session=session,
                    kb_id=kb_id,
                    where_clause="e.name = $name OR e.canonical_name = $name OR $name IN coalesce(e.aliases, [])",
                    params={"name": entity}
                )
                if exact:
                    exact['match_stage'] = 'exact'
                    exact['matched_entity'] = exact.get('name')
                    return exact

                normalized_candidates = candidate_pack['normalized']
                if normalized_candidates:
                    normalized_match = self._query_entity_with_relations(
                        session=session,
                        kb_id=kb_id,
                        where_clause="e.normalized_name IN $normalized_candidates",
                        params={"normalized_candidates": normalized_candidates}
                    )
                    if normalized_match:
                        normalized_match['match_stage'] = 'normalized'
                        normalized_match['matched_entity'] = normalized_match.get('name')
                        return normalized_match

                split_candidates = candidate_pack['raw']
                if split_candidates:
                    split_match = self._query_entity_with_relations(
                        session=session,
                        kb_id=kb_id,
                        where_clause="e.name IN $split_candidates OR e.canonical_name IN $split_candidates OR any(alias IN coalesce(e.aliases, []) WHERE alias IN $split_candidates)",
                        params={"split_candidates": split_candidates}
                    )
                    if split_match:
                        split_match['match_stage'] = 'split'
                        split_match['matched_entity'] = split_match.get('name')
                        return split_match

                return None

        except Exception as e:
            logger.error(f"获取实体信息失败: {str(e)}")
            return None

    def refresh_entity_normalized_names(self, kb_id: Optional[int] = None) -> int:
        """补写历史实体的 normalized_name 字段。"""
        try:
            where_clause = "WHERE e.kb_id = $kb_id" if kb_id is not None else ""
            query = f"""
            MATCH (e:Entity)
            {where_clause}
            RETURN e.canonical_name as canonical_name, e.name as name, e.kb_id as kb_id
            """

            update_count = 0
            with self.driver.session() as session:
                records = session.run(query, kb_id=kb_id) if kb_id is not None else session.run(query)
                for record in records:
                    canonical_name = record.get('canonical_name') or record.get('name') or ''
                    normalized_name = self._normalize_lookup_key(canonical_name)
                    if not normalized_name:
                        continue

                    session.run(
                        """
                        MATCH (e:Entity {kb_id: $kb_id})
                        WHERE e.name = $name OR e.canonical_name = $canonical_name
                        SET e.normalized_name = $normalized_name
                        """,
                        kb_id=record.get('kb_id'),
                        name=record.get('name'),
                        canonical_name=record.get('canonical_name'),
                        normalized_name=normalized_name
                    )
                    update_count += 1

            logger.info("补写 normalized_name 完成: kb_id=%s, updated=%s", kb_id, update_count)
            return update_count
        except Exception as error:
            logger.error("补写 normalized_name 失败: %s", str(error))
            return 0
    
    def delete_kb_graph(self, kb_id: int) -> int:
        """
        删除知识库的所有图谱数据
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            删除的节点数量
        """
        try:
            query = """
            MATCH (n)
            WHERE n.kb_id = $kb_id
            DETACH DELETE n
            """
            
            with self.driver.session() as session:
                # 使用显式事务确保删除提交
                tx = session.begin_transaction()
                try:
                    result = tx.run(query, kb_id=kb_id)
                    summary = result.consume()
                    deleted = summary.counters.nodes_deleted
                    tx.commit()
                    logger.info(f"删除图谱数据成功: kb_id={kb_id}, nodes={deleted}")
                    return deleted
                except Exception as e:
                    tx.rollback()
                    logger.error(f"删除图谱数据失败(已回滚): {str(e)}")
                    raise
            
        except Exception as e:
            logger.error(f"删除图谱数据失败: {str(e)}")
            return 0
    
    def get_graph_stats(self, kb_id: int) -> Dict[str, Any]:
        """
        获取图谱统计信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            统计信息字典
        """
        try:
            query = """
            MATCH (e:Entity {kb_id: $kb_id})
            OPTIONAL MATCH (e)-[r:RELATES]->()
            WITH count(DISTINCT e) as node_count,
                 count(r) as edge_count,
                 collect(DISTINCT e.type) as types
            RETURN node_count, edge_count, types
            """
            
            with self.driver.session() as session:
                result = session.run(query, kb_id=kb_id)
                record = result.single()
                
                if not record:
                    return {
                        'kb_id': kb_id,
                        'node_count': 0,
                        'edge_count': 0,
                        'entity_types': {}
                    }
                
                # 获取各类型数量
                type_query = """
                MATCH (e:Entity {kb_id: $kb_id})
                RETURN e.type as type, count(*) as count
                ORDER BY count DESC
                """
                type_result = session.run(type_query, kb_id=kb_id)
                entity_types = {r['type']: r['count'] for r in type_result if r['type']}
                
                # 获取关系类型统计
                rel_query = """
                MATCH (:Entity {kb_id: $kb_id})-[r:RELATES]->(:Entity {kb_id: $kb_id})
                RETURN r.type as relation, count(*) as count
                ORDER BY count DESC
                """
                rel_result = session.run(rel_query, kb_id=kb_id)
                relation_types = {r['relation']: r['count'] for r in rel_result if r['relation']}
                
                return {
                    'kb_id': kb_id,
                    'node_count': record['node_count'],
                    'edge_count': record['edge_count'],
                    'chunk_count': self._count_chunks(kb_id),
                    'fact_count': self._count_facts(kb_id),
                    'entity_types': entity_types,
                    'relation_types': relation_types
                }
            
        except Exception as e:
            logger.error(f"获取图谱统计失败: {str(e)}")
            return {
                'kb_id': kb_id,
                'node_count': 0,
                'edge_count': 0,
                'chunk_count': 0,
                'fact_count': 0,
                'entity_types': {},
                'relation_types': {}
            }

    def _count_chunks(self, kb_id: int) -> int:
        """统计Chunk节点数量。"""
        try:
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (c:Chunk {kb_id: $kb_id}) RETURN count(c) as cnt",
                    kb_id=kb_id
                )
                record = result.single()
                return int(record['cnt']) if record else 0
        except Exception:
            return 0

    def _count_facts(self, kb_id: int) -> int:
        """统计Fact节点数量。"""
        try:
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (f:Fact {kb_id: $kb_id}) RETURN count(f) as cnt",
                    kb_id=kb_id
                )
                record = result.single()
                return int(record['cnt']) if record else 0
        except Exception:
            return 0
    
    def close(self) -> None:
        """关闭驱动连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j连接已关闭")


# 全局单例
_neo4j_graph_service_instance = None


def get_neo4j_graph_service() -> Neo4jGraphService:
    """获取Neo4j图谱服务单例"""
    global _neo4j_graph_service_instance
    if _neo4j_graph_service_instance is None:
        _neo4j_graph_service_instance = Neo4jGraphService()
    return _neo4j_graph_service_instance
