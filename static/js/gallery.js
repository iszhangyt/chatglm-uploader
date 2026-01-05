// ==================== DOM 元素 ====================
const galleryMasonry = document.getElementById('gallery-masonry');
const galleryLoading = document.getElementById('gallery-loading');
const galleryError = document.getElementById('gallery-error');
const galleryEmpty = document.getElementById('gallery-empty');
const galleryLoadMore = document.getElementById('gallery-load-more');
const loadMoreBtn = document.getElementById('load-more-btn');
const loadMoreInfo = document.getElementById('load-more-info');
const retryBtn = document.getElementById('retry-btn');
const toast = document.getElementById('toast');

// 筛选控件
const channelFilter = document.getElementById('channel-filter');
const orientationFilter = document.getElementById('orientation-filter');
const imageCountEl = document.getElementById('image-count');

// ==================== 状态变量 ====================
let allImages = [];           // 所有图片数据
let filteredImages = [];      // 筛选后的图片
let displayedCount = 0;       // 已显示的图片数量
const BATCH_SIZE = 30;        // 每批加载数量
let imageViewer = null;       // 图片查看器实例
let isLoading = false;        // 防止重复加载
let columnCount = 4;          // 列数
let columns = [];             // 列元素数组

// ==================== 工具函数 ====================

/**
 * 带超时的 fetch 请求
 */
function fetchWithTimeout(url, options = {}, timeout = 15000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    return fetch(url, {
        ...options,
        signal: controller.signal
    }).finally(() => clearTimeout(timeoutId));
}

/**
 * 生成阿里云OSS缩略图URL
 * 米游社渠道的图片使用OSS图片处理生成缩略图
 */
function getOssThumbnailUrl(originalUrl, channel) {
    // 只有米游社渠道的图片才使用OSS图片处理
    if (channel !== 'miyoushe') {
        return originalUrl;
    }

    // OSS图片处理参数：宽度400px，质量80%，WebP格式
    const ossProcess = 'x-oss-process=image/resize,w_400/quality,q_80/interlace,1/format,webp';

    if (originalUrl.includes('?')) {
        return `${originalUrl}&${ossProcess}`;
    } else {
        return `${originalUrl}?${ossProcess}`;
    }
}

/**
 * 判断图片方向
 */
function getImageOrientation(width, height) {
    if (!width || !height) return 'unknown';
    const ratio = width / height;
    if (ratio >= 1.2) return 'landscape';
    if (ratio <= 0.8) return 'portrait';
    return 'square';
}

/**
 * 渠道名称映射
 */
const channelMap = {
    'miyoushe': '米游社',
    'chatglm': 'ChatGLM',
    'jd': '京东'
};

/**
 * 根据窗口宽度计算列数
 */
function calculateColumnCount() {
    const width = window.innerWidth;
    if (width <= 768) return 2;
    if (width <= 1024) return 3;
    return 4;
}

/**
 * 初始化列容器
 */
function initColumns() {
    columnCount = calculateColumnCount();
    columns = [];
    galleryMasonry.innerHTML = '';

    for (let i = 0; i < columnCount; i++) {
        const column = document.createElement('div');
        column.className = 'gallery-column';
        galleryMasonry.appendChild(column);
        columns.push(column);
    }
}



// ==================== 状态切换 ====================

function showLoading() {
    galleryLoading.hidden = false;
    galleryError.hidden = true;
    galleryEmpty.hidden = true;
    galleryMasonry.hidden = true;
    galleryLoadMore.hidden = true;
}

function showError() {
    galleryLoading.hidden = true;
    galleryError.hidden = false;
    galleryEmpty.hidden = true;
    galleryMasonry.hidden = true;
    galleryLoadMore.hidden = true;
}

function showEmpty() {
    galleryLoading.hidden = true;
    galleryError.hidden = true;
    galleryEmpty.hidden = false;
    galleryMasonry.hidden = true;
    galleryLoadMore.hidden = true;
}

function showGallery() {
    galleryLoading.hidden = true;
    galleryError.hidden = true;
    galleryEmpty.hidden = true;
    galleryMasonry.hidden = false;
}

/**
 * 更新加载更多按钮状态
 */
function updateLoadMoreState() {
    const remaining = filteredImages.length - displayedCount;

    if (remaining > 0) {
        galleryLoadMore.hidden = false;
        loadMoreInfo.textContent = `还有 ${remaining} 张图片`;
        loadMoreBtn.disabled = false;
    } else {
        galleryLoadMore.hidden = true;
    }
}

// ==================== 数据加载 ====================

/**
 * 加载图片数据
 */
function loadImages() {
    const token = localStorage.getItem('verificationToken');

    if (!token) {
        window.location.href = '/verify';
        return;
    }

    showLoading();

    fetchWithTimeout('/history', {
        headers: {
            'X-Verification-Token': token
        }
    }, 15000)
        .then(response => {
            if (response.status === 401) {
                localStorage.removeItem('verificationToken');
                window.location.href = '/verify';
                throw new Error('验证已过期');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 0) {
                allImages = data.result || [];
                applyFilters();
            } else {
                showError();
                showToast(`加载失败: ${data.message}`, 'error');
            }
        })
        .catch(error => {
            if (error.message !== '验证已过期') {
                showError();
                if (error.name === 'AbortError') {
                    showToast('加载超时，请点击重试', 'error');
                } else {
                    console.error('Error loading images:', error);
                }
            }
        });
}

// ==================== 筛选功能 ====================

/**
 * 应用筛选条件
 */
