document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements - Upload & Settings
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const fileNameDisplay = document.getElementById('fileNameDisplay');
  const compareBtn = document.getElementById('compareBtn');
  const resetParamsBtn = document.getElementById('resetParamsBtn');

  const splitModeSelect = document.getElementById('splitMode');
  const diffThresholdSlider = document.getElementById('diffThreshold');
  const diffThresholdVal = document.getElementById('diffThresholdVal');
  const minAreaSlider = document.getElementById('minArea');
  const minAreaVal = document.getElementById('minAreaVal');
  const blurRadiusSlider = document.getElementById('blurRadius');
  const blurRadiusVal = document.getElementById('blurRadiusVal');

  // DOM Elements - Preview & Viewer
  const previewContainer = document.getElementById('previewContainer');
  const emptyState = document.getElementById('emptyState');
  const loadingOverlay = document.getElementById('loadingOverlay');
  const resultViewer = document.getElementById('resultViewer');
  const stageViewport = document.getElementById('stageViewport');
  const transformLayer = document.getElementById('transformLayer');
  const annotatedImage = document.getElementById('annotatedImage');
  const imageToolbar = document.getElementById('imageToolbar');

  // DOM Elements - Toolbar
  const zoomInBtn = document.getElementById('zoomInBtn');
  const zoomOutBtn = document.getElementById('zoomOutBtn');
  const zoomResetBtn = document.getElementById('zoomResetBtn');
  const fitViewBtn = document.getElementById('fitViewBtn');
  const toggleOriginalBtn = document.getElementById('toggleOriginalBtn');
  const downloadBtn = document.getElementById('downloadBtn');
  const fullscreenBtn = document.getElementById('fullscreenBtn');

  // DOM Elements - Statistics Dashboard
  const diffStatsCard = document.getElementById('diffStatsCard');
  const execTimeBadge = document.getElementById('execTimeBadge');
  const statDiffCount = document.getElementById('statDiffCount');
  const statRadiusRange = document.getElementById('statRadiusRange');
  const statRadiusAvg = document.getElementById('statRadiusAvg');
  const statAreaTotal = document.getElementById('statAreaTotal');
  const statAreaAvg = document.getElementById('statAreaAvg');
  const statSplitMode = document.getElementById('statSplitMode');
  const statResolution = document.getElementById('statResolution');
  const foldCount = document.getElementById('foldCount');
  const diffTableBody = document.getElementById('diffTableBody');
  const copyReportBtn = document.getElementById('copyReportBtn');

  // Internal State
  let currentFile = null;
  let originalImageUrl = null;
  let annotatedImageUrl = null;
  let isViewingOriginal = false;
  let currentResultData = null;

  // Transform State (Zoom & Pan)
  let scale = 1.0;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let naturalWidth = 0;
  let naturalHeight = 0;

  // Default parameters
  const DEFAULTS = {
    threshold: 18,
    minArea: 50,
    blurRadius: 3,
    splitMode: 'auto',
  };

  // Slider synchronization
  diffThresholdSlider.addEventListener('input', (e) => {
    diffThresholdVal.textContent = e.target.value;
  });
  minAreaSlider.addEventListener('input', (e) => {
    minAreaVal.textContent = e.target.value;
  });
  blurRadiusSlider.addEventListener('input', (e) => {
    blurRadiusVal.textContent = e.target.value;
  });

  // Reset to default params
  resetParamsBtn.addEventListener('click', () => {
    diffThresholdSlider.value = DEFAULTS.threshold;
    diffThresholdVal.textContent = DEFAULTS.threshold;

    minAreaSlider.value = DEFAULTS.minArea;
    minAreaVal.textContent = DEFAULTS.minArea;

    blurRadiusSlider.value = DEFAULTS.blurRadius;
    blurRadiusVal.textContent = DEFAULTS.blurRadius;

    splitModeSelect.value = DEFAULTS.splitMode;

    if (currentFile) {
      performComparison();
    }
  });

  // File Upload Handlers
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
          handleFileSelected(file, '剪贴板粘贴图片.png');
          break;
        }
      }
    }
  });

  function handleFileSelected(file, customName = null) {
    if (!file.type.startsWith('image/')) {
      alert('请上传有效的图片文件 (PNG, JPG, WebP)');
      return;
    }
    currentFile = file;
    const displayName = customName || file.name || '已选图片';
    fileNameDisplay.textContent = `已选: ${displayName} (${(file.size / 1024).toFixed(1)} KB)`;
    fileNameDisplay.classList.remove('hidden');
    compareBtn.disabled = false;

    // Cache original image object URL for instant comparison toggle
    if (originalImageUrl) {
      URL.revokeObjectURL(originalImageUrl);
    }
    originalImageUrl = URL.createObjectURL(file);

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

  // Core Comparison Request
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
        const errorData = await response.json().catch(() => ({ detail: '比对识别异常' }));
        throw new Error(errorData.detail || '识别失败');
      }

      const data = await response.json();
      currentResultData = data;
      renderResults(data);
    } catch (err) {
      alert(`处理失败: ${err.message}`);
    } finally {
      loadingOverlay.classList.add('hidden');
    }
  }

  // Render Result and Metrics
  function renderResults(data) {
    emptyState.classList.add('hidden');
    resultViewer.classList.remove('hidden');
    imageToolbar.classList.remove('hidden');
    diffStatsCard.classList.remove('hidden');

    annotatedImageUrl = data.annotated_image_base64;
    annotatedImage.src = annotatedImageUrl;

    // Wait for image dimensions to initialize fit view
    annotatedImage.onload = () => {
      naturalWidth = annotatedImage.naturalWidth;
      naturalHeight = annotatedImage.naturalHeight;
      fitToViewport();
    };

    // Render Statistics Summary
    renderStatistics(data);
  }

  // Populate Statistics Cards
  function renderStatistics(data) {
    execTimeBadge.textContent = `耗时: ${data.execution_time_ms} ms`;
    statDiffCount.textContent = `${data.difference_count} 处`;

    const diffs = data.differences || [];
    if (diffs.length > 0) {
      const radii = diffs.map(d => d.radius);
      const areas = diffs.map(d => d.area);

      const minR = Math.min(...radii);
      const maxR = Math.max(...radii);
      const avgR = (radii.reduce((a, b) => a + b, 0) / radii.length).toFixed(1);

      const totalArea = Math.round(areas.reduce((a, b) => a + b, 0));
      const avgArea = Math.round(totalArea / areas.length);

      statRadiusRange.textContent = `${minR} ~ ${maxR} px`;
      statRadiusAvg.textContent = `均值: ${avgR} px`;

      statAreaTotal.textContent = `${totalArea.toLocaleString()} px²`;
      statAreaAvg.textContent = `均值: ${avgArea.toLocaleString()} px²`;
    } else {
      statRadiusRange.textContent = '-';
      statRadiusAvg.textContent = '均值: - px';
      statAreaTotal.textContent = '0 px²';
      statAreaAvg.textContent = '均值: - px²';
    }

    statSplitMode.textContent = data.split_mode === 'horizontal' ? '左右水平切分' : '上下垂直切分';
    statResolution.textContent = `分辨率: ${naturalWidth || '-'}×${naturalHeight || '-'} px`;

    // Populate Collapsible Table
    foldCount.textContent = diffs.length;
    diffTableBody.innerHTML = '';
    diffs.forEach(diff => {
      const tr = document.createElement('tr');
      const refCoord = diff.global_ref_center ? `(${diff.global_ref_center[0]}, ${diff.global_ref_center[1]})` : `(${diff.center_x}, ${diff.center_y})`;
      const tgtCoord = diff.global_tgt_center ? `(${diff.global_tgt_center[0]}, ${diff.global_tgt_center[1]})` : '-';
      tr.innerHTML = `
        <td style="font-weight: 700; color: #ef4444;">#${diff.id}</td>
        <td>${refCoord}</td>
        <td>${tgtCoord}</td>
        <td>${diff.radius} px</td>
        <td>${Math.round(diff.area).toLocaleString()} px²</td>
      `;
      diffTableBody.appendChild(tr);
    });
  }

  // Copy Statistics & Coordinates Report to Clipboard
  copyReportBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (!currentResultData || !currentResultData.differences) {
      alert('暂无差异数据可复制');
      return;
    }

    let report = `## 找茬游戏差异对比结果\n`;
    report += `- 差异总数: ${currentResultData.difference_count} 处\n`;
    report += `- 切分模式: ${currentResultData.split_mode}\n`;
    report += `- 执行耗时: ${currentResultData.execution_time_ms} ms\n\n`;
    report += `| 编号 | 参考图全局坐标 | 对照图全局坐标 | 半径 | 面积 |\n`;
    report += `| :--- | :--- | :--- | :--- | :--- |\n`;

    currentResultData.differences.forEach(d => {
      const refC = d.global_ref_center ? `(${d.global_ref_center[0]}, ${d.global_ref_center[1]})` : `(${d.center_x}, ${d.center_y})`;
      const tgtC = d.global_tgt_center ? `(${d.global_tgt_center[0]}, ${d.global_tgt_center[1]})` : '-';
      report += `| #${d.id} | ${refC} | ${tgtC} | ${d.radius}px | ${Math.round(d.area)}px² |\n`;
    });

    navigator.clipboard.writeText(report).then(() => {
      const originalText = copyReportBtn.textContent;
      copyReportBtn.textContent = '✅ 已复制报表!';
      setTimeout(() => {
        copyReportBtn.textContent = originalText;
      }, 2000);
    }).catch(() => {
      alert('复制失败，请手动选取表格');
    });
  });

  // ==========================================
  // Interactive Zoom & Pan Engine
  // ==========================================

  function applyTransform() {
    transformLayer.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    zoomResetBtn.textContent = `${Math.round(scale * 100)}%`;
  }

  function fitToViewport() {
    if (!naturalWidth || !naturalHeight) return;

    const vWidth = stageViewport.clientWidth;
    const vHeight = stageViewport.clientHeight;

    const padding = 32;
    const availW = Math.max(vWidth - padding * 2, 100);
    const availH = Math.max(vHeight - padding * 2, 100);

    const fitScale = Math.min(availW / naturalWidth, availH / naturalHeight, 1.0);
    scale = fitScale;

    // Center image in viewport
    translateX = (vWidth - naturalWidth * scale) / 2;
    translateY = (vHeight - naturalHeight * scale) / 2;

    applyTransform();
  }

  function setZoom(newScale, clientCenterX = null, clientCenterY = null) {
    const clampedScale = Math.max(0.1, Math.min(newScale, 8.0));

    const rect = stageViewport.getBoundingClientRect();
    const pivotX = clientCenterX !== null ? clientCenterX - rect.left : stageViewport.clientWidth / 2;
    const pivotY = clientCenterY !== null ? clientCenterY - rect.top : stageViewport.clientHeight / 2;

    // Zoom anchored to pivot point
    const factor = clampedScale / scale;
    translateX = pivotX - factor * (pivotX - translateX);
    translateY = pivotY - factor * (pivotY - translateY);
    scale = clampedScale;

    applyTransform();
  }

  // Toolbar Actions
  zoomInBtn.addEventListener('click', () => setZoom(scale * 1.25));
  zoomOutBtn.addEventListener('click', () => setZoom(scale / 1.25));
  zoomResetBtn.addEventListener('click', () => {
    scale = 1.0;
    const vWidth = stageViewport.clientWidth;
    const vHeight = stageViewport.clientHeight;
    translateX = (vWidth - naturalWidth) / 2;
    translateY = (vHeight - naturalHeight) / 2;
    applyTransform();
  });
  fitViewBtn.addEventListener('click', fitToViewport);

  // Mouse Wheel Zoom (Anchored to mouse cursor)
  stageViewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    setZoom(scale * zoomFactor, e.clientX, e.clientY);
  }, { passive: false });

  // Pan (Click and Drag)
  stageViewport.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return; // Left mouse button only
    isDragging = true;
    dragStartX = e.clientX - translateX;
    dragStartY = e.clientY - translateY;
    stageViewport.classList.add('panning');
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    translateX = e.clientX - dragStartX;
    translateY = e.clientY - dragStartY;
    applyTransform();
  });

  window.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      stageViewport.classList.remove('panning');
    }
  });

  // Double-click to toggle 100% / 150%
  stageViewport.addEventListener('dblclick', (e) => {
    if (scale < 1.4) {
      setZoom(1.5, e.clientX, e.clientY);
    } else {
      fitToViewport();
    }
  });

  // Toggle/Hold Original Image Comparison
  function showOriginal() {
    if (originalImageUrl && !isViewingOriginal) {
      isViewingOriginal = true;
      annotatedImage.src = originalImageUrl;
      toggleOriginalBtn.classList.add('active');
      toggleOriginalBtn.textContent = '🎯 查看标注';
    }
  }

  function showAnnotated() {
    if (annotatedImageUrl && isViewingOriginal) {
      isViewingOriginal = false;
      annotatedImage.src = annotatedImageUrl;
      toggleOriginalBtn.classList.remove('active');
      toggleOriginalBtn.textContent = '👁️ 对比原图';
    }
  }

  toggleOriginalBtn.addEventListener('mousedown', showOriginal);
  window.addEventListener('mouseup', () => {
    if (isViewingOriginal) showAnnotated();
  });

  toggleOriginalBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    showOriginal();
  });
  window.addEventListener('touchend', showAnnotated);

  // Download Annotated Image
  downloadBtn.addEventListener('click', () => {
    if (!annotatedImageUrl) return;
    const a = document.createElement('a');
    a.href = annotatedImageUrl;
    a.download = `diff_result_${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });

  // Fullscreen View Mode
  fullscreenBtn.addEventListener('click', () => {
    if (!document.fullscreenElement) {
      previewContainer.requestFullscreen().catch(() => {
        // Fallback for browsers blocking requestFullscreen
        previewContainer.classList.toggle('is-fullscreen');
      });
    } else {
      document.exitFullscreen();
    }
  });

  document.addEventListener('fullscreenchange', () => {
    const isFs = !!document.fullscreenElement;
    fullscreenBtn.textContent = isFs ? '✕ 退出全屏' : '⛶ 全屏';
    setTimeout(fitToViewport, 100);
  });

  // Global Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    // Ignore keystrokes when typing in inputs/textareas
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      return;
    }

    if (e.code === 'Space') {
      e.preventDefault();
      showOriginal();
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      setZoom(scale * 1.25);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      setZoom(scale / 1.25);
    } else if (e.key === '0') {
      e.preventDefault();
      fitToViewport();
    } else if (e.key.toLowerCase() === 'f') {
      e.preventDefault();
      fullscreenBtn.click();
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
      showAnnotated();
    }
  });

  // Resize listener
  window.addEventListener('resize', () => {
    if (currentResultData) {
      fitToViewport();
    }
  });
});
