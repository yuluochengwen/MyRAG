"""Neo4j图数据库服务"""
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
                
            logger.info("Neo4j索引创建完成")
            
        except Exception as e:
            logger.warning(f"创建索引失败（可能已存在）: {str(e)}")
    
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
    
    def add_entity(
        self,
        kb_id: int,
        entity: str,
        entity_type: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加实体节点
        
        Args:
            kb_id: 知识库ID
            entity: 实体名称
            entity_type: 实体类型
            attributes: 实体属性
            
        Returns:
            是否成功
        """
        try:
            query = """
            MERGE (e:Entity {name: $name, kb_id: $kb_id})
            SET e.type = $type,
                e.updated_at = datetime()
            """
            
            params = {
                'name': entity,
                'kb_id': kb_id,
                'type': entity_type
            }
            
            # 添加额外属性
            if attributes:
                query += ", e += $attributes"
                params['attributes'] = attributes
            
            with self.driver.session() as session:
                session.run(query, **params)
            
            logger.debug(f"添加实体: {entity} ({entity_type}) in kb_{kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加实体失败: {str(e)}")
            return False
    
    def add_relation(
        self,
        kb_id: int,
        source: str,
        target: str,
        relation: str,
        attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加关系边
        
        Args:
            kb_id: 知识库ID
            source: 源实体
            target: 目标实体
            relation: 关系类型
            attributes: 关系属性
            
        Returns:
            是否成功
        """
        try:
            # 首先确保两个实体都存在
            query = """
            MERGE (s:Entity {name: $source, kb_id: $kb_id})
            MERGE (t:Entity {name: $target, kb_id: $kb_id})
            MERGE (s)-[r:RELATES {type: $relation}]->(t)
            SET r.updated_at = datetime()
            """
            
            params = {
                'source': source,
                'target': target,
                'kb_id': kb_id,
                'relation': relation
            }
            
            # 添加额外属性
            if attributes:
                query += ", r += $attributes"
                params['attributes'] = attributes
            
            with self.driver.session() as session:
                session.run(query, **params)
            
            logger.debug(f"添加关系: {source} -[{relation}]-> {target} in kb_{kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加关系失败: {str(e)}")
            return False
    
    def batch_import_entities(
        self,
        kb_id: int,
        entities: List[Dict[str, Any]]
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
            query = """
            UNWIND $entities AS entity
            MERGE (e:Entity {name: entity.name, kb_id: $kb_id})
            SET e.type = entity.type,
                e.updated_at = datetime()
            """
            
            # 处理属性
            has_attrs = any('attributes' in e for e in entities)
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
                for i in range(0, len(entities), batch_size):
                    batch = entities[i:i + batch_size]
                    # 使用显式事务确保提交
                    tx = session.begin_transaction()
                    try:
                        result = tx.run(query, entities=batch, kb_id=kb_id)
                        # 消费结果确保查询执行完成
                        summary = result.consume()
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
        relations: List[Dict[str, Any]]
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
            query = """
            UNWIND $relations AS rel
            MATCH (s:Entity {name: rel.source, kb_id: $kb_id})
            MATCH (t:Entity {name: rel.target, kb_id: $kb_id})
            MERGE (s)-[r:RELATES {type: rel.relation}]->(t)
            SET r.updated_at = datetime()
            """
            
            count = 0
            batch_size = 1000
            
            with self.driver.session() as session:
                for i in range(0, len(relations), batch_size):
                    batch = relations[i:i + batch_size]
                    # 使用显式事务确保提交
                    tx = session.begin_transaction()
                    try:
                        result = tx.run(query, relations=batch, kb_id=kb_id)
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
            MATCH path = (e:Entity {{name: $name, kb_id: $kb_id}})
                         -[r:RELATES*1..{max_hops}]-
                         (related:Entity)
            WHERE related.name <> $name
            WITH DISTINCT related, 
                 [rel in relationships(path) | rel.type] as relations,
                 length(path) as hop
            RETURN related.name as entity,
                   related.type as type,
                   relations,
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
                        'relations': record['relations'],
                        'hop': record['hop']
                    })
                
                logger.debug(f"图遍历完成: entity={entity}, found={len(entities)}")
                return entities
            
        except Exception as e:
            logger.error(f"图遍历失败: {str(e)}")
            return []
    
    def get_entity_info(
        self,
        kb_id: int,
        entity: str
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
            query = """
            MATCH (e:Entity {name: $name, kb_id: $kb_id})
            OPTIONAL MATCH (e)-[r_out:RELATES]->(target:Entity)
            OPTIONAL MATCH (source:Entity)-[r_in:RELATES]->(e)
            RETURN e.name as name,
                   e.type as type,
                   properties(e) as attributes,
                   collect(DISTINCT {target: target.name, relation: r_out.type}) as out_relations,
                   collect(DISTINCT {source: source.name, relation: r_in.type}) as in_relations
            """
            
            with self.driver.session() as session:
                result = session.run(query, name=entity, kb_id=kb_id)
                record = result.single()
                
                if not record:
                    return None
                
                # 过滤掉空关系
                out_relations = [r for r in record['out_relations'] if r['target'] is not None]
                in_relations = [r for r in record['in_relations'] if r['source'] is not None]
                
                return {
                    'name': record['name'],
                    'type': record['type'],
                    'attributes': dict(record['attributes']),
                    'out_relations': out_relations,
                    'in_relations': in_relations
                }
            
        except Exception as e:
            logger.error(f"获取实体信息失败: {str(e)}")
            return None
    
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
            MATCH (e:Entity {kb_id: $kb_id})
            DETACH DELETE e
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
                MATCH ()-[r:RELATES]->(:Entity {kb_id: $kb_id})
                RETURN r.type as relation, count(*) as count
                ORDER BY count DESC
                """
                rel_result = session.run(rel_query, kb_id=kb_id)
                relation_types = {r['relation']: r['count'] for r in rel_result if r['relation']}
                
                return {
                    'kb_id': kb_id,
                    'node_count': record['node_count'],
                    'edge_count': record['edge_count'],
                    'entity_types': entity_types,
                    'relation_types': relation_types
                }
            
        except Exception as e:
            logger.error(f"获取图谱统计失败: {str(e)}")
            return {
                'kb_id': kb_id,
                'node_count': 0,
                'edge_count': 0,
                'entity_types': {},
                'relation_types': {}
            }
    
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
