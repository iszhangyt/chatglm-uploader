// DOM元素
const historyList = document.getElementById('history-list');
const historyLoading = document.getElementById('history-loading');
const historyError = document.getElementById('history-error');
const historyEmpty = document.getElementById('history-empty');
const refreshHistoryBtn = document.getElementById('refresh-history-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const retryBtn = document.getElementById('retry-btn');
const toast = document.getElementById('toast');

// 带超时的fetch请求
function fetchWithTimeout(url, options = {}, timeout = 15000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    return fetch(url, {
        ...options,
        signal: controller.signal
    }).finally(() => clearTimeout(timeoutId));
}

// 分页控制元素
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const currentPageEl = document.getElementById('current-page');
const totalPagesEl = document.getElementById('total-pages');
const pageJumpInput = document.getElementById('page-jump-input');
const pageJumpBtn = document.getElementById('page-jump-btn');
const paginationControls = document.getElementById('pagination-controls');

// 确认对话框元素
const confirmDialog = document.getElementById('confirm-dialog');
const confirmMessage = document.getElementById('confirm-message');
const confirmOkBtn = document.getElementById('confirm-ok-btn');
const confirmCancelBtn = document.getElementById('confirm-cancel-btn');

// 分页相关变量
let currentPage = 1;
let totalPages = 1;
let itemsPerPage = 6; // 每页显示6条记录
let allHistoryItems = []; // 存储所有历史记录

// 图片查看器实例
let imageViewer = null;

// 格式化文件大小为人类可读格式
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let unitIndex = 0;
    let size = bytes;
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    return size.toFixed(unitIndex === 0 ? 0 : 2) + ' ' + units[unitIndex];
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查验证状态
    checkVerification();
});

// 检查验证状态
function checkVerification() {
    const token = localStorage.getItem('verificationToken');
    
    // 验证令牌存在，验证其有效性
    if (token) {
        fetchWithTimeout('/api/check_verification', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token: token })
        }, 10000)  // 10秒超时
        .then(response => response.json())
        .then(data => {
            if (data.status === 0) {
                // 验证有效，初始化应用
                initializeApp();
            } else {
                // 验证无效，跳转到验证页
                redirectToVerify();
            }
        })
        .catch(error => {
            console.error('验证检查失败:', error);
            if (error.name === 'AbortError') {
                // 超时情况，显示错误让用户可以重试
                showError();
                showToast('验证请求超时，请点击重试', 'error');
            } else {
                redirectToVerify();
            }
        });
    } else {
        // 没有验证令牌，跳转到验证页
        redirectToVerify();
    }
}

// 跳转到验证页
function redirectToVerify() {
    window.location.href = '/verify';
}

// 初始化应用
function initializeApp() {
    setupEventListeners();
    loadHistory();
}

// 设置事件监听器
function setupEventListeners() {
    // 分页控制事件
    prevPageBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderHistoryPage();
            updatePaginationControls();
        }
    });
    
    nextPageBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderHistoryPage();
            updatePaginationControls();
        }
    });
    
    // 页码跳转事件
    pageJumpBtn.addEventListener('click', () => {
        jumpToPage();
    });
    
    // 在页码输入框中按回车键也可以跳转
    pageJumpInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            jumpToPage();
        }
    });
    
    // 刷新历史记录
    refreshHistoryBtn.addEventListener('click', () => {
        loadHistory();
    });
    
    // 重试按钮
    retryBtn.addEventListener('click', () => {
        loadHistory();
    });
    
    // 清空历史记录
    clearHistoryBtn.addEventListener('click', clearHistory);
}

// 显示加载状态
function showLoading() {
    historyLoading.hidden = false;
    historyError.hidden = true;
    historyEmpty.hidden = true;
    historyList.hidden = true;
    paginationControls.hidden = true;
}

// 显示错误状态
function showError() {
    historyLoading.hidden = true;
    historyError.hidden = false;
    historyEmpty.hidden = true;
    historyList.hidden = true;
    paginationControls.hidden = true;
}

