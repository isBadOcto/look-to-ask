# 0.4.6 安装包许可与测试记录

日期：2026-10-17。范围：本地 Windows x64 安装器、便携包、应用源码及对应库源码侧包。
本轮不推送、不发布；不操作真实摄像头、麦克风或外部 AI。

## 已处理的许可问题

- 旧社区 FFmpeg 虽自报 LGPL，却静态包含 GPL FFTW。已完全排除其 DLL，使用官方 PyAV 17.1.0 BSD 绑定，并从固定源码真正编译最小 LGPLv2.1+ FFmpeg。七库的导入、许可证、配置、哈希均核验；真实 WAV 解码/重采样与三次中文识别通过。
- Qt/PySide/Shiboken 6.8.3 官方 wheel 与对应源码 commit 已核对。补齐 QtImageFormats、QtTranslations、完整 SPDX、FreeType/PCRE/Python 3.7 等通知，保留目录与 attribution；程序内增加许可证入口，并提供具体替换步骤。
- NumPy 的 OpenBLAS 含 LGPL libquadmath，不能只靠 GCC Runtime Exception。补齐 GCC 10.3.0、实际 OpenBLAS commit、NumPy 1.26.4 和固定生产配方源码；保留原通知，说明 DLL 替换与重建。
- 排除全部 Microsoft CRT/UCRT DLL及来自其他应用 PATH 的原生库。安装器检测微软官方 VC++ v14 x64 14.51.36247 或更新；Windows 10/11 提供 UCRT。摄像头扩展仅修复副本的 MSVCP 导入名。
- Intel OpenMP 改用官方运行库清单明确允许分发的固定版本，保留原 DLL、EULA、fredist、OpenMP/TCM/oneTBB 通知。接口全部匹配，真实冻结包 CPU/GPU 推理通过。CTranslate2 的静态 oneMKL 保留原 ISSL，oneDNN 保留 Apache 及第三方通知；安装器单独展示 Intel 条款，只适用于 Intel 的专有部分。
- 补齐 CPython 原生 OpenSSL/libffi/SQLite、tokenizers 的 151 个锁定 Rust crate、MediaPipe/TensorFlow/Eigen 及已识别原生依赖的源码/通知。源码和通知为保守超集，不表示所有开发或其他平台依赖都进入 DLL。
- PortAudio 只保留 Windows x64 非 ASIO 库；不收录可选 NVIDIA DLL、模型缓存或个人数据。

首轮构建遇到 Windows 长路径限制，改用保留目录的通知 ZIP；冻结自检随后发现 scikit-learn 的包内 CRT 预加载，已仅改其打包副本为系统加载，两项均经修正重测。

构建脚本、上游 URL、版本、哈希、原始许可文本、DLL 导入修复记录随包提供。
库源码侧包必须与二进制一起提供，不能仅保留上游链接。具体构建/替换见 [RELINKING.md](RELINKING.md)。

## 自动测试

- pytest：221 项通过，25.61 秒，包含本机已有模型的真实 CPU/GPU 识别与异常/连续提问测试。
- ruff、pip check：通过。
- 冻结程序：在仅保留 Windows 系统 PATH、空工作目录和隔离设置目录下，依赖、真实 EyeTrax 初始化、Whisper/VAD 与双语 UI 检查通过；许可证内容可读。
- 冻结 CPU：base/int8 模型实际识别同一合成中文测试音频三次，456 / 477 / 456 ms；冻结 GPU：medium/float16 三次为 461 / 280 / 278 ms，未回退 CPU。这些是测试夹具延迟，不是实录或外部 AI 的端到端延迟。
- 实际安装/卸载：通过。安装到经校验的新测试目录，检查文件、快捷方式、注册表与安装后的真实程序，再卸载；惰性测试设置保留。没有覆盖已有安装。
- 原生文件核验：七个最小 FFmpeg DLL 与实编哈希一致；Intel DLL 与官方可分发版本一致；没有 Microsoft CRT/UCRT 或可选 NVIDIA DLL。通知 ZIP 内确认 LGPL libquadmath、MPL Eigen、FTL、PCRE、PSF 和 Rust 原生库所需文本。
- 工程源码：Gitleaks 本地脱敏扫描未发现密钥；Git 候选源文件无本机截图、录音、校准或凭据。源码侧包来自固定公开来源，未从用户目录采集材料。

## 验证限制与人工验收

未从源码编译 Qt/PySide 或 NumPy/OpenBLAS/libquadmath；提供已对应的上游源码/生产配方，不声称第三方二进制可逐字节重现。
libffi DLL 没有版本资源，所附 MIT 来源版本根据构建来源推断，未把文件名当成精确版本证明。
未验证干净 Windows 10、缺少 VC++ 运行库的系统、真实摄像头、人工注视精度、麦克风录制或外部 AI 问答。

1. 运行 0.4.6 Setup；若提示缺少微软运行库，按官方地址安装，再重新运行。微软前置库可能需要管理员权限，应用本身按当前用户安装。
2. 检查安装语言与单独的 Intel 组件条款页面；启动后检查「开源许可证」入口及 English/简体中文切换。
3. 选择摄像头、重新校准，注视不同位置用文字模式确认裁剪和回答。
4. 准备已有语音模型，连续按键说话三次；确认松开后完成转写/回答，录音中移动注视不改变已冻结目标。
5. 退出并重开确认设置正常，校准仍须重做。若测试卸载，确认程序文件/快捷方式移除而用户设置与模型缓存保留。

来源与条件：[Qt LGPL 义务](https://www.qt.io/licensing/open-source-lgpl-obligations)、
[FFmpeg 许可](https://ffmpeg.org/legal.html)、[微软运行库分发说明](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)、
[Intel oneMKL 许可说明](https://www.intel.com/content/www/us/en/developer/articles/tool/onemkl-license-faq.html)。
Intel OpenMP 的具体许可证据为包内原始 EULA 与 fredist；完整哈希来源见 NATIVE-RUNTIME-PROVENANCE.json。
