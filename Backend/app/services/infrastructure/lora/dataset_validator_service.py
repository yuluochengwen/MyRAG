"""训练数据集验证服务"""
import json
from typing import Dict, List, Tuple, Any
from pathlib import Path


class DatasetValidatorService:
    """训练数据集验证服务"""
    
    @staticmethod
    def validate_dataset(file_path: str) -> Dict[str, Any]:
        """
        验证训练数据集
        
        Args:
            file_path: 数据集文件路径
            
        Returns:
            {
                "valid": bool,
                "format": "alpaca" | "conversation" | "unknown",
                "sample_count": int,
                "errors": List[str],
                "warnings": List[str]
            }
        """
        errors = []
        warnings = []
        
        # 1. 验证文件存在
        if not Path(file_path).exists():
            return {
                "valid": False,
                "format": "unknown",
                "sample_count": 0,
                "errors": [f"文件不存在: {file_path}"],
                "warnings": []
            }
        
        # 2. 验证 JSON 格式
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "format": "unknown",
                "sample_count": 0,
                "errors": [f"JSON 格式错误: {str(e)}"],
                "warnings": []
            }
        except Exception as e:
            return {
                "valid": False,
                "format": "unknown",
                "sample_count": 0,
                "errors": [f"文件读取错误: {str(e)}"],
                "warnings": []
            }
        
        # 3. 验证数据是列表
        if not isinstance(data, list):
            return {
                "valid": False,
                "format": "unknown",
                "sample_count": 0,
                "errors": ["数据格式错误: 根元素必须是数组"],
                "warnings": []
            }
        
        # 4. 验证数据集不为空
        if len(data) == 0:
            return {
                "valid": False,
                "format": "unknown",
                "sample_count": 0,
                "errors": ["数据集为空"],
                "warnings": []
            }
        
        # 5. 验证数据集大小限制
        if len(data) > 10000:
            errors.append(f"数据集样本数量超过限制: {len(data)} > 10000")
        
        # 6. 检测数据格式
        data_format = DatasetValidatorService.detect_format(data)
        
        # 7. 根据格式验证数据
        if data_format == "alpaca":
            valid, format_errors = DatasetValidatorService.validate_alpaca_format(data)
            errors.extend(format_errors)
        elif data_format == "conversation":
            valid, format_errors = DatasetValidatorService.validate_conversation_format(data)
            errors.extend(format_errors)
        else:
            errors.append("无法识别的数据格式，支持的格式: Alpaca 或 Conversation")
            valid = False
        
        # 8. 返回验证结果
        return {
            "valid": valid and len(errors) == 0,
            "format": data_format,
            "sample_count": len(data),
            "errors": errors,
            "warnings": warnings
        }
    
    @staticmethod
    def detect_format(data: List[Dict]) -> str:
        """
        检测数据格式类型
        
        Args:
            data: 数据列表
            
        Returns:
            "alpaca" | "conversation" | "unknown"
        """
        if not data or len(data) == 0:
            return "unknown"
        
        # 检查第一个样本
        first_sample = data[0]
        
        # Alpaca 格式: 包含 instruction 和 output 字段
        if isinstance(first_sample, dict):
            if "instruction" in first_sample and "output" in first_sample:
                return "alpaca"
            
            # Conversation 格式: 包含 conversations 数组
            if "conversations" in first_sample:
                return "conversation"
        
        return "unknown"
    
    @staticmethod
    def validate_alpaca_format(data: List[Dict]) -> Tuple[bool, List[str]]:
        """
        验证 Alpaca 格式
        
        格式要求:
        [
            {
                "instruction": str (必需),
                "input": str (可选),
                "output": str (必需)
            }
        ]
        
        Args:
            data: 数据列表
            
        Returns:
            (valid, errors)
        """
        errors = []
        
        for idx, sample in enumerate(data):
            # 验证是字典
            if not isinstance(sample, dict):
                errors.append(f"样本 {idx}: 必须是对象")
                continue
            
            # 验证必需字段
            if "instruction" not in sample:
                errors.append(f"样本 {idx}: 缺少必需字段 'instruction'")
            elif not isinstance(sample["instruction"], str):
                errors.append(f"样本 {idx}: 'instruction' 必须是字符串")
            elif len(sample["instruction"].strip()) == 0:
                errors.append(f"样本 {idx}: 'instruction' 不能为空")
            
            if "output" not in sample:
                errors.append(f"样本 {idx}: 缺少必需字段 'output'")
            elif not isinstance(sample["output"], str):
                errors.append(f"样本 {idx}: 'output' 必须是字符串")
            elif len(sample["output"].strip()) == 0:
                errors.append(f"样本 {idx}: 'output' 不能为空")
            
            # 验证可选字段
            if "input" in sample:
                if not isinstance(sample["input"], str):
                    errors.append(f"样本 {idx}: 'input' 必须是字符串")
            
            # 限制错误数量，避免输出过多
            if len(errors) >= 10:
                errors.append(f"... 还有更多错误（仅显示前 10 个）")
                break
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_conversation_format(data: List[Dict]) -> Tuple[bool, List[str]]:
        """
        验证 Conversation 格式
        
        格式要求:
        [
            {
                "conversations": [
                    {"role": "user" | "assistant", "content": str}
                ]
            }
        ]
        
        Args:
            data: 数据列表
            
        Returns:
            (valid, errors)
        """
        errors = []
        
        for idx, sample in enumerate(data):
            # 验证是字典
            if not isinstance(sample, dict):
                errors.append(f"样本 {idx}: 必须是对象")
                continue
            
            # 验证 conversations 字段
            if "conversations" not in sample:
                errors.append(f"样本 {idx}: 缺少必需字段 'conversations'")
                continue
            
            conversations = sample["conversations"]
            
            # 验证 conversations 是列表
            if not isinstance(conversations, list):
                errors.append(f"样本 {idx}: 'conversations' 必须是数组")
                continue
            
            # 验证 conversations 不为空
            if len(conversations) == 0:
                errors.append(f"样本 {idx}: 'conversations' 不能为空")
                continue
            
            # 验证每个对话
            for conv_idx, conv in enumerate(conversations):
                if not isinstance(conv, dict):
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 必须是对象")
                    continue
                
                # 验证 role 字段
                if "role" not in conv:
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 缺少必需字段 'role'")
                elif conv["role"] not in ["user", "assistant", "system"]:
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 'role' 必须是 'user', 'assistant' 或 'system'")
                
                # 验证 content 字段
                if "content" not in conv:
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 缺少必需字段 'content'")
                elif not isinstance(conv["content"], str):
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 'content' 必须是字符串")
                elif len(conv["content"].strip()) == 0:
                    errors.append(f"样本 {idx}, 对话 {conv_idx}: 'content' 不能为空")
            
            # 限制错误数量
            if len(errors) >= 10:
                errors.append(f"... 还有更多错误（仅显示前 10 个）")
                break
        
        return len(errors) == 0, errors