// 显示空状态
function showEmpty() {
    historyLoading.hidden = true;
    historyError.hidden = true;
    historyEmpty.hidden = false;
    historyList.hidden = true;
    paginationControls.hidden = true;
}

// 显示历史列表
function showHistoryList() {
    historyLoading.hidden = true;
    historyError.hidden = true;
    historyEmpty.hidden = true;
    historyList.hidden = false;
}

// 加载历史记录
function loadHistory() {
    const token = localStorage.getItem('verificationToken');
    
    // 显示加载状态
    showLoading();
    
    fetchWithTimeout('/history', {
        headers: {
            'X-Verification-Token': token
        }
    }, 15000)  // 15秒超时
    .then(response => {
        if (response.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            throw new Error('验证已过期');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 0) {
            // 存储所有历史记录
            allHistoryItems = data.result;
            
            if (allHistoryItems.length === 0) {
                // 显示空状态
                showEmpty();
                return;
            }
            
            // 计算总页数
            totalPages = Math.ceil(allHistoryItems.length / itemsPerPage);
            
            // 如果当前页超出范围，重置为第一页
            if (currentPage > totalPages) {
                currentPage = 1;
            }
            
            // 显示历史列表
            showHistoryList();
            
            // 渲染当前页的历史记录
            renderHistoryPage();
            
            // 更新分页控制
            updatePaginationControls();
        } else {
            showError();
            showToast(`获取历史记录失败: ${data.message}`, 'error');
        }
    })
    .catch(error => {
        if (error.message !== '验证已过期') {
            showError();
            if (error.name === 'AbortError') {
                showToast('加载历史记录超时，请点击重试', 'error');
            } else {
                console.error('Error loading history:', error);
            }
        }
    });
}

