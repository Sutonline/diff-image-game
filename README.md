# 🎯 Spot The Difference Game Tool (图片找茬游戏比对工具)

> **零大模型依赖 · 纯本地运行 · 毫秒级 OpenCV 亚像素配准 · 严格红圈互斥无重叠**

一个轻量、纯本地运行的找茬游戏（Spot the Difference）辅助比对工具。无需依赖任何云端视觉大模型，仅基于传统计算机视觉算法与图像形态学，在本地端即可对游戏截图进行自动视口检测、配准并用无重叠的红圈标出所有差异区域。

---

## 🌟 效果演示 (以真实手机截图 `test2.jpg` 为例)

工具自动识别出手机截图中的游戏有效双视口，并对上下两块区域进行色差与形态学聚类分析，在 **~69 毫秒** 内检出全部差异：

| 原始游戏截图 (输入) | 自动比对标注结果 (输出) |
| :---: | :---: |
| ![Original Screenshot](assets/demo_original.jpg) | ![Annotated Result](assets/demo_annotated.jpg) |

### 📊 `test2.jpg` 实测指标

* **输入尺寸**：`1170 × 2532 px` (iPhone 视网膜屏幕截图)
* **有效视口定位**：
  * 参考面板 (Reference Panel)：`Y = 465 ~ 1256` (高度 791 px)
  * 对照面板 (Target Panel)：`Y = 1256 ~ 2047` (高度 791 px)
  * 自动裁剪：滤除顶部状态栏/关卡标题以及底部道具栏与操作区
* **检出差异数量**：**21 处**
* **重叠红圈数量**：**0 处** (100% 互斥最小包围圆合并)
* **纯本地处理耗时**：**~69 ms** (C++ 底层加速)

---

## 🚀 核心技术亮点

### 1. 智能视口识别与黑边/状态栏裁剪 (`detect_viewports`)
针对手游截图中常带有的顶部刘海屏状态栏、进度星级以及底部广告道具栏，算法采用归一化互相关匹配 (Normalized Cross-Correlation) 配合 Sobel 边缘梯度剖面峰值检测，自动计算两面板的垂直/水平物理偏移量，精准提取有效游戏视口，告别暴力 50% 切分的对齐误差。

### 2. 严格互斥无重叠规则 (`merge_overlapping_circles`)
在找茬游戏中，同一个目标实体（如热气球、大树）可能包含多个相近的分散色块差异。传统找茬算法容易画出两三个相交甚至重叠的红圈。
本项目实现严格的几何相交判定：
* 若任意两个圆形标记距离 $\text{dist} < r_1 + r_2$，则判定为属于同一游戏实体的局部；
* 算法沿连心线端点自动合成包裹两者的**最小几何外接圆**，并迭代传递至全图两两互斥，确保**红圈零重叠**。

### 3. 直观轻量的 Web 交互界面
* **纯统计指标展示**：移除冗长杂乱的平铺坐标列表，顶部清晰展示差异总数、切分排布、计算耗时与去重校验状态。
* **自由放大弹出图层**：点击结果图片即可展开大图，顶部配备 **50% ~ 300% 自由放大滑动条** 与常用倍率档位（100%、150%、200%）；**点击外部暗色空白区域立即平滑缩小退出**。
* **剪贴板秒级粘贴 (<kbd>Cmd / Ctrl + V</kbd>)**：截屏后无需保存为文件，在页面任意位置直接按快捷键即可秒级触发比对。

---

## 🛠️ 快速开始

### 1. 环境准备
推荐使用 Python 3.9+ 环境：

```bash
git clone git@github.com:Sutonline/diff-image-game.git
cd diff-image-game

# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动本地服务
运行根目录下的启动脚本：

```bash
python run.py
```

服务启动后，在浏览器访问：
👉 **`http://127.0.0.1:8000`**

### 3. 运行自动化测试套件
项目配备完整的端到端和核心算法单元测试（覆盖视口识别、噪声过滤、互斥合并与截图实测）：

```bash
PYTHONPATH=. pytest tests/
```

---

## 📁 目录结构

```text
diff-image-game/
├── assets/                    # README 演示图集
│   ├── demo_original.jpg      # 演示输入原图
│   └── demo_annotated.jpg     # 演示比对标注结果
├── diff_game/                 # 核心模块
│   ├── __init__.py
│   ├── app.py                 # FastAPI 异步应用与路由
│   ├── engine.py              # CV 配准、阈值形态学与互斥外接圆引擎
│   ├── models.py              # Pydantic 领域模型
│   └── static/                # 极简 Web 前端 (HTML5 / CSS3 / Vanilla JS)
│       ├── app.js             # 剪贴板监听、滑动条放大与点击外部缩小
│       ├── index.html         # 响应式布局与统计横幅
│       └── style.css          # 暗色现代风格样式
├── docs/                      # 架构决策记录 (ADR)
│   └── adr/
│       └── 0001-minimal-cv-diff-engine.md
├── tests/                     # 自动化测试用例
│   ├── test_app.py            # API 接口测试
│   └── test_engine.py         # 图像引擎、几何合并与实测 fixture 测试
├── GLOSSARY.md                # 统一领域模型词汇表
├── pyproject.toml             # 打包与依赖配置
├── pytest.ini                 # 测试配置
├── requirements.txt           # Python 依赖清单
└── run.py                     # 本地快速启动入口
```

---

## 📄 License

MIT License.
