// DOM元素
const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('file-input');
const uploadForm = document.getElementById('upload-form');
const channelSelect = document.getElementById('channel-select');
const uploadProgress = document.getElementById('upload-progress');
const progressBarInner = document.getElementById('progress-bar-inner');
const progressPercentage = document.getElementById('progress-percentage');
const resultSection = document.getElementById('result-section');
const resultImg = document.getElementById('result-img');
const imageUrl = document.getElementById('image-url');
const htmlCode = document.getElementById('html-code');
const markdownCode = document.getElementById('markdown-code');
const fileName = document.getElementById('file-name');
const imageSize = document.getElementById('image-size');
const uploadChannel = document.getElementById('upload-channel');
const copyUrlBtn = document.getElementById('copy-url-btn');
const copyHtmlBtn = document.getElementById('copy-html-btn');
const copyMdBtn = document.getElementById('copy-md-btn');
const uploadAnotherBtn = document.getElementById('upload-another-btn');
const historyList = document.getElementById('history-list');
const refreshHistoryBtn = document.getElementById('refresh-history-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const toast = document.getElementById('toast');
// 图片链接上传
const imageUrlInput = document.getElementById('image-url-input');
const urlUploadBtn = document.getElementById('url-upload-btn');
const urlUploadContainer = document.querySelector('.url-upload-container');
// 分页控制元素
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const currentPageEl = document.getElementById('current-page');
const totalPagesEl = document.getElementById('total-pages');
const pageJumpInput = document.getElementById('page-jump-input');
const pageJumpBtn = document.getElementById('page-jump-btn');
// 确认对话框元素
const confirmDialog = document.getElementById('confirm-dialog');
const confirmMessage = document.getElementById('confirm-message');
const confirmOkBtn = document.getElementById('confirm-ok-btn');
const confirmCancelBtn = document.getElementById('confirm-cancel-btn');

// 上传状态标记
let isUploading = false;
// 鼠标是否在上传区域内
let isMouseOverDropArea = false;
// 分页相关变量
let currentPage = 1;
let totalPages = 1;
let itemsPerPage = 6; // 每页显示6条记录
let allHistoryItems = []; // 存储所有历史记录

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
        fetch('/api/check_verification', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token: token })
        })
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
            redirectToVerify();
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
    loadHistory();
    setupEventListeners();
    // 恢复用户选择的渠道
    restoreSelectedChannel();
    
    // 页面加载完成后检测鼠标是否已经在上传区域上
    // 使用一次性的mousemove事件来获取鼠标位置
    let initialPositionChecked = false;
    function checkInitialMousePosition(e) {
        if (initialPositionChecked) return;
        initialPositionChecked = true;
        
        const dropAreaRect = dropArea.getBoundingClientRect();
        if (
            e.clientX >= dropAreaRect.left &&
            e.clientX <= dropAreaRect.right &&
            e.clientY >= dropAreaRect.top &&
            e.clientY <= dropAreaRect.bottom
        ) {
            isMouseOverDropArea = true;
        }
        
        // 移除事件监听器，不再需要它
        document.removeEventListener('mousemove', checkInitialMousePosition);
    }
    
    // 添加监听器来捕获第一次鼠标移动事件
    document.addEventListener('mousemove', checkInitialMousePosition);
}

