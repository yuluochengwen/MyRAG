"""智能助手数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP
from app.core.database import Base


class Assistant(Base):
    """智能助手模型"""
    __tablename__ = "assistants"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment='助手ID')
    name = Column(String(255), nullable=False, comment='助手名称')
    description = Column(Text, comment='助手描述')
    kb_ids = Column(String(1000), comment='关联知识库ID列表(逗号分隔)')
    embedding_model = Column(String(255), nullable=False, comment='嵌入模型')
    llm_model = Column(String(255), nullable=False, comment='大语言模型')
    llm_provider = Column(String(50), nullable=False, default='local', comment='LLM提供方')
    system_prompt = Column(Text, comment='系统提示词')
    color_theme = Column(String(50), default='blue', comment='卡片配色主题')
    status = Column(String(50), default='active', comment='状态')
    created_at = Column(TIMESTAMP, default=datetime.now, comment='创建时间')
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f"<Assistant(id={self.id}, name='{self.name}', llm_model='{self.llm_model}')>"
