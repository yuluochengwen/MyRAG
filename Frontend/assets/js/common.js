/**
 * 通用工具函数
 */

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
}

/**
 * 格式化日期时间
 */
function formatDateTime(dateString) {
    const date = new Date(dateString);
    
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    const second = String(date.getSeconds()).padStart(2, '0');
    
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

/**
 * 防抖函数
 */
function debounce(func, wait) {
    let timeout;
    
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数
 */
function throttle(func, limit) {
    let inThrottle;
    
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * 复制到剪贴板
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (error) {
        console.error('复制失败:', error);
        return false;
    }
}

/**
 * 下载文件
 */
function downloadFile(content, filename, mimeType = 'text/plain') {
    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    
    a.href = url;
    a.download = filename;
    a.click();
    
    window.URL.revokeObjectURL(url);
}

/**
 * 获取URL参数
 */
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    
    for (const [key, value] of params) {
        result[key] = value;
    }
    
    return result;
}

/**
 * 设置URL参数
 */
function setUrlParams(params) {
    const url = new URL(window.location);
    
    for (const [key, value] of Object.entries(params)) {
        if (value === null || value === undefined) {
            url.searchParams.delete(key);
        } else {
            url.searchParams.set(key, value);
        }
    }
    
    window.history.pushState({}, '', url);
}

/**
 * 统一的Toast提示
 * @param {string} message - 提示消息
 * @param {string} type - 类型: success, error, warning, info
 */
function showToast(message, type = 'info') {
    // 配置
    const config = {
        'success': { bg: 'bg-green-500', icon: 'fa-check-circle' },
        'error': { bg: 'bg-red-500', icon: 'fa-exclamation-circle' },
        'warning': { bg: 'bg-yellow-500', icon: 'fa-exclamation-triangle' },
        'info': { bg: 'bg-blue-500', icon: 'fa-info-circle' }
    };
    
    const { bg, icon } = config[type] || config.info;
    
    // 创建toast元素
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 ${bg} text-white px-6 py-4 rounded-lg shadow-lg z-50 flex items-center space-x-3 transition-all duration-300 transform`;
    toast.style.minWidth = '280px';
    toast.style.maxWidth = '420px';
    
    // 添加图标和消息
    toast.innerHTML = `
        <i class="fas ${icon} text-xl flex-shrink-0"></i>
        <span class="font-medium flex-1">${escapeHtmlForToast(message)}</span>
        <button class="ml-2 text-white hover:text-gray-200 transition-colors" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    // 添加到页面并应用动画
    document.body.appendChild(toast);
    
    // 初始状态（从右侧滑入）
    toast.style.transform = 'translateX(400px)';
    toast.style.opacity = '0';
    
    // 触发动画
    setTimeout(() => {
        toast.style.transform = 'translateX(0)';
        toast.style.opacity = '1';
    }, 10);
    
    // 3秒后自动移除
    setTimeout(() => {
        toast.style.transform = 'translateX(400px)';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * 转义HTML（用于Toast）
 */
function escapeHtmlForToast(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导出到全局
window.utils = {
    formatFileSize,
    formatDateTime,
    debounce,
    throttle,
    copyToClipboard,
    downloadFile,
    getUrlParams,
    setUrlParams,
    showToast
};

// 同时导出showToast为全局函数（向后兼容）
window.showToast = showToast;
