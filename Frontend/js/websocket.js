/**
 * WebSocket客户端管理
 */

class WebSocketClient {
    constructor() {
        this.ws = null;
        this.clientId = this.generateClientId();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectInterval = 3000;
        this.messageHandlers = new Map();
        this.onOpen = null;
        this.onClose = null;
        this.onError = null;
    }

    /**
     * 生成客户端ID
     */
    generateClientId() {
        return `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 连接WebSocket
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.clientId}`;

        console.log('正在连接WebSocket:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = (event) => {
            console.log('WebSocket连接成功');
            this.reconnectAttempts = 0;
            
            // 发送心跳
            this.startHeartbeat();
            
            if (this.onOpen) {
                this.onOpen(event);
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // 处理心跳响应
                if (data.type === 'pong') {
                    return;
                }
                
                console.log('收到WebSocket消息:', data);
                
                // 调用对应类型的处理器
                const handler = this.messageHandlers.get(data.type);
                if (handler) {
                    handler(data);
                } else {
                    console.warn('未找到消息处理器:', data.type);
                }
            } catch (error) {
                console.error('解析WebSocket消息失败:', error, '原始数据:', event.data);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket连接关闭:', event.code, event.reason);
            
            this.stopHeartbeat();
            
            if (this.onClose) {
                this.onClose(event);
            }
            
            // 尝试重连
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`${this.reconnectInterval / 1000}秒后尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
                
                setTimeout(() => {
                    this.connect();
                }, this.reconnectInterval);
            } else {
                console.error('WebSocket重连失败，已达到最大重连次数');
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket错误:', error);
            
            if (this.onError) {
                this.onError(error);
            }
        };
    }

    /**
     * 开始心跳
     */
    startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send('ping');
            }
        }, 30000); // 每30秒发送一次心跳
    }

    /**
     * 停止心跳
     */
    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    /**
     * 注册消息处理器
     */
    on(type, handler) {
        this.messageHandlers.set(type, handler);
    }

    /**
     * 发送消息
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket未连接，无法发送消息');
        }
    }

    /**
     * 关闭连接
     */
    close() {
        this.maxReconnectAttempts = 0; // 防止重连
        
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        
        this.stopHeartbeat();
    }

    /**
     * 获取连接状态
     */
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}

// 导出
window.WebSocketClient = WebSocketClient;
