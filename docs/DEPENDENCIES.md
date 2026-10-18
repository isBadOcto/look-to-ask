# 当前依赖、来源与许可证

当前本地版本 0.4.6。实际固定版本见 `requirements-lock.txt`；本轮多语言使用已有 PySide6 6.8.3 的 QtCore 翻译机制和 lrelease 工具，没有新增或升级 pip 运行依赖。应用自己的 TS/QM 文案适用项目 MIT 许可证。
只保留 EyeTrax 眼动方案，未采用的替代源码、浏览器对照工具及其分发入口已移除。

## 原创与眼动源码

项目原创代码为 MIT。EyeTrax 0.4.0 MIT 核心收录于 `src/look_to_ask/_vendor/eyetrax/`，
上游 commit `84e13a16af168ac7c383f7d50ec901cd6c0ad61d`。LICENSE、UPSTREAM、manifest 哈希随源码保留并测试。
个人屏幕校准调用其既有 Ridge；不训练新的视觉模型，不保存个人特征/模型。

## 运行库

| 组件 | 当前版本 | 许可与用途 |
|---|---|---|
| MediaPipe | 0.10.32 | Apache-2.0；现成人脸/眼部特征 |
| OpenCV contrib | 4.11.0.86 | Apache-2.0；Windows 摄像头采集，仅此包提供 cv2 |
| cv2-enumerate-cameras | 1.4.0 | MIT；只枚举名称与摄像头索引 |
| NumPy / SciPy | 1.26.4 / 1.15.3 | BSD；数值运算、音频重采样 |
| scikit-learn | 1.6.1 | BSD-3-Clause；EyeTrax 原坐标回归 |
| screeninfo | 0.8.1 | MIT；原有显示器工具 |
| PySide6 Essentials / Shiboken | 6.8.3 | Qt 的 LGPLv3/GPL/商业许可，依所用模块与附带组件履行义务 |
| faster-whisper | 1.2.1 | MIT；本地语音识别，来源 SYSTRAN/faster-whisper |
| CTranslate2 | 4.8.3 | MIT 原生推理；可选 CUDA 路径 |
| sounddevice | 0.5.6 | MIT；本地按键录音，Windows wheel 含 PortAudio 通知 |
| PyAV | 17.1.0 | BSD-3-Clause 官方绑定；打包替换为自编译最小 LGPL FFmpeg |
| ONNX Runtime | 1.31.0 | MIT；Silero VAD 所需推理 |

其他传递依赖保留实际 wheel 的通知。`build/LICENSES/BUILD-ENVIRONMENT.json` 是包含开发工具的环境超集，
不是全部打包声明；`dist/BUNDLE-MANIFEST.json` 记录真正分发的文件。包内 `_internal/LICENSES/` 收集通知。
OpenAI 兼容 HTTP 复用 QtNetwork/标准库，不安装提供商 SDK。无数据库、微服务、MCP 或 Agent 框架。

## 原生库与构建

0.4.6 不再使用社区 PyAV LGPL wheel：审查发现其中 Chromaprint 静态引入 GPL FFTW，不能只根据 FFmpeg 自报 LGPL 判断许可。
源码依赖改为官方 PyPI `av==17.1.0`。打包时保留 BSD 绑定代码，仅在副本中修复 DLL 导入名；排除官方 wheel 的所有 FFmpeg/外部 codec DLL。
使用 `scripts/build_minimal_ffmpeg.py` 从哈希固定的 `e4c7fbf6c0` 源码实际编译 7 个音频所需共享库：关闭 autodetect/GPL/nonfree/version3/network，不链接 FFTW 或其他外部编解码库，采用 LGPLv2.1-or-later。
配置、构建日志、输出哈希、GCC runtime exception 和 MinGW 通知进入 LibrarySources.zip；编译器只用于构建，不进入应用包。

Qt/PySide/Shiboken 6.8.3 的官方 wheel 和对应源码 commit 已对应；完整 QtBase、QtSvg、QtImageFormats、QtTranslations 和 pyside-setup 源码与许可证一起提供。
收集器保留源路径，包括所有 LICENSES 文本、LICENCE、FTL、Python 3.7 PSF 文本和 qt_attribution.json，避免扁平化遗漏。
程序提供显著的许可证入口；[RELINKING.md](RELINKING.md) 给出 LGPL 库实际路径和替换/重建步骤。