function applyFilters() {
    const channelValue = channelFilter.value;
    const orientationValue = orientationFilter.value;

    filteredImages = allImages.filter(img => {
        // 渠道筛选
        if (channelValue && img.channel !== channelValue) {
            return false;
        }

        // 方向筛选
        if (orientationValue) {
            const orientation = getImageOrientation(img.width, img.height);
            if (orientationValue === 'landscape' && orientation !== 'landscape') {
                return false;
            }
            if (orientationValue === 'portrait' && orientation !== 'portrait') {
                return false;
            }
        }

        return true;
    });

    // 更新图片计数
    imageCountEl.textContent = `共 ${filteredImages.length} 张图片`;

    // 重置显示状态
    displayedCount = 0;
    isLoading = false;

    // 重新初始化列
    initColumns();

    if (filteredImages.length === 0) {
        showEmpty();
    } else {
        showGallery();
        // 初次加载一批图片
        loadMoreImages();
    }
}

// ==================== 渲染画廊 ====================

/**
 * 加载更多图片
 */
function loadMoreImages() {
    // 防止重复加载
    if (isLoading) {
        return;
    }

    const remaining = filteredImages.length - displayedCount;
    const toLoad = Math.min(BATCH_SIZE, remaining);

    if (toLoad <= 0) {
        galleryLoadMore.hidden = true;
        return;
    }

    isLoading = true;
    loadMoreBtn.disabled = true;
    loadMoreBtn.textContent = '加载中...';

    const batch = filteredImages.slice(displayedCount, displayedCount + toLoad);

    // 简单轮询方式分配到各列（更可靠的方式）
    batch.forEach((img, index) => {
        const item = createGalleryItem(img);
        // 轮询分配到各列
        const targetColumn = columns[index % columnCount];
        targetColumn.appendChild(item);
    });

    displayedCount += toLoad;

    // 恢复按钮状态
    loadMoreBtn.textContent = '加载更多';
    loadMoreBtn.disabled = false;
    isLoading = false;

    // 更新加载更多状态
    updateLoadMoreState();

    // 初始化图片查看器
    initImageViewer();
}

/**
 * 创建画廊项
 */
function createGalleryItem(img) {
    const thumbnailUrl = getOssThumbnailUrl(img.file_url, img.channel);

    const item = document.createElement('div');
    item.className = 'gallery-item';

    item.innerHTML = `
        <div class="gallery-item-wrapper">
            <img class="gallery-item-img" 
                 src="${thumbnailUrl}" 
                 alt="${img.file_name}" 
                 data-original="${img.file_url}"
                 loading="lazy">
            <div class="gallery-item-loading">
                <div class="gallery-item-spinner"></div>
            </div>
            <div class="gallery-item-overlay">
                <div class="gallery-item-info">
                    <span class="gallery-item-channel">${channelMap[img.channel] || img.channel}</span>
                    ${img.width && img.height ? `<span class="gallery-item-size">${img.width}×${img.height}</span>` : ''}
                </div>
            </div>
        </div>
    `;

    // 图片加载事件
    const imgEl = item.querySelector('.gallery-item-img');
    const loadingEl = item.querySelector('.gallery-item-loading');

    imgEl.addEventListener('load', () => {
        loadingEl.style.display = 'none';
        imgEl.classList.add('loaded');
    });

    imgEl.addEventListener('error', () => {
        loadingEl.innerHTML = '<span class="gallery-item-error">加载失败</span>';
    });

    return item;
}

// ==================== 图片查看器 ====================

/**
 * 显示图片查看器
 */
function showImageViewer(imgElement) {
    if (typeof Viewer === 'undefined') {
        showToast('图片查看器正在加载，请稍后再试', 'info');
        return;
    }

    if (imageViewer) {
        imageViewer.destroy();
        imageViewer = null;
    }

    imageViewer = new Viewer(imgElement, {
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
        hidden: function () {
            setTimeout(() => {
                if (imageViewer) {
                    imageViewer.destroy();
                    imageViewer = null;
                }
            }, 100);
        }
    });
    imageViewer.show();
}

/**
 * 初始化图片查看器（绑定点击事件）
 */
function initImageViewer() {
    const galleryImages = galleryMasonry.querySelectorAll('.gallery-item-img');

    galleryImages.forEach(img => {
        // 避免重复绑定
        if (!img.dataset.viewerBound) {
            img.dataset.viewerBound = 'true';
            img.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                showImageViewer(this);
            });
        }
    });
}

// ==================== Toast 提示 ====================

function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.hidden = false;

    toast.classList.remove('toast-error', 'toast-warning', 'toast-success', 'toast-info');
    if (type) {
        toast.classList.add(`toast-${type}`);
    }

    const duration = type === 'error' ? 4000 : (type === 'warning' ? 3000 : 2000);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.hidden = true;
            toast.style.opacity = '1';
        }, 300);
    }, duration);
}

// ==================== 事件绑定 ====================

function setupEventListeners() {
    // 筛选器变化
    channelFilter.addEventListener('change', applyFilters);
    orientationFilter.addEventListener('change', applyFilters);

    // 重试按钮
    retryBtn.addEventListener('click', loadImages);

    // 加载更多
    loadMoreBtn.addEventListener('click', loadMoreImages);

    // 窗口大小变化时重新布局（防抖）
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            const newColumnCount = calculateColumnCount();
            if (newColumnCount !== columnCount) {
                // 列数变化，需要重新布局
                applyFilters();
            }
        }, 300);
    });
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadImages();
});