// 渲染历史记录列表
function renderHistoryList(history) {
    historyList.innerHTML = '';
    
    // 渠道名称映射
    const channelMap = {
        'miyoushe': '米游社',
        'chatglm': 'ChatGLM',
        'jd': '京东'
    };
    
    history.forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <div class="history-item-img-container">
                <img class="history-item-img" src="${item.file_url}" alt="${item.file_name}" data-original="${item.file_url}" loading="lazy">
                <div class="img-loading-placeholder">
                    <div class="img-spinner"></div>
                </div>
            </div>
            <div class="history-item-info">
                <div class="history-item-name" title="${item.file_name}">${item.file_name}</div>
                <div class="history-item-time">${item.upload_time}</div>
                <div class="history-item-channel">${channelMap[item.channel] || item.channel || '未知'}${item.file_size ? ' · ' + formatFileSize(item.file_size) : ''}</div>
            </div>
            <div class="history-item-actions">
                <button class="btn copy-url-btn" title="复制链接" data-url="${item.file_url}">复制链接</button>
                <button class="btn copy-md-btn" title="复制Markdown格式" data-url="${item.file_url}" data-filename="${item.file_name}">MD格式</button>
                <button class="btn delete-btn" title="删除记录" data-id="${item.id}">删除记录</button>
            </div>
        `;
        
        // 获取图片元素，添加加载事件
        const imgEl = historyItem.querySelector('.history-item-img');
        const placeholderEl = historyItem.querySelector('.img-loading-placeholder');
        
        imgEl.addEventListener('load', () => {
            placeholderEl.style.display = 'none';
            imgEl.classList.add('loaded');
        });
        
        imgEl.addEventListener('error', () => {
            placeholderEl.innerHTML = '<span class="img-error-text">加载失败</span>';
        });
        
        // 获取复制和删除按钮
        const copyUrlButton = historyItem.querySelector('.copy-url-btn');
        const copyMdButton = historyItem.querySelector('.copy-md-btn');
        const deleteButton = historyItem.querySelector('.delete-btn');
        
        // 添加事件监听器
        copyUrlButton.addEventListener('click', () => {
            copyToClipboard(item.file_url, '图片链接已复制');
        });
        
        copyMdButton.addEventListener('click', () => {
            const mdText = `![${item.file_name}](${item.file_url})`;
            copyToClipboard(mdText, 'Markdown格式已复制');
        });
        
        deleteButton.addEventListener('click', () => {
            deleteHistoryItem(item.id);
        });
        
        historyList.appendChild(historyItem);
    });
    
    // 初始化图片查看器
    initImageViewer();
}

// 初始化图片查看器
function initImageViewer() {
    // 如果已存在查看器实例，先销毁
    if (imageViewer) {
        imageViewer.destroy();
        imageViewer = null;
    }
    
    // 获取所有历史图片
    const historyImages = document.querySelectorAll('.history-item-img');
    
    // 为每个图片添加点击事件
    historyImages.forEach(img => {
        img.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // 如果已存在查看器实例，先销毁
            if (imageViewer) {
                imageViewer.destroy();
                imageViewer = null;
            }
            
            // 创建查看器实例
            imageViewer = new Viewer(this, {
                inline: false,
                navbar: false,
                title: false,
                toolbar: {
                    zoomIn: true,
                    zoomOut: true,
                    oneToOne: true,
                    reset: true,
                    prev: false,
                    next: false,
                    rotateLeft: true,
                    rotateRight: true,
                    flipHorizontal: true,
                    flipVertical: true,
                },
                url: 'data-original',
                keyboard: true,
                backdrop: true,
                loop: false,
                tooltip: true,
                movable: true,
                zoomable: true,
                zoomRatio: 0.4,
                minZoomRatio: 0.05,
                maxZoomRatio: 10,
                rotatable: true,
                scalable: true,
                toggleOnDblclick: true,
                transition: false,
                loading: false,
                // 关键修复：在查看器隐藏后销毁实例
                hidden: function() {
                    // 延迟销毁，确保动画完成
                    setTimeout(() => {
                        if (imageViewer) {
                            imageViewer.destroy();
                            imageViewer = null;
                        }
                    }, 100);
                }
            });
            imageViewer.show();
        });
    });
}

// 渲染当前页的历史记录
function renderHistoryPage() {
    // 计算当前页的起始和结束索引
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, allHistoryItems.length);
    
    // 获取当前页的记录
    const currentPageItems = allHistoryItems.slice(startIndex, endIndex);
    
    // 渲染当前页记录
    renderHistoryList(currentPageItems);
}

// 更新分页控制按钮状态
function updatePaginationControls() {
    // 更新页码显示
    currentPageEl.textContent = currentPage;
    totalPagesEl.textContent = totalPages || 1;
    
    // 更新页码跳转输入框
    pageJumpInput.value = currentPage;
    pageJumpInput.max = totalPages || 1;
    
    // 更新按钮状态
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages || totalPages === 0;
    
    // 如果有记录，显示分页控制
    if (totalPages > 0) {
        paginationControls.hidden = false;
    }
    
    // 如果只有一页，隐藏分页控制
    if (totalPages <= 1) {
        paginationControls.style.display = 'none';
    } else {
        paginationControls.style.display = 'flex';
    }
}

// 页码跳转事件
function jumpToPage() {
    const page = parseInt(pageJumpInput.value, 10);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        renderHistoryPage();
        updatePaginationControls();
    } else {
        showToast('请输入有效的页码', 'warning');
    }
}

// 删除历史记录项
function deleteHistoryItem(id) {
    // 使用自定义确认对话框
    showConfirmDialog('确定要删除这条记录吗？', () => {
        const token = localStorage.getItem('verificationToken');
        
        fetch(`/delete_history/${id}`, { 
            method: 'DELETE',
            headers: {
                'X-Verification-Token': token
            }
        })
        .then(response => {
            if (response.status === 401) {
                // 验证已过期，重新验证
                localStorage.removeItem('verificationToken');
                redirectToVerify();
                throw new Error('验证已过期');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 0) {
                // 刷新历史记录，但尝试保持在当前页
                loadHistory();
                showToast('删除成功', 'success');
            } else {
                showToast(`删除失败: ${data.message}`, 'error');
            }
        })
        .catch(error => {
            if (error.message !== '验证已过期') {
                showToast('删除失败', 'error');
                console.error('Error deleting history item:', error);
            }
        });
    });
}

// 清空历史记录
function clearHistory() {
    // 使用自定义确认对话框
    showConfirmDialog('确定要清空所有上传历史吗？', () => {
        const token = localStorage.getItem('verificationToken');
        
        fetch('/clear_history', { 
            method: 'DELETE',
            headers: {
                'X-Verification-Token': token
            }
        })
        .then(response => {
            if (response.status === 401) {
                // 验证已过期，重新验证
                localStorage.removeItem('verificationToken');
                redirectToVerify();
                throw new Error('验证已过期');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 0) {
                // 清空历史后，重置为第一页
                currentPage = 1;
                loadHistory();
                showToast('历史记录已清空', 'success');
            } else {
                showToast(`清空失败: ${data.message}`, 'error');
            }
        })
        .catch(error => {
            if (error.message !== '验证已过期') {
                showToast('清空失败', 'error');
                console.error('Error clearing history:', error);
            }
        });
    });
}

// 复制文本到剪贴板
function copyToClipboard(text, successMessage) {
    // 创建一个临时的文本区域元素
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    let success = false;
    try {
        // 尝试使用document.execCommand API (兼容性更好)
        success = document.execCommand('copy');
        if (success) {
            showToast(successMessage || '复制成功', 'success');
        } else {
            // 如果execCommand失败，尝试使用Clipboard API
            navigator.clipboard.writeText(text)
                .then(() => showToast(successMessage || '复制成功', 'success'))
                .catch(() => showToast('复制失败', 'error'));
        }
    } catch (err) {
        console.error('复制失败:', err);
        showToast('复制失败', 'error');
    }
    
    // 移除临时元素
    document.body.removeChild(textArea);
}

// 显示提示消息
function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.hidden = false;
    
    // 移除之前的类型样式
    toast.classList.remove('toast-error', 'toast-warning', 'toast-success', 'toast-info');
    
    // 添加新的类型样式
    if (type) {
        toast.classList.add(`toast-${type}`);
    }
    
    // 根据类型设置显示时间
    const duration = type === 'error' ? 4000 : (type === 'warning' ? 3000 : 2000);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.hidden = true;
            toast.style.opacity = '1';
        }, 300);
    }, duration);
}

// 显示自定义确认对话框
function showConfirmDialog(message, onConfirm) {
    // 设置确认信息
    confirmMessage.textContent = message;
    
    // 显示对话框
    confirmDialog.style.display = 'flex';
    
    // 标记是否已经处理过确认/取消操作
    let isHandled = false;
    
    // 确认按钮事件
    const handleConfirm = () => {
        // 防止重复处理
        if (isHandled) return;
        isHandled = true;
        
        // 先清除事件监听器
        confirmOkBtn.removeEventListener('click', handleConfirm);
        confirmCancelBtn.removeEventListener('click', handleCancel);
        document.removeEventListener('keydown', handleKeyPress);
        
        // 隐藏对话框
        confirmDialog.style.display = 'none';
        
        // 执行确认回调
        setTimeout(() => onConfirm(), 10);
    };
    
    // 取消按钮事件
    const handleCancel = () => {
        // 防止重复处理
        if (isHandled) return;
        isHandled = true;
        
        // 先清除事件监听器
        confirmOkBtn.removeEventListener('click', handleConfirm);
        confirmCancelBtn.removeEventListener('click', handleCancel);
        document.removeEventListener('keydown', handleKeyPress);
        
        // 隐藏对话框
        confirmDialog.style.display = 'none';
    };
    
    // 监听Esc和Enter键
    const handleKeyPress = (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            handleCancel();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            handleConfirm();
        }
    };
    
    // 添加事件监听器
    confirmOkBtn.addEventListener('click', handleConfirm);
    confirmCancelBtn.addEventListener('click', handleCancel);
    document.addEventListener('keydown', handleKeyPress);
}