标准包排除所有微软 CRT/UCRT DLL，不从其他应用的 PATH 采集运行库。需要用户另装微软官方 VC++ v14 x64 14.51.36247 或更新，安装程序检测前置条件；Windows 10/11 提供 UCRT。
摄像头枚举扩展在打包副本中将哈希 MSVCP 导入名改为系统 MSVCP140.dll，不改枚举逻辑。
PortAudio 只保留 Windows x64 非 ASIO DLL，排除未使用的 ASIO 和其他架构库。

CTranslate2/tokenizers wheel 缺失的顶层许可从固定标签/哈希补齐。原生 OpenMP、CPython 的 OpenSSL/libffi/SQLite 另保留各自许可；详见 THIRD_PARTY_NOTICES.md 和包内 LICENSES。
Intel OpenMP 使用明确列入官方 fredist 的 `5.0.20250422`，CTranslate2 静态 oneMKL 2025.3.0 使用 Intel Simplified Software License，oneDNN 3.1.1 为 Apache；保留各自原始条款。
NumPy 内嵌的 libquadmath 是 LGPLv2.1+，对应 GCC 10.3.0/OpenBLAS/生产配方源码随侧包提供。MediaPipe/Eigen 及全部锁定 Rust crate 的对应源码/通知也随侧包保留。
上游深层通知目录放入 `UPSTREAM-NOTICES.zip`，保留路径而不触发 Windows 长路径限制。摄像头 PE 导入和 scikit-learn 的两处 CRT 预加载均只修改打包副本，数值代码不变。
构建使用 PyInstaller 6.22.3（GPL + 应用打包例外）、NSIS 3.13（使用的核心/压缩器为 zlib/libpng）和 GCC 14.2 / MinGW-w64 12（仅构建工具）。
不升级或替换眼动、语音推理算法。构建方式见 [PACKAGING.md](PACKAGING.md)，实测结果见 [LICENSE-AUDIT.zh.md](LICENSE-AUDIT.zh.md)。

## 通用模型

MediaPipe FaceLandmarker 首次按需缓存，不收录个人校准。Whisper 模型也只按需缓存，未进入安装包或源码包。
本机验证过的 SYSTRAN 通用权重，模型卡标注 MIT：

| 模型 | 缓存 revision | 约下载大小 |
|---|---|---:|
| base | `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` | 145 MB |
| small | `536b0662742c02347bc0e980a01041f333bce120` | 490 MB |
| medium | `08e178d48790749d25932bbc082711ddcfdfbc4f` | 1.5 GB |

来源为 Hugging Face 的 `Systran/faster-whisper-{name}`。运行时允许标准模型名与本地目录，
不把用户自选模型都宣称为 MIT。Silero VAD ONNX 是 faster-whisper 的通用资源，随包保留 MIT 通知。

## 可选 NVIDIA GPU 运行库

| 官方 PyPI wheel | 固定版本 | 许可 |
|---|---|---|
| nvidia-cublas-cu12 | 12.8.4.1 | NVIDIA Proprietary Software |
| nvidia-cudnn-cu12 | 9.10.2.21 | LicenseRef-NVIDIA-Proprietary |
| nvidia-cuda-runtime-cu12 | 12.8.90 | NVIDIA Proprietary Software |

这些是专有运行库，不是项目的 MIT 开源源码。可选脚本独立安装到 `%LOCALAPPDATA%/LookToAsk/gpu`，
保留各 wheel 的许可证；不修改系统 PATH/驱动，不加入默认依赖锁文件或普通二进制包。
CTranslate2 wheel 自带的 cuDNN 调度 DLL 也在标准包中排除；CPU 导入不依赖它。
审计拒绝 cuBLAS/cuDNN/CUDA Runtime/NVRTC DLL。未来若捆绑必须另行复核 NVIDIA 再分发条款。
实际 GPU/CPU 运行与安装步骤见 [SPEECH.zh.md](SPEECH.zh.md)。
