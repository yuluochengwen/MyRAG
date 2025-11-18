"""
Ollama代码备份脚本
在迁移到vLLM之前,备份所有Ollama相关文件
"""
import shutil
from datetime import datetime
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 备份目录
BACKUP_DIR = BASE_DIR / f"MyRAG_Ollama_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 需要备份的文件列表
FILES_TO_BACKUP = {
    # 代码文件
    'Backend/app/services/ollama_service.py': 'Backend/app/services/',
    'Backend/config.yaml': 'Backend/',
    'Backend/app/core/config.py': 'Backend/app/core/',
    'scripts/setup_ollama_models.py': 'scripts/',
    'scripts/auto_register_models.py': 'scripts/',
    'start.bat': '',
    
    # 文档文件
    'OLLAMA_LOCAL_MODELS.md': 'docs/',
    'OLLAMA_REGISTRATION_GUIDE.md': 'docs/',
    'OLLAMA_ARCHITECTURE_COMPATIBILITY.md': 'docs/',
    'DeepSeek-OCR_ISSUE_SOLUTION.md': 'docs/',
    'CHAT_IMPLEMENTATION_PLAN.md': 'docs/',
}

# 可选文件(如果存在则备份)
OPTIONAL_FILES = {
    'OLLAMA_SETUP.md': 'docs/',
}


def create_backup():
    """执行备份操作"""
    print("=" * 70)
    print("🗂️  Ollama代码备份工具")
    print("=" * 70)
    print()
    
    # 创建备份目录
    print(f"📁 创建备份目录: {BACKUP_DIR.name}")
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # 创建时间戳文件
    timestamp_file = BACKUP_DIR / "timestamp.txt"
    with open(timestamp_file, 'w', encoding='utf-8') as f:
        f.write(f"备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"备份原因: 迁移到vLLM推理引擎\n")
        f.write(f"备份内容: Ollama相关代码和文档\n")
    
    print(f"✅ 创建时间戳: {timestamp_file.name}")
    print()
    
    # 备份文件
    backed_up = 0
    skipped = 0
    
    print("📦 开始备份文件...")
    print()
    
    # 合并必需和可选文件
    all_files = {**FILES_TO_BACKUP, **OPTIONAL_FILES}
    
    for src_path, dest_dir in all_files.items():
        src_file = BASE_DIR / src_path
        
        # 检查文件是否存在
        if not src_file.exists():
            if src_path in OPTIONAL_FILES:
                print(f"⏭️  [SKIP] {src_path} (可选文件,不存在)")
                skipped += 1
                continue
            else:
                print(f"⚠️  [WARN] {src_path} (文件不存在)")
                skipped += 1
                continue
        
        # 创建目标目录
        dest_full_dir = BACKUP_DIR / dest_dir
        dest_full_dir.mkdir(parents=True, exist_ok=True)
        
        # 复制文件
        dest_file = dest_full_dir / src_file.name
        shutil.copy2(src_file, dest_file)
        
        # 显示进度
        file_size = src_file.stat().st_size / 1024  # KB
        print(f"✅ {src_path:<50} ({file_size:.1f} KB)")
        backed_up += 1
    
    print()
    print("=" * 70)
    print(f"📊 备份完成!")
    print(f"   ✅ 成功备份: {backed_up} 个文件")
    print(f"   ⏭️  跳过: {skipped} 个文件")
    print(f"   📁 备份位置: {BACKUP_DIR}")
    print("=" * 70)
    print()
    
    # 创建备份说明文档
    readme_file = BACKUP_DIR / "README_BACKUP.md"
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(f"""# Ollama代码备份

## 备份信息

- **备份时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **备份原因**: 迁移到vLLM推理引擎
- **备份内容**: Ollama相关代码和文档

## 备份文件清单

### 代码文件 ({backed_up} 个)

""")
        
        for src_path, dest_dir in FILES_TO_BACKUP.items():
            src_file = BASE_DIR / src_path
            if src_file.exists():
                f.write(f"- `{src_path}`\n")
        
        f.write(f"""
### 文档文件

- `OLLAMA_LOCAL_MODELS.md` - Ollama本地模型使用指南
- `OLLAMA_REGISTRATION_GUIDE.md` - Ollama模型注册教程
- `OLLAMA_ARCHITECTURE_COMPATIBILITY.md` - Ollama架构兼容性说明
- `DeepSeek-OCR_ISSUE_SOLUTION.md` - DeepSeek-OCR模型问题解决方案
- `CHAT_IMPLEMENTATION_PLAN.md` - 聊天功能实现计划

## 回退方案

如果需要回退到Ollama:

```bash
# 1. 停止vLLM服务
taskkill /F /IM python.exe /FI "WINDOWTITLE eq vLLM*"

# 2. 恢复备份文件
cp -r {BACKUP_DIR.name}/Backend/* Backend/
cp -r {BACKUP_DIR.name}/scripts/* scripts/
cp {BACKUP_DIR.name}/start.bat .
cp {BACKUP_DIR.name}/docs/* .

# 3. 重启Ollama服务
ollama serve

# 4. 启动后端
cd Backend
python main.py
```

## 迁移到vLLM的优势

1. ✅ 支持所有HuggingFace模型架构
2. ✅ 支持Qwen3-8B和DeepSeek-OCR-3B
3. ✅ 推理速度提升50-100%
4. ✅ OpenAI兼容API
5. ✅ 更好的GPU利用率

## 注意事项

- 本备份仅包含Ollama相关文件
- 数据库数据未备份(assistants表需手动备份)
- 如需完整回退,请参考上述回退方案
""")
    
    print(f"📄 创建备份说明: {readme_file.name}")
    print()
    
    return BACKUP_DIR


if __name__ == "__main__":
    try:
        backup_dir = create_backup()
        print("✅ 备份完成! 可以安全地开始迁移到vLLM")
        print()
        
    except Exception as e:
        print()
        print(f"❌ 备份失败: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
