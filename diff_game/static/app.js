document.addEventListener('DOMContentLoaded', () => {
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
  const diffDetailsCard = document.getElementById('diffDetailsCard');
  const diffList = document.getElementById('diffList');

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

  // Drag and drop
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

  function handleFileSelected(file) {
    if (!file.type.startsWith('image/')) {
      alert('请上传有效的图片文件');
      return;
    }
    currentFile = file;
    fileNameDisplay.textContent = `已选: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    fileNameDisplay.classList.remove('hidden');
    compareBtn.disabled = false;

    // Trigger auto comparison on upload
    performComparison();
  }

  // Auto re-compare on slider change if file is already loaded
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
        const errorData = await response.json().catch(() => ({ detail: '网络或识别异常' }));
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

    diffCount.textContent = `${data.difference_count} 处`;
    activeMode.textContent = data.split_mode === 'horizontal' ? '左右并排' : '上下并排';
    execTime.textContent = `${data.execution_time_ms} ms`;

    // Render detailed coordinates
    diffList.innerHTML = '';
    if (data.differences && data.differences.length > 0) {
      diffDetailsCard.classList.remove('hidden');
      data.differences.forEach(diff => {
        const item = document.createElement('div');
        item.className = 'diff-item';
        const refCoord = diff.global_ref_center ? `(${diff.global_ref_center[0]}, ${diff.global_ref_center[1]})` : `(${diff.center_x}, ${diff.center_y})`;
        const tgtCoord = diff.global_tgt_center ? `(${diff.global_tgt_center[0]}, ${diff.global_tgt_center[1]})` : '-';
        item.innerHTML = `
          <span class="diff-badge">#${diff.id}</span>
          <span>原图: ${refCoord}</span>
          <span>对照: ${tgtCoord}</span>
          <span>半径: ${diff.radius}px</span>
        `;
        diffList.appendChild(item);
      });
    } else {
      diffDetailsCard.classList.add('hidden');
    }
  }
});