// 设置事件监听器
function setupEventListeners() {
    // 文件选择事件
    fileInput.addEventListener('change', handleFileSelect);
    
    // 防止表单默认提交行为
    uploadForm.addEventListener('submit', (e) => {
        e.preventDefault();
        return false;
    });
    
    // 渠道选择事件 - 保存用户选择
    channelSelect.addEventListener('change', (e) => {
        saveSelectedChannel(e.target.value);
    });
    
    // 拖放区域事件
    dropArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropArea.classList.add('dragover');
    });
    
    dropArea.addEventListener('dragleave', () => {
        dropArea.classList.remove('dragover');
    });
    
    dropArea.addEventListener('drop', (e) => {
        e.preventDefault();
        dropArea.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFiles(e.dataTransfer.files);
        }
    });
    
    // 鼠标进入上传区域
    dropArea.addEventListener('mouseenter', () => {
        isMouseOverDropArea = true;
    });
    
    // 鼠标离开上传区域
    dropArea.addEventListener('mouseleave', () => {
        isMouseOverDropArea = false;
    });
    
    // 剪贴板粘贴事件 - 全局监听粘贴事件，但仅在鼠标悬停在上传区域时处理
    document.addEventListener('paste', (e) => {
        // 只有在上传区域可见且鼠标在上传区域内时才处理粘贴
        if (dropArea.hidden || !isMouseOverDropArea) {
            return;
        }
        
        const items = e.clipboardData.items;
        let imageFile = null;
        
        // 遍历粘贴的内容
        for (let i = 0; i < items.length; i++) {
            // 如果是图片类型
            if (items[i].type.indexOf('image') !== -1) {
                imageFile = items[i].getAsFile();
                break;
            }
        }
        
        // 如果找到图片，处理上传
        if (imageFile) {
            e.preventDefault(); // 阻止默认粘贴行为
            handleFiles([imageFile]);
            
            // 显示粘贴上传提示
            showToast('已从剪贴板获取图片，正在上传...');
        }
    });
    
    // 阻止渠道选择器事件冒泡
    document.querySelector('.channel-selector').addEventListener('click', (e) => {
        e.stopPropagation();
    });
    
    // 图片链接上传按钮 - 不再需要阻止事件冒泡
    if (urlUploadBtn) {
        urlUploadBtn.addEventListener('click', handleUrlUpload);
        
        // 支持在输入框中按Enter键提交
        imageUrlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleUrlUpload();
            }
        });
    }
    
    // 点击上传区域选择文件 - 改为只在标签上触发
    document.querySelector('.file-label').addEventListener('click', (e) => {
        // 阻止事件冒泡，防止触发dropArea的点击事件
        e.stopPropagation();
    });
    
    // 点击整个区域也可以选择文件，但通过标记防止重复触发
    let isSelecting = false;
    dropArea.addEventListener('click', (e) => {
        // 防止重复打开文件选择器
        if (!isSelecting) {
            isSelecting = true;
            fileInput.click();
            // 短暂延迟后重置标记
            setTimeout(() => {
                isSelecting = false;
            }, 500);
        }
    });
    
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
    refreshHistoryBtn.addEventListener('click', loadHistory);
    
    // 清空历史记录
    clearHistoryBtn.addEventListener('click', clearHistory);
    
    // 上传成功后继续上传按钮
    uploadAnotherBtn.addEventListener('click', resetUploadForm);
    
    // 复制按钮
    copyUrlBtn.addEventListener('click', () => {
        copyText(imageUrl, '图片链接已复制');
    });
    
    copyHtmlBtn.addEventListener('click', () => {
        copyText(htmlCode, 'HTML代码已复制');
    });
    
    copyMdBtn.addEventListener('click', () => {
        copyText(markdownCode, 'Markdown代码已复制');
    });
}

// 处理选择的文件
function handleFileSelect(e) {
    if (e.target.files && e.target.files.length) {
        handleFiles(e.target.files);
        // 重置文件输入框，以便能够重新选择相同的文件
        // e.target.value = '';  // 注释掉此行，避免在处理过程中清空
    }
}

// 处理文件上传
function handleFiles(files) {
    // 防止重复上传
    if (isUploading) {
        return;
    }
    
    const file = files[0]; // 只处理第一个文件
    if (!file) {
        return;
    }
    
    // 验证文件类型
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];
    if (!validTypes.includes(file.type)) {
        showToast('请选择图片文件（JPG, PNG, GIF, BMP, WEBP）');
        return;
    }
    
    // 标记上传状态
    isUploading = true;
    
    // 显示进度条
    uploadProgress.hidden = false;
    progressBarInner.style.width = '0%';
    progressPercentage.textContent = '0%';
    
    // 获取选择的渠道
    const selectedChannel = channelSelect.value;
    
    // 创建FormData
    const formData = new FormData();
    formData.append('file', file);
    formData.append('channel', selectedChannel);
    
    // 发送上传请求
    const xhr = new XMLHttpRequest();
    
    // 上传进度事件
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressBarInner.style.width = `${percentComplete}%`;
            progressPercentage.textContent = `${percentComplete}%`;
        }
    });
    
    // 上传完成事件
    xhr.addEventListener('load', () => {
        // 重置上传状态
        isUploading = false;
        
        if (xhr.status === 200) {
            try {
                const response = JSON.parse(xhr.responseText);
                if (response.status === 0) {
                    handleUploadSuccess(response.result, file.name);
                    loadHistory(); // 刷新历史记录
                } else {
                    showToast(`上传失败: ${response.message}`);
                }
            } catch (e) {
                showToast('解析响应失败');
            }
        } else if (xhr.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            showToast('验证已过期，请重新验证');
        } else {
            showToast(`上传失败: ${xhr.statusText}`);
        }
        uploadProgress.hidden = true;
        
        // 重置文件输入框，以便能够重新选择相同的文件
        fileInput.value = '';
    });
    
    // 上传错误事件
    xhr.addEventListener('error', () => {
        isUploading = false;
        showToast('上传失败，请检查网络连接');
        uploadProgress.hidden = true;
        fileInput.value = '';
    });
    
    // 上传中断事件
    xhr.addEventListener('abort', () => {
        isUploading = false;
        showToast('上传已取消');
        uploadProgress.hidden = true;
        fileInput.value = '';
    });
    
    // 发送请求
    xhr.open('POST', '/upload');
    
    // 添加验证令牌
    const token = localStorage.getItem('verificationToken');
    if (token) {
        xhr.setRequestHeader('X-Verification-Token', token);
    }
    
    xhr.send(formData);
}

