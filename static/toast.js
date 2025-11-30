/**
 * Toast 通知模块
 * 提供现代化的提示消息，替代原生 alert()
 * 
 * 用法:
 *   Toast.success('操作成功！');
 *   Toast.error('操作失败，请重试');
 *   Toast.warning('请注意此操作');
 *   Toast.info('提示信息');
 *   Toast.confirm('确定要删除吗？').then(confirmed => { ... });
 */

const Toast = (function() {
    'use strict';

    // 配置
    const CONFIG = {
        position: 'top-right',  // 'top-right', 'top-left', 'bottom-right', 'bottom-left', 'top-center'
        duration: 4000,         // 默认显示时长 (ms)
        maxToasts: 5,           // 最多同时显示的 Toast 数量
        animationDuration: 300  // 动画时长 (ms)
    };

    // Toast 类型图标 (使用 emoji，避免额外依赖)
    const ICONS = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    // Toast 类型颜色
    const COLORS = {
        success: { bg: '#d4edda', border: '#c3e6cb', text: '#155724' },
        error: { bg: '#f8d7da', border: '#f5c6cb', text: '#721c24' },
        warning: { bg: '#fff3cd', border: '#ffc107', text: '#856404' },
        info: { bg: '#d1ecf1', border: '#bee5eb', text: '#0c5460' }
    };

    let container = null;
    let toastQueue = [];

    /**
     * 初始化 Toast 容器
     */
    function initContainer() {
        if (container) return container;

        container = document.createElement('div');
        container.id = 'toast-container';
        container.setAttribute('role', 'alert');
        container.setAttribute('aria-live', 'polite');

        // 根据位置设置样式
        const positionStyles = {
            'top-right': 'top: 20px; right: 20px;',
            'top-left': 'top: 20px; left: 20px;',
            'bottom-right': 'bottom: 20px; right: 20px;',
            'bottom-left': 'bottom: 20px; left: 20px;',
            'top-center': 'top: 20px; left: 50%; transform: translateX(-50%);'
        };

        container.style.cssText = `
            position: fixed;
            ${positionStyles[CONFIG.position] || positionStyles['top-right']}
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 380px;
            pointer-events: none;
        `;

        document.body.appendChild(container);
        return container;
    }

    /**
     * 创建 Toast 元素
     */
    function createToastElement(message, type, options = {}) {
        const colors = COLORS[type] || COLORS.info;
        const icon = ICONS[type] || ICONS.info;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 14px 18px;
            background: ${colors.bg};
            border: 1px solid ${colors.border};
            border-left: 4px solid ${colors.border};
            border-radius: 6px;
            color: ${colors.text};
            font-size: 14px;
            line-height: 1.5;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            opacity: 0;
            transform: translateX(100%);
            transition: all ${CONFIG.animationDuration}ms ease;
            pointer-events: auto;
            word-break: break-word;
        `;

        // 图标
        const iconSpan = document.createElement('span');
        iconSpan.textContent = icon;
        iconSpan.style.cssText = 'font-size: 16px; flex-shrink: 0;';

        // 内容区域
        const content = document.createElement('div');
        content.style.cssText = 'flex: 1;';
        
        // 消息文本
        const messageEl = document.createElement('div');
        messageEl.textContent = message;
        content.appendChild(messageEl);

        // 关闭按钮
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = `
            background: none;
            border: none;
            font-size: 20px;
            color: ${colors.text};
            cursor: pointer;
            padding: 0;
            line-height: 1;
            opacity: 0.7;
            transition: opacity 0.2s;
            flex-shrink: 0;
        `;
        closeBtn.addEventListener('mouseenter', () => closeBtn.style.opacity = '1');
        closeBtn.addEventListener('mouseleave', () => closeBtn.style.opacity = '0.7');
        closeBtn.addEventListener('click', () => dismissToast(toast));

        toast.appendChild(iconSpan);
        toast.appendChild(content);
        toast.appendChild(closeBtn);

        // 进度条 (如果设置了持续时间)
        if (options.duration !== 0) {
            const progressBar = document.createElement('div');
            progressBar.className = 'toast-progress';
            progressBar.style.cssText = `
                position: absolute;
                bottom: 0;
                left: 0;
                height: 3px;
                background: ${colors.border};
                border-radius: 0 0 0 6px;
                width: 100%;
                animation: toast-progress ${options.duration || CONFIG.duration}ms linear forwards;
            `;
            toast.style.position = 'relative';
            toast.style.overflow = 'hidden';
            toast.appendChild(progressBar);
        }

        return toast;
    }

    /**
     * 显示 Toast
     */
    function showToast(message, type, options = {}) {
        initContainer();

        // 限制最大 Toast 数量
        while (toastQueue.length >= CONFIG.maxToasts) {
            const oldToast = toastQueue.shift();
            dismissToast(oldToast);
        }

        const toast = createToastElement(message, type, options);
        container.appendChild(toast);
        toastQueue.push(toast);

        // 触发入场动画
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });

        // 自动关闭
        const duration = options.duration !== undefined ? options.duration : CONFIG.duration;
        if (duration > 0) {
            setTimeout(() => dismissToast(toast), duration);
        }

        return toast;
    }

    /**
     * 关闭 Toast
     */
    function dismissToast(toast) {
        if (!toast || !toast.parentNode) return;

        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';

        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            const index = toastQueue.indexOf(toast);
            if (index > -1) {
                toastQueue.splice(index, 1);
            }
        }, CONFIG.animationDuration);
    }

    /**
     * 确认对话框 (替代 confirm())
     */
    function showConfirm(message, options = {}) {
        return new Promise((resolve) => {
            // 创建遮罩
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 10001;
                display: flex;
                justify-content: center;
                align-items: center;
                animation: fadeIn 0.2s ease;
            `;

            // 创建对话框
            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: white;
                border-radius: 8px;
                padding: 24px;
                max-width: 400px;
                width: 90%;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                animation: slideIn 0.3s ease;
            `;

            // 图标
            const icon = document.createElement('div');
            icon.textContent = '❓';
            icon.style.cssText = 'font-size: 40px; text-align: center; margin-bottom: 16px;';

            // 消息
            const messageEl = document.createElement('div');
            messageEl.textContent = message;
            messageEl.style.cssText = `
                font-size: 16px;
                color: #333;
                text-align: center;
                margin-bottom: 24px;
                line-height: 1.5;
            `;

            // 按钮容器
            const buttons = document.createElement('div');
            buttons.style.cssText = 'display: flex; gap: 12px; justify-content: center;';

            // 取消按钮
            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = options.cancelText || '取消';
            cancelBtn.style.cssText = `
                padding: 10px 24px;
                border: 1px solid #ddd;
                border-radius: 6px;
                background: #f8f9fa;
                color: #333;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            `;
            cancelBtn.addEventListener('mouseenter', () => {
                cancelBtn.style.background = '#e9ecef';
            });
            cancelBtn.addEventListener('mouseleave', () => {
                cancelBtn.style.background = '#f8f9fa';
            });

            // 确认按钮
            const confirmBtn = document.createElement('button');
            confirmBtn.textContent = options.confirmText || '确定';
            confirmBtn.style.cssText = `
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                background: ${options.danger ? '#dc3545' : '#007bff'};
                color: white;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            `;
            confirmBtn.addEventListener('mouseenter', () => {
                confirmBtn.style.background = options.danger ? '#c82333' : '#0056b3';
            });
            confirmBtn.addEventListener('mouseleave', () => {
                confirmBtn.style.background = options.danger ? '#dc3545' : '#007bff';
            });

            // 关闭函数
            function close(result) {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    document.body.removeChild(overlay);
                    resolve(result);
                }, 200);
            }

            cancelBtn.addEventListener('click', () => close(false));
            confirmBtn.addEventListener('click', () => close(true));
            
            // ESC 键关闭
            function handleKeydown(e) {
                if (e.key === 'Escape') {
                    close(false);
                    document.removeEventListener('keydown', handleKeydown);
                }
            }
            document.addEventListener('keydown', handleKeydown);

            buttons.appendChild(cancelBtn);
            buttons.appendChild(confirmBtn);
            dialog.appendChild(icon);
            dialog.appendChild(messageEl);
            dialog.appendChild(buttons);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            // 聚焦确认按钮
            confirmBtn.focus();
        });
    }

    /**
     * 输入对话框 (替代 prompt())
     */
    function showPrompt(message, defaultValue = '', options = {}) {
        return new Promise((resolve) => {
            // 创建遮罩
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                z-index: 10001;
                display: flex;
                justify-content: center;
                align-items: center;
                animation: fadeIn 0.2s ease;
            `;

            // 创建对话框
            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: white;
                border-radius: 8px;
                padding: 24px;
                max-width: 400px;
                width: 90%;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                animation: slideIn 0.3s ease;
            `;

            // 消息
            const messageEl = document.createElement('div');
            messageEl.textContent = message;
            messageEl.style.cssText = `
                font-size: 16px;
                color: #333;
                margin-bottom: 16px;
                line-height: 1.5;
            `;

            // 输入框
            const input = document.createElement('input');
            input.type = 'text';
            input.value = defaultValue;
            input.placeholder = options.placeholder || '';
            input.style.cssText = `
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                margin-bottom: 20px;
                box-sizing: border-box;
                transition: border-color 0.2s;
            `;
            input.addEventListener('focus', () => {
                input.style.borderColor = '#007bff';
                input.style.outline = 'none';
            });
            input.addEventListener('blur', () => {
                input.style.borderColor = '#ddd';
            });

            // 按钮容器
            const buttons = document.createElement('div');
            buttons.style.cssText = 'display: flex; gap: 12px; justify-content: flex-end;';

            // 取消按钮
            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = options.cancelText || '取消';
            cancelBtn.style.cssText = `
                padding: 10px 24px;
                border: 1px solid #ddd;
                border-radius: 6px;
                background: #f8f9fa;
                color: #333;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            `;

            // 确认按钮
            const confirmBtn = document.createElement('button');
            confirmBtn.textContent = options.confirmText || '确定';
            confirmBtn.style.cssText = `
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                background: #007bff;
                color: white;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
            `;

            // 关闭函数
            function close(result) {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    document.body.removeChild(overlay);
                    resolve(result);
                }, 200);
            }

            cancelBtn.addEventListener('click', () => close(null));
            confirmBtn.addEventListener('click', () => close(input.value));
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') close(input.value);
                if (e.key === 'Escape') close(null);
            });

            buttons.appendChild(cancelBtn);
            buttons.appendChild(confirmBtn);
            dialog.appendChild(messageEl);
            dialog.appendChild(input);
            dialog.appendChild(buttons);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            // 聚焦并选中输入框
            input.focus();
            input.select();
        });
    }

    // 添加动画样式
    function addStyles() {
        if (document.getElementById('toast-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.textContent = `
            @keyframes toast-progress {
                from { width: 100%; }
                to { width: 0%; }
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes slideIn {
                from { 
                    opacity: 0;
                    transform: scale(0.9) translateY(-20px);
                }
                to { 
                    opacity: 1;
                    transform: scale(1) translateY(0);
                }
            }
        `;
        document.head.appendChild(style);
    }

    // 初始化样式
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', addStyles);
    } else {
        addStyles();
    }

    // 公共 API
    return {
        success: (message, options) => showToast(message, 'success', options),
        error: (message, options) => showToast(message, 'error', options),
        warning: (message, options) => showToast(message, 'warning', options),
        info: (message, options) => showToast(message, 'info', options),
        confirm: showConfirm,
        prompt: showPrompt,
        dismiss: dismissToast,
        
        // 配置方法
        config: (options) => {
            Object.assign(CONFIG, options);
        }
    };
})();

// 如果使用模块系统，导出 Toast
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Toast;
}
