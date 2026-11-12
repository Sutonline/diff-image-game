document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const fileNameDisplay = document.getElementById('fileNameDisplay');
  const compareBtn = document.getElementById('compareBtn');

  const splitModeSelect = document.getElementById('splitMode');
  const diffThresholdSlider = document.getElementById('diffThreshold');
  const diffThresholdVal = document.getElementById('diffThresholdVal');
  const minAreaSlider = document.getElementById('minArea');
  const minAreaVal = document.getElementById('minAreaVal');
  const blurRadiusSlider = document.getElementById('blurRadius');
  const blurRadiusVal = document.getElementById('blurRadiusVal');

  const emptyState = document.getElementById('emptyState');
  const loadingOverlay = document.getElementById('loadingOverlay');
  const resultViewer = document.getElementById('resultViewer');
  const annotatedImage = document.getElementById('annotatedImage');
  const statusBanner = document.getElementById('statusBanner');
  const diffCount = document.getElementById('diffCount');
  const activeMode = document.getElementById('activeMode');
  const execTime = document.getElementById('execTime');

  // Lightbox Zoom Elements (自由放大滑动条，点击外部缩小)
  const lightboxOverlay = document.getElementById('lightboxOverlay');
  const lightboxToolbar = document.getElementById('lightboxToolbar');
  const lightboxViewport = document.getElementById('lightboxViewport');
  const lightboxImageBox = document.getElementById('lightboxImageBox');
  const lightboxImage = document.getElementById('lightboxImage');
  const lightboxZoomSlider = document.getElementById('lightboxZoomSlider');
  const lightboxZoomVal = document.getElementById('lightboxZoomVal');
  const closeLightboxBtn = document.getElementById('closeLightboxBtn');
  const presetBtns = document.querySelectorAll('.preset-btn');
  const imageBox = document.querySelector('.image-box');

  let currentFile = null;

  // Sliders value feedback
  diffThresholdSlider.addEventListener('input', (e) => {
    diffThresholdVal.textContent = e.target.value;
  });
  minAreaSlider.addEventListener('input', (e) => {
    minAreaVal.textContent = e.target.value;
  });
  blurRadiusSlider.addEventListener('input', (e) => {
    blurRadiusVal.textContent = e.target.value;
  });

  // Drag and drop handlers
  dropZone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelected(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });

  // Global Clipboard Paste Support (Cmd+V / Ctrl+V)
  window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          handleFileSelected(file, '剪贴板粘贴截图.png');
          break;
        }
      }
    }
  });

  function handleFileSelected(file, customName = null) {
    if (!file.type.startsWith('image/')) {
      alert('请上传有效的图片文件');
      return;
    }
    currentFile = file;
    const name = customName || file.name || '已选图片';
    fileNameDisplay.textContent = `已选: ${name} (${(file.size / 1024).toFixed(1)} KB)`;
    fileNameDisplay.classList.remove('hidden');
    compareBtn.disabled = false;

    performComparison();
  }

  // Auto re-compare on slider changes
  [diffThresholdSlider, minAreaSlider, blurRadiusSlider, splitModeSelect].forEach(el => {
    el.addEventListener('change', () => {
      if (currentFile) {
        performComparison();
      }
    });
  });

  compareBtn.addEventListener('click', () => {
    if (currentFile) {
      performComparison();
    }
  });

  async function performComparison() {
    if (!currentFile) return;

    loadingOverlay.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('split_mode', splitModeSelect.value);
    formData.append('diff_threshold', diffThresholdSlider.value);
    formData.append('min_area', minAreaSlider.value);
    formData.append('blur_radius', blurRadiusSlider.value);

    try {
      const response = await fetch('/api/compare', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '识别比对异常' }));
        throw new Error(errorData.detail || '识别失败');
      }

      const data = await response.json();
      renderResults(data);
    } catch (err) {
      alert(`处理失败: ${err.message}`);
    } finally {
      loadingOverlay.classList.add('hidden');
    }
  }

  function renderResults(data) {
    emptyState.classList.add('hidden');
    resultViewer.classList.remove('hidden');
    statusBanner.classList.remove('hidden');

    annotatedImage.src = data.annotated_image_base64;
    lightboxImage.src = data.annotated_image_base64;

    // Display statistics
    diffCount.textContent = `${data.difference_count} 处`;
    activeMode.textContent = data.split_mode === 'horizontal' ? '左右水平' : '上下垂直';
    execTime.textContent = `${data.execution_time_ms} ms`;
  }

  // ========================================================
  // 自由放大弹出图层交互：滑动条控制比例，点击外部空白缩小退出
  // ========================================================

  function applyLightboxZoom(scalePercent) {
    const val = Math.max(50, Math.min(300, parseInt(scalePercent, 10) || 100));
    lightboxZoomSlider.value = val;
    lightboxZoomVal.textContent = `${val}%`;
    lightboxImageBox.style.transform = `scale(${val / 100})`;

    presetBtns.forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.scale, 10) === val);
    });
  }

  // 点击结果图片 -> 打开自由放大弹出层
  imageBox.addEventListener('click', () => {
    if (annotatedImage.src) {
      lightboxOverlay.classList.remove('hidden');
      applyLightboxZoom(100);
      lightboxViewport.scrollTop = 0;
      lightboxViewport.scrollLeft = 0;
    }
  });

  // 滑动条实时缩放比例
  lightboxZoomSlider.addEventListener('input', (e) => {
    applyLightboxZoom(e.target.value);
  });

  // 预设比例快捷按钮 (100%, 150%, 200%, 250%)
  presetBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      applyLightboxZoom(btn.dataset.scale);
    });
  });

  // 鼠标滚轮在弹出层中微调缩放比例
  lightboxViewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const currentVal = parseInt(lightboxZoomSlider.value, 10);
    const step = e.deltaY < 0 ? 10 : -10;
    applyLightboxZoom(currentVal + step);
  }, { passive: false });

  // 阻止控制栏内部点击冒泡，避免误触发关闭
  lightboxToolbar.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // 点击图片本身阻止冒泡，避免误触发关闭
  lightboxImageBox.addEventListener('click', (e) => {
    e.stopPropagation();
  });

  // 点击外部任意空白区域 (遮罩或视口边缘) -> 立即缩小关闭
  function closeLightbox() {
    lightboxOverlay.classList.add('hidden');
    applyLightboxZoom(100);
  }

  lightboxOverlay.addEventListener('click', (e) => {
    if (e.target === lightboxOverlay) {
      closeLightbox();
    }
  });

  lightboxViewport.addEventListener('click', (e) => {
    // 点击图片之外的视口空白背景即可缩小退出
    if (e.target === lightboxViewport) {
      closeLightbox();
    }
  });

  closeLightboxBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    closeLightbox();
  });

  // 按 ESC 键快速关闭缩小
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !lightboxOverlay.classList.contains('hidden')) {
      closeLightbox();
    }
  });
});