// 处理上传成功
function handleUploadSuccess(result, originalFileName) {
    // 重置为第一页，因为新上传的图片会显示在第一页
    currentPage = 1;
    
    // 重新加载历史记录
    loadHistory();
    
    const fileUrl = result.file_url;
    const width = result.width || 0;
    const height = result.height || 0;
    const channelName = document.getElementById('channel-select').options[document.getElementById('channel-select').selectedIndex].text;
    
    // 显示结果区域
    resultImg.src = fileUrl;
    imageUrl.value = fileUrl;
    htmlCode.value = `<img src="${fileUrl}" alt="${originalFileName}" />`;
    markdownCode.value = `![${originalFileName}](${fileUrl})`;
    fileName.textContent = originalFileName;
    
    if (width && height) {
        imageSize.textContent = `${width} × ${height}`;
    } else {
        imageSize.textContent = '未知';
    }
    
    uploadChannel.textContent = channelName || '未知';
    
    // 隐藏上传区域，显示结果区域
    dropArea.hidden = true;
    urlUploadContainer.hidden = true; // 隐藏链接上传区域
    resultSection.hidden = false;
    
    // 将结果区域滚动到可视区域
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 重置上传表单
function resetUploadForm() {
    dropArea.hidden = false;
    urlUploadContainer.hidden = false; // 显示链接上传区域
    resultSection.hidden = true;
    fileInput.value = '';
}

// 加载历史记录
function loadHistory() {
    const token = localStorage.getItem('verificationToken');
    
    fetch('/history', {
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
            // 存储所有历史记录
            allHistoryItems = data.result;
            
            // 计算总页数
            totalPages = Math.ceil(allHistoryItems.length / itemsPerPage);
            
            // 如果当前页超出范围，重置为第一页
            if (currentPage > totalPages) {
                currentPage = 1;
            }
            
            // 渲染当前页的历史记录
            renderHistoryPage();
            
            // 更新分页控制
            updatePaginationControls();
        } else {
            showToast(`获取历史记录失败: ${data.message}`);
        }
    })
    .catch(error => {
        if (error.message !== '验证已过期') {
            showToast('获取历史记录失败');
            console.error('Error loading history:', error);
        }
    });
}

// 渲染历史记录列表
function renderHistoryList(history) {
    historyList.innerHTML = '';
    
    if (history.length === 0) {
        historyList.innerHTML = '<div class="no-history">暂无上传记录</div>';
        return;
    }
    
    // 渠道名称映射
    const channelMap = {
        'chatglm': 'ChatGLM',
        'jd': '京东'
    };
    
    history.forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <img class="history-item-img" src="${item.file_url}" alt="${item.file_name}">
            <div class="history-item-info">
                <div class="history-item-name" title="${item.file_name}">${item.file_name}</div>
                <div class="history-item-time">${item.upload_time}</div>
                <div class="history-item-channel">${channelMap[item.channel] || item.channel || '未知'}</div>
            </div>
            <div class="history-item-actions">
                <button class="btn copy-url-btn" title="复制链接" data-url="${item.file_url}">复制链接</button>
                <button class="btn copy-md-btn" title="复制Markdown格式" data-url="${item.file_url}" data-filename="${item.file_name}">MD格式</button>
                <button class="btn delete-btn" title="删除记录" data-id="${item.id}">删除记录</button>
            </div>
        `;
        
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
    
    // 如果没有记录，隐藏分页控制
    document.getElementById('pagination-controls').style.display = 
        (totalPages <= 1) ? 'none' : 'flex';
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
                loadHistory(); // 这将重新计算页数并保持当前页在有效范围内
                showToast('删除成功');
            } else {
                showToast(`删除失败: ${data.message}`);
            }
        })
        .catch(error => {
            if (error.message !== '验证已过期') {
                showToast('删除失败');
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
                showToast('历史记录已清空');
            } else {
                showToast(`清空失败: ${data.message}`);
            }
        })
        .catch(error => {
            if (error.message !== '验证已过期') {
                showToast('清空失败');
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
    textArea.style.position = 'fixed';  // 避免滚动到底部
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
            showToast(successMessage || '复制成功');
        } else {
        //     如果execCommand失败，尝试使用Clipboard API
            navigator.clipboard.writeText(text)
                .then(() => showToast(successMessage || '复制成功'))
                .catch(() => showToast('复制失败'));
        }
    } catch (err) {
        console.error('复制失败:', err);
        showToast('复制失败');
    }
    
    // 移除临时元素
    document.body.removeChild(textArea);
}

// 复制文本
function copyText(input, successMessage) {
    input.select();
    copyToClipboard(input.value, successMessage);
}

// 显示提示消息
function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.hidden = true;
            toast.style.opacity = '1';
        }, 300);
    }, 2000);
}

// 保存用户选择的渠道到localStorage
function saveSelectedChannel(channel) {
    localStorage.setItem('preferredUploadChannel', channel);
}

// 从localStorage恢复用户选择的渠道
function restoreSelectedChannel() {
    const savedChannel = localStorage.getItem('preferredUploadChannel');
    if (savedChannel) {
        channelSelect.value = savedChannel;
    }
}

// 处理URL上传
function handleUrlUpload() {
    // 防止重复上传
    if (isUploading) {
        return;
    }
    
    const url = imageUrlInput.value.trim();
    if (!url) {
        showToast('请输入图片链接');
        return;
    }
    
    // 标记上传状态
    isUploading = true;
    
    // 显示进度条
    uploadProgress.hidden = false;
    progressBarInner.style.width = '0%';
    progressPercentage.textContent = '0%';
    
    // 获取选择的渠道
    const selectedChannel = channelSelect.value;
    
    // 发送请求到服务器
    const xhr = new XMLHttpRequest();
    
    // 上传进度事件
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressBarInner.style.width = `${percentComplete}%`;
            progressPercentage.textContent = `${percentComplete}%`;
        }
    });
    
    // 上传完成事件
    xhr.addEventListener('load', () => {
        // 重置上传状态
        isUploading = false;
        
        if (xhr.status === 200) {
            try {
                const response = JSON.parse(xhr.responseText);
                if (response.status === 0) {
                    const fileName = url.split('/').pop().split('?')[0] || 'image.jpg';
                    handleUploadSuccess(response.result, fileName);
                    loadHistory(); // 刷新历史记录
                    imageUrlInput.value = ''; // 清空输入框
                } else {
                    showToast(`上传失败: ${response.message}`);
                }
            } catch (e) {
                showToast('解析响应失败');
            }
        } else if (xhr.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            showToast('验证已过期，请重新验证');
        } else {
            // 尝试解析错误信息
            try {
                const errorResponse = JSON.parse(xhr.responseText);
                if (errorResponse && errorResponse.message) {
                    showToast(`上传失败: ${errorResponse.message}`);
                } else {
                    showToast(`上传失败: ${xhr.statusText || '未知错误'}`);
                }
            } catch (e) {
                // 如果无法解析JSON，显示更友好的错误信息
                const statusMessages = {
                    400: '请求参数错误',
                    401: '未授权，请重新登录',
                    403: '禁止访问此资源',
                    404: '请求的资源不存在',
                    500: '服务器内部错误',
                    502: '网关错误',
                    503: '服务暂时不可用',
                    504: '网关超时'
                };
                const message = statusMessages[xhr.status] || `${xhr.status} ${xhr.statusText || '未知错误'}`;
                showToast(`上传失败: ${message}`);
            }
        }
        uploadProgress.hidden = true;
    });
    
    // 上传错误事件
    xhr.addEventListener('error', () => {
        isUploading = false;
        showToast('上传失败，请检查网络连接');
        uploadProgress.hidden = true;
    });
    
    // 上传中断事件
    xhr.addEventListener('abort', () => {
        isUploading = false;
        showToast('上传已取消');
        uploadProgress.hidden = true;
    });
    
    // 发送请求
    xhr.open('POST', '/upload_from_url');
    
    // 添加验证令牌
    const token = localStorage.getItem('verificationToken');
    if (token) {
        xhr.setRequestHeader('X-Verification-Token', token);
    }
    
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.send(JSON.stringify({
        url: url,
        channel: selectedChannel
    }));
    
    showToast('正在从链接获取图片...');
}

// 页码跳转事件
function jumpToPage() {
    const page = parseInt(pageJumpInput.value, 10);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        renderHistoryPage();
        updatePaginationControls();
    } else {
        showToast('请输入有效的页码');
    }
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